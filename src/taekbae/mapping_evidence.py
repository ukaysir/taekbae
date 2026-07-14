from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import struct
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

from taekbae.config import KST, USER_AGENT


FetchResult = tuple[int, bytes, str]
Fetcher = Callable[[str], FetchResult]


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _fetch(url: str, *, timeout: int = 30) -> FetchResult:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return (
            int(getattr(response, "status", 200)),
            response.read(),
            str(response.headers.get("Content-Type", "")),
        )


def _compact_html(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", "", text)


def _png_size(raw: bytes) -> tuple[int | None, int | None]:
    if len(raw) >= 24 and raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", raw[16:24])
    return None, None


def validate_mapping_evidence(
    evidence_path: Path, *, fetcher: Fetcher | None = None
) -> dict[str, object]:
    rows = _read_rows(evidence_path)
    fetch = fetcher or _fetch
    cache: dict[str, FetchResult | Exception] = {}
    seen_ids: set[str] = set()
    results: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []

    def get(url: str) -> FetchResult:
        if url not in cache:
            try:
                cache[url] = fetch(url)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                cache[url] = exc
        result = cache[url]
        if isinstance(result, Exception):
            raise result
        return result

    for row_number, row in enumerate(rows, start=2):
        evidence_id = row.get("evidence_id", "").strip()
        event_id = row.get("event_id", "").strip()
        source_url = row.get("source_url", "").strip()
        asset_url = row.get("asset_url", "").strip()
        expected_hash = row.get("expected_sha256", "").strip().lower()
        expected_text = row.get("expected_text", "").strip()
        row_errors: list[str] = []
        result: dict[str, object] = {
            "evidence_id": evidence_id,
            "event_id": event_id,
            "evidence_type": row.get("evidence_type", ""),
            "confidence": row.get("confidence", ""),
            "source_url": source_url,
            "asset_url": asset_url or None,
        }
        if not evidence_id or not event_id or not source_url:
            row_errors.append("missing_required_field")
        if evidence_id in seen_ids:
            row_errors.append("duplicate_evidence_id")
        seen_ids.add(evidence_id)
        if row.get("confidence") not in {"high", "medium", "low"}:
            row_errors.append("invalid_confidence")

        try:
            source_status, source_raw, _ = get(source_url)
            result["source_http_status"] = source_status
            if source_status != 200:
                row_errors.append("source_http_error")
            if expected_text:
                text_match = re.sub(r"\s+", "", expected_text) in _compact_html(source_raw)
                result["expected_text_match"] = text_match
                if not text_match:
                    row_errors.append("expected_text_not_found")
            else:
                result["expected_text_match"] = None
        except Exception as exc:  # URL details are intentionally not included.
            result["source_error_type"] = type(exc).__name__
            row_errors.append("source_fetch_failed")

        if asset_url:
            if not expected_hash:
                row_errors.append("missing_asset_hash")
            try:
                asset_status, asset_raw, content_type = get(asset_url)
                actual_hash = hashlib.sha256(asset_raw).hexdigest()
                width, height = _png_size(asset_raw)
                result.update(
                    {
                        "asset_http_status": asset_status,
                        "asset_content_type": content_type.split(";", 1)[0],
                        "asset_bytes": len(asset_raw),
                        "asset_sha256": actual_hash,
                        "asset_hash_match": actual_hash == expected_hash,
                        "asset_width": width,
                        "asset_height": height,
                    }
                )
                if asset_status != 200:
                    row_errors.append("asset_http_error")
                if actual_hash != expected_hash:
                    row_errors.append("asset_hash_mismatch")
            except Exception as exc:
                result["asset_error_type"] = type(exc).__name__
                row_errors.append("asset_fetch_failed")
        else:
            result["asset_hash_match"] = None

        result["status"] = "valid" if not row_errors else "invalid"
        result["errors"] = row_errors
        results.append(result)
        errors.extend(
            {"row": row_number, "evidence_id": evidence_id, "error": error}
            for error in row_errors
        )

    valid_events = sorted(
        {
            str(result["event_id"])
            for result in results
            if result["status"] == "valid" and result["confidence"] == "high"
        }
    )
    return {
        "status": "valid" if not errors and rows else "invalid",
        "checked_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "evidence_rows": len(rows),
        "valid_rows": sum(result["status"] == "valid" for result in results),
        "high_confidence_verified_events": valid_events,
        "results": results,
        "errors": errors,
    }


def write_mapping_evidence_report(report: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
