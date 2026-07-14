from __future__ import annotations

import gzip
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from taekbae.config import KST
from taekbae.models import TrafficObservation, WeatherObservation


SCHEMA = """
CREATE TABLE IF NOT EXISTS traffic_observations (
    source TEXT NOT NULL,
    observed_at_kst TEXT NOT NULL,
    segment_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    row_order INTEGER NOT NULL,
    speed_kmh REAL NOT NULL,
    zone INTEGER,
    link_id TEXT,
    segment_label TEXT,
    road_name TEXT,
    direction TEXT,
    start_name TEXT,
    end_name TEXT,
    traffic_state TEXT,
    travel_time_sec REAL,
    congestion_code INTEGER,
    PRIMARY KEY (source, observed_at_kst, segment_id)
);
CREATE INDEX IF NOT EXISTS idx_traffic_segment_time
ON traffic_observations (segment_id, observed_at_kst);
CREATE INDEX IF NOT EXISTS idx_traffic_zone_time
ON traffic_observations (zone, observed_at_kst);

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    started_at_kst TEXT NOT NULL,
    ended_at_kst TEXT NOT NULL,
    status TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    warning_count INTEGER NOT NULL,
    details_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weather_observations (
    source TEXT NOT NULL,
    observed_at_kst TEXT NOT NULL,
    station_id INTEGER NOT NULL,
    station_name TEXT,
    temperature_c REAL,
    rainfall_mm REAL,
    wind_speed_mps REAL,
    humidity_percent REAL,
    source_url TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    PRIMARY KEY (source, observed_at_kst, station_id)
);
CREATE INDEX IF NOT EXISTS idx_weather_station_time
ON weather_observations (station_id, observed_at_kst);
"""


OBSERVATION_COLUMNS = (
    "source",
    "observed_at_kst",
    "segment_id",
    "source_url",
    "source_hash",
    "row_order",
    "speed_kmh",
    "zone",
    "link_id",
    "segment_label",
    "road_name",
    "direction",
    "start_name",
    "end_name",
    "traffic_state",
    "travel_time_sec",
    "congestion_code",
)

WEATHER_COLUMNS = (
    "source",
    "observed_at_kst",
    "station_id",
    "station_name",
    "temperature_c",
    "rainfall_mm",
    "wind_speed_mps",
    "humidity_percent",
    "source_url",
    "source_hash",
)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def insert_observations(
    connection: sqlite3.Connection, observations: Iterable[TrafficObservation]
) -> int:
    rows = []
    for observation in observations:
        values = observation.to_dict()
        rows.append(tuple(values[column] for column in OBSERVATION_COLUMNS))
    if not rows:
        return 0
    placeholders = ",".join("?" for _ in OBSERVATION_COLUMNS)
    before = connection.total_changes
    connection.executemany(
        f"INSERT OR IGNORE INTO traffic_observations "
        f"({','.join(OBSERVATION_COLUMNS)}) VALUES ({placeholders})",
        rows,
    )
    connection.commit()
    return connection.total_changes - before


def insert_weather_observations(
    connection: sqlite3.Connection, observations: Iterable[WeatherObservation]
) -> int:
    rows = []
    for observation in observations:
        values = observation.to_dict()
        rows.append(tuple(values[column] for column in WEATHER_COLUMNS))
    if not rows:
        return 0
    placeholders = ",".join("?" for _ in WEATHER_COLUMNS)
    before = connection.total_changes
    connection.executemany(
        f"INSERT OR IGNORE INTO weather_observations "
        f"({','.join(WEATHER_COLUMNS)}) VALUES ({placeholders})",
        rows,
    )
    connection.commit()
    return connection.total_changes - before


def record_run(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    source: str,
    started_at_kst: str,
    ended_at_kst: str,
    status: str,
    record_count: int,
    warning_count: int,
    details: dict[str, object],
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO collection_runs
        (run_id, source, started_at_kst, ended_at_kst, status,
         record_count, warning_count, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            source,
            started_at_kst,
            ended_at_kst,
            status,
            record_count,
            warning_count,
            json.dumps(details, ensure_ascii=False, sort_keys=True),
        ),
    )
    connection.commit()


def save_raw_response(
    raw_root: Path,
    *,
    source: str,
    observed_at: datetime,
    suffix: str,
    raw: bytes,
    metadata: dict[str, object],
) -> tuple[Path, Path]:
    timestamp = observed_at.astimezone(KST)
    directory = raw_root / source / timestamp.strftime("%Y/%m/%d")
    directory.mkdir(parents=True, exist_ok=True)
    stem = timestamp.strftime("%Y%m%dT%H%M%S%z") + f"_{suffix}"
    raw_path = directory / f"{stem}.bin.gz"
    metadata_path = directory / f"{stem}.metadata.json"
    with gzip.open(raw_path, "wb") as handle:
        handle.write(raw)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return raw_path, metadata_path
