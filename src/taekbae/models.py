from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class TrafficObservation:
    source: str
    observed_at_kst: str
    segment_id: str
    source_url: str
    source_hash: str
    row_order: int
    speed_kmh: float
    zone: int | None = None
    link_id: str | None = None
    segment_label: str | None = None
    road_name: str | None = None
    direction: str | None = None
    start_name: str | None = None
    end_name: str | None = None
    traffic_state: str | None = None
    travel_time_sec: float | None = None
    congestion_code: int | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WeatherObservation:
    source: str
    observed_at_kst: str
    station_id: int
    station_name: str | None
    temperature_c: float | None
    rainfall_mm: float | None
    wind_speed_mps: float | None
    humidity_percent: float | None
    source_url: str
    source_hash: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
