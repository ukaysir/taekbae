from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

from taekbae.config import KMA_ASOS_HOURLY_ENDPOINT, KST, USER_AGENT
from taekbae.models import WeatherObservation


class KmaApiError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"KMA API error {code}: {message}")


@dataclass(frozen=True, slots=True)
class KmaWeatherPage:
    page_no: int
    num_rows: int
    total_count: int
    raw: bytes
    observations: tuple[WeatherObservation, ...]


def _number(value: object) -> float | None:
    if value in (None, "", "-", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _xml_error(raw: bytes) -> KmaApiError | None:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    code = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode")
    message = root.findtext(".//resultMsg") or root.findtext(".//errMsg")
    if code or message:
        return KmaApiError(str(code or "UNKNOWN"), str(message or "Unknown service error"))
    return None


def parse_weather_page(raw: bytes) -> KmaWeatherPage:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        service_error = _xml_error(raw)
        if service_error:
            raise service_error from exc
        raise KmaApiError("INVALID_RESPONSE", type(exc).__name__) from exc
    response = payload.get("response", {})
    header = response.get("header", {})
    code = str(header.get("resultCode", ""))
    message = str(header.get("resultMsg", ""))
    if code not in {"", "0", "00"}:
        raise KmaApiError(code, message or "Unknown service error")
    body = response.get("body", {}) or {}
    items_container = body.get("items", {}) or {}
    items = items_container.get("item", []) if isinstance(items_container, dict) else []
    if isinstance(items, dict):
        items = [items]
    source_hash = hashlib.sha256(raw).hexdigest()
    observations = []
    for item in items:
        station = _number(item.get("stnId"))
        observed_text = str(item.get("tm", "")).strip()
        if station is None or not observed_text:
            continue
        try:
            observed = datetime.strptime(observed_text, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        except ValueError:
            continue
        observations.append(
            WeatherObservation(
                source="kma_asos",
                observed_at_kst=observed.isoformat(timespec="seconds"),
                station_id=int(station),
                station_name=str(item.get("stnNm") or "").strip() or None,
                temperature_c=_number(item.get("ta")),
                rainfall_mm=_number(item.get("rn")),
                wind_speed_mps=_number(item.get("ws")),
                humidity_percent=_number(item.get("hm")),
                source_url=KMA_ASOS_HOURLY_ENDPOINT,
                source_hash=source_hash,
            )
        )
    return KmaWeatherPage(
        page_no=int(_number(body.get("pageNo")) or 1),
        num_rows=int(_number(body.get("numOfRows")) or 0),
        total_count=int(_number(body.get("totalCount")) or 0),
        raw=raw,
        observations=tuple(observations),
    )


def fetch_weather_page(
    service_key: str,
    *,
    start_dt: str,
    end_dt: str,
    start_hh: str = "00",
    end_hh: str = "23",
    station_id: int = 133,
    page_no: int = 1,
    num_rows: int = 100,
    timeout: int = 30,
) -> KmaWeatherPage:
    decoded_key = urllib.parse.unquote(service_key.strip())
    query = urllib.parse.urlencode(
        {
            "ServiceKey": decoded_key,
            "pageNo": page_no,
            "numOfRows": num_rows,
            "dataType": "JSON",
            "dataCd": "ASOS",
            "dateCd": "HR",
            "startDt": start_dt,
            "startHh": start_hh,
            "endDt": end_dt,
            "endHh": end_hh,
            "stnIds": station_id,
        }
    )
    request = urllib.request.Request(
        f"{KMA_ASOS_HOURLY_ENDPOINT}?{query}", headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        raise KmaApiError(f"HTTP_{exc.code}", "HTTP request failed") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise KmaApiError("NETWORK_ERROR", type(exc).__name__) from exc
    if status != 200:
        raise KmaApiError(f"HTTP_{status}", "Non-success HTTP response")
    return parse_weather_page(raw)
