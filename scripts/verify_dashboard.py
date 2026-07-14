from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

import websocket


EDGE_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)


def find_browser() -> Path:
    configured = os.environ.get("TAEKBAE_BROWSER_PATH")
    if configured and Path(configured).is_file():
        return Path(configured)
    for candidate in EDGE_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "No supported browser found. Set TAEKBAE_BROWSER_PATH to a Chromium executable."
    )


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_page(port: int, timeout_seconds: float = 15) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    url = f"http://127.0.0.1:{port}/json/list"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                targets = json.loads(response.read().decode("utf-8"))
            pages = [target for target in targets if target.get("type") == "page"]
            if pages:
                return pages[0]
        except Exception as exc:  # browser startup is inherently racy
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"Edge CDP page did not start: {type(last_error).__name__}")


class CdpSession:
    def __init__(self, websocket_url: str):
        self.socket = websocket.create_connection(
            websocket_url, timeout=10, suppress_origin=True
        )
        self.next_id = 1
        self.console_errors: list[str] = []
        self.page_errors: list[str] = []

    def close(self) -> None:
        self.socket.close()

    def _record_event(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        params = message.get("params", {})
        if method == "Runtime.exceptionThrown":
            details = params.get("exceptionDetails", {})
            self.page_errors.append(str(details.get("text", "Runtime exception")))
        elif method == "Runtime.consoleAPICalled" and params.get("type") == "error":
            values = [item.get("value", item.get("description", "")) for item in params.get("args", [])]
            self.console_errors.append(" ".join(str(value) for value in values))
        elif method == "Log.entryAdded" and params.get("entry", {}).get("level") == "error":
            self.console_errors.append(str(params["entry"].get("text", "Log error")))

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        message_id = self.next_id
        self.next_id += 1
        self.socket.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.socket.recv())
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method} failed: {message['error']}")
                return message.get("result", {})
            self._record_event(message)

    def evaluate(self, expression: str) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        remote = result.get("result", {})
        if "exceptionDetails" in result:
            raise RuntimeError(str(result["exceptionDetails"]))
        return remote.get("value")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--screenshot", type=Path, default=Path("outputs/figures/dashboard_full.png")
    )
    args = parser.parse_args()
    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
    port = free_port()
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    checks: dict[str, Any] = {}
    failures: list[str] = []
    with tempfile.TemporaryDirectory(
        prefix="taekbae-edge-", dir=".tmp", ignore_cleanup_errors=True
    ) as profile:
        process = subprocess.Popen(
            [
                str(find_browser()),
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--remote-allow-origins=*",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={Path(profile).resolve()}",
                args.url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        session: CdpSession | None = None
        try:
            target = wait_for_page(port)
            session = CdpSession(str(target["webSocketDebuggerUrl"]))
            session.call("Page.enable")
            session.call("Runtime.enable")
            session.call("Log.enable")
            session.call(
                "Emulation.setDeviceMetricsOverride",
                {"width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False},
            )
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                ready = session.evaluate(
                    "document.readyState === 'complete' && "
                    "document.querySelectorAll('#segmentRows tr').length === 41"
                )
                if ready:
                    break
                time.sleep(0.1)
            else:
                failures.append("dashboard data did not render within 15 seconds")

            checks["title"] = session.evaluate("document.title")
            checks["heading"] = session.evaluate("document.querySelector('h1')?.innerText")
            checks["has_observation_notice"] = session.evaluate(
                "document.querySelector('#notice')?.innerText.includes('예측이 아닙니다')"
            )
            checks["all_zone_rows"] = session.evaluate(
                "document.querySelectorAll('#segmentRows tr').length"
            )
            session.evaluate("document.querySelector('[data-zone=\"1\"]')?.click()")
            checks["zone_1_rows"] = session.evaluate(
                "document.querySelectorAll('#segmentRows tr').length"
            )
            session.evaluate("document.querySelector('[data-zone=\"12\"]')?.click()")
            checks["zone_12_rows"] = session.evaluate(
                "document.querySelectorAll('#segmentRows tr').length"
            )
            checks["event_cards"] = session.evaluate(
                "document.querySelectorAll('#events article').length"
            )
            checks["exposure_rows"] = session.evaluate(
                "payload.segments.filter(x => x.exposure_proxy != null).length"
            )
            checks["has_exposure_disclaimer"] = session.evaluate(
                "document.querySelector('.footer')?.innerText.includes('실제 택배 물량이 아닙니다')"
            )
            metrics = session.call("Page.getLayoutMetrics")
            content = metrics.get("cssContentSize") or metrics.get("contentSize")
            image = session.call(
                "Page.captureScreenshot",
                {
                    "format": "png",
                    "captureBeyondViewport": True,
                    "fromSurface": True,
                    "clip": {
                        "x": 0,
                        "y": 0,
                        "width": content["width"],
                        "height": content["height"],
                        "scale": 1,
                    },
                },
            )
            args.screenshot.write_bytes(base64.b64decode(image["data"]))
            session.evaluate("document.body.innerText.length")  # drain pending error events
        finally:
            if session is not None:
                try:
                    session.call("Browser.close")
                except Exception:
                    pass
                session.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()

    expected = {
        "title": "트램 물류영향 관측판",
        "heading": "트램 물류영향 관측판",
        "has_observation_notice": True,
        "all_zone_rows": 41,
        "zone_1_rows": 9,
        "zone_12_rows": 32,
        "event_cards": 5,
        "exposure_rows": 10,
        "has_exposure_disclaimer": True,
    }
    for name, value in expected.items():
        if checks.get(name) != value:
            failures.append(f"{name}: expected {value!r}, got {checks.get(name)!r}")
    console_errors = session.console_errors if session is not None else []
    page_errors = session.page_errors if session is not None else []
    if console_errors:
        failures.append("browser console errors detected")
    if page_errors:
        failures.append("uncaught page errors detected")

    result = {
        "status": "pass" if not failures else "fail",
        "checks": checks,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "failures": failures,
        "screenshot": str(args.screenshot),
        "browser": "Microsoft Edge via Chrome DevTools Protocol",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
