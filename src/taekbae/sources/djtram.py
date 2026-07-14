from __future__ import annotations

import hashlib
import html
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from taekbae.config import DJTRAM_ZONE_ENDPOINT, KST, USER_AGENT
from taekbae.models import TrafficObservation


_ROW_PATTERN = re.compile(
    r'<div class="swiper-slide">\s*'
    r'<p class="txt">(.*?)</p>\s*'
    r'<span[^>]*><i>(.*?)</i></span>',
    re.DOTALL,
)
_STATE_SPEED_PATTERN = re.compile(
    r"(?P<state>원활|지체|정체|정보없음)\s+"
    r"(?P<speed>[0-9]+(?:\.[0-9]+)?)\s*km",
)
_LABEL_PATTERN = re.compile(
    r"^(?P<road>.+?)\s+(?P<direction>상행|하행)"
    r"(?:\((?P<context>.*)\))?$"
)


class DjTramParseError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DjTramPage:
    zone: int
    fetched_at_kst: str
    url: str
    raw: bytes
    observations: tuple[TrafficObservation, ...]
    duplicate_label_count: int


def _clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", value)
    return " ".join(html.unescape(without_tags).split())


def _label_parts(label: str) -> tuple[str | None, str | None, str | None, str | None]:
    match = _LABEL_PATTERN.match(label)
    if not match:
        return None, None, None, None
    road = match.group("road")
    direction = match.group("direction")
    context = (match.group("context") or "").strip()
    if " 에서 " in context:
        start_name, end_name = (part.strip() for part in context.split(" 에서 ", 1))
    else:
        start_name, end_name = (context or None), None
    return road, direction, start_name, end_name


def parse_zone_page(
    raw: bytes,
    *,
    zone: int,
    observed_at: datetime | None = None,
    url: str | None = None,
) -> DjTramPage:
    if not 1 <= zone <= 14:
        raise ValueError("zone must be between 1 and 14")
    observed_at = observed_at or datetime.now(KST)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=KST)
    observed_iso = observed_at.astimezone(KST).isoformat(timespec="seconds")
    source_url = url or DJTRAM_ZONE_ENDPOINT.format(zone=zone)
    source_hash = hashlib.sha256(raw).hexdigest()
    document = raw.decode("utf-8", errors="replace")

    labels: Counter[str] = Counter()
    rows: list[TrafficObservation] = []
    for row_order, match in enumerate(_ROW_PATTERN.finditer(document), start=1):
        label = _clean_text(match.group(1))
        state_speed = _clean_text(match.group(2))
        parsed = _STATE_SPEED_PATTERN.search(state_speed)
        if not label or not parsed:
            continue
        labels[label] += 1
        occurrence = labels[label]
        identity = f"{zone}|{label}|{occurrence}".encode("utf-8")
        segment_id = f"djtram-z{zone:02d}-{hashlib.sha1(identity).hexdigest()[:12]}"
        road, direction, start_name, end_name = _label_parts(label)
        rows.append(
            TrafficObservation(
                source="djtram_web",
                observed_at_kst=observed_iso,
                zone=zone,
                segment_id=segment_id,
                segment_label=label,
                road_name=road,
                direction=direction,
                start_name=start_name,
                end_name=end_name,
                traffic_state=parsed.group("state"),
                speed_kmh=float(parsed.group("speed")),
                travel_time_sec=None,
                congestion_code=None,
                source_url=source_url,
                source_hash=source_hash,
                row_order=row_order,
            )
        )

    if not rows:
        raise DjTramParseError(f"No traffic observations found for zone {zone}")
    duplicate_count = sum(count - 1 for count in labels.values() if count > 1)
    return DjTramPage(
        zone=zone,
        fetched_at_kst=observed_iso,
        url=source_url,
        raw=raw,
        observations=tuple(rows),
        duplicate_label_count=duplicate_count,
    )


def fetch_zone(zone: int, *, observed_at: datetime | None = None, timeout: int = 30) -> DjTramPage:
    url = DJTRAM_ZONE_ENDPOINT.format(zone=zone)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        status = getattr(response, "status", 200)
    if status != 200:
        raise RuntimeError(f"Daejeon tram page returned HTTP {status} for zone {zone}")
    return parse_zone_page(raw, zone=zone, observed_at=observed_at, url=url)
