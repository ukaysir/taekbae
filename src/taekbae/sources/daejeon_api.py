from __future__ import annotations

import hashlib
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

from taekbae.config import DAEJEON_TRAFFIC_ENDPOINT, KST, USER_AGENT
from taekbae.models import TrafficObservation


class DaejeonApiError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Daejeon traffic API error {code}: {message}")


@dataclass(frozen=True, slots=True)
class DaejeonApiPage:
    page_no: int
    num_rows: int
    total_count: int
    link_count: int | None
    raw: bytes
    observations: tuple[TrafficObservation, ...]


def _text(root: ET.Element, name: str) -> str:
    node = root.find(f".//{name}")
    return node.text.strip() if node is not None and node.text else ""


def _number(value: str, *, integer: bool = False) -> float | int | None:
    if value in ("", "-", "null", "None"):
        return None
    try:
        return int(float(value)) if integer else float(value)
    except ValueError:
        return None


def parse_api_page(raw: bytes, *, observed_at: datetime | None = None) -> DaejeonApiPage:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise DaejeonApiError("INVALID_XML", type(exc).__name__) from exc

    result_code = _text(root, "resultCode")
    result_message = _text(root, "resultMsg")
    if result_code not in {"", "0", "00"}:
        raise DaejeonApiError(result_code, result_message or "Unknown service error")

    observed_at = observed_at or datetime.now(KST)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=KST)
    observed_iso = observed_at.astimezone(KST).isoformat(timespec="seconds")
    source_hash = hashlib.sha256(raw).hexdigest()
    page_no = int(_number(_text(root, "pageNo"), integer=True) or 1)
    num_rows = int(_number(_text(root, "numOfRows"), integer=True) or 0)
    total_count = int(_number(_text(root, "totalCnt"), integer=True) or 0)
    link_count_value = _number(_text(root, "linkCount"), integer=True)
    link_count = int(link_count_value) if link_count_value is not None else None

    row_nodes = root.findall(".//item")
    if not row_nodes:
        row_nodes = root.findall(".//TRAFFIC")

    rows: list[TrafficObservation] = []
    for row_order, item in enumerate(row_nodes, start=1):
        def item_text(*names: str) -> str:
            for name in names:
                node = item.find(name)
                if node is not None and node.text:
                    return node.text.strip()
            return ""

        link_id = item_text("linkID", "linkId")
        speed = _number(item_text("speed"))
        if not link_id or speed is None:
            continue
        travel_time = _number(item_text("travelT"))
        congestion = _number(item_text("congestion"), integer=True)
        rows.append(
            TrafficObservation(
                source="daejeon_openapi",
                observed_at_kst=observed_iso,
                segment_id=link_id,
                link_id=link_id,
                segment_label=None,
                road_name=item_text("roadName") or None,
                direction=item_text("udType") or None,
                start_name=item_text("startNodeName") or None,
                end_name=item_text("endNodeName") or None,
                traffic_state=None,
                speed_kmh=float(speed),
                travel_time_sec=float(travel_time) if travel_time is not None else None,
                congestion_code=int(congestion) if congestion is not None else None,
                source_url=DAEJEON_TRAFFIC_ENDPOINT,
                source_hash=source_hash,
                row_order=row_order,
            )
        )
    return DaejeonApiPage(
        page_no=page_no,
        num_rows=num_rows,
        total_count=total_count,
        link_count=link_count,
        raw=raw,
        observations=tuple(rows),
    )


def fetch_api_page(
    service_key: str,
    *,
    page_no: int = 1,
    num_rows: int = 4000,
    observed_at: datetime | None = None,
    timeout: int = 30,
) -> DaejeonApiPage:
    decoded_key = urllib.parse.unquote(service_key.strip())
    query = urllib.parse.urlencode(
        {"serviceKey": decoded_key, "pageNo": page_no, "numOfRows": num_rows}
    )
    request = urllib.request.Request(
        f"{DAEJEON_TRAFFIC_ENDPOINT}?{query}", headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        raise DaejeonApiError(f"HTTP_{exc.code}", "HTTP request failed") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # urllib exceptions can contain the full request URL, including the key.
        raise DaejeonApiError("NETWORK_ERROR", type(exc).__name__) from exc
    if status != 200:
        raise DaejeonApiError(f"HTTP_{status}", "Non-success HTTP response")
    return parse_api_page(raw, observed_at=observed_at)
