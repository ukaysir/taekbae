from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from taekbae.analysis import assess_forecast_readiness
from taekbae.config import KST


ROUTE_REQUIRED_FIELDS = {"route_id", "stop_order", "segment_id", "planned_at_kst"}
RISK_OUTPUT_FIELDS = [
    "route_id",
    "stop_order",
    "segment_id",
    "segment_label",
    "zone",
    "planned_at_kst",
    "forecast_at_kst",
    "target_at_kst",
    "predicted_travel_time_sec",
    "baseline_travel_time_sec",
    "expected_delay_sec",
    "observed_speed_kmh",
    "observed_traffic_state",
    "risk_grade",
    "risk_basis",
    "exposure_proxy",
    "model_status",
    "confidence_or_warning",
    "source_updated_at_kst",
    "matched",
]


def _observation_grade(traffic_state: str | None) -> tuple[str, str]:
    mapping = {
        "정체": ("high", "official_current_traffic_state"),
        "지체": ("medium", "official_current_traffic_state"),
        "원활": ("low", "official_current_traffic_state"),
    }
    return mapping.get(traffic_state or "", ("unknown", "insufficient_observation"))


def latest_risk_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    readiness = assess_forecast_readiness(connection)
    rows = connection.execute(
        """
        WITH ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY source, segment_id ORDER BY observed_at_kst DESC
            ) AS row_number
            FROM traffic_observations
        )
        SELECT source, observed_at_kst, segment_id, segment_label, zone,
               speed_kmh, traffic_state, travel_time_sec
        FROM ranked
        WHERE row_number = 1
        ORDER BY zone, row_order, segment_id
        """
    ).fetchall()
    result = []
    for row in rows:
        grade, basis = _observation_grade(row["traffic_state"])
        warning = (
            "예측 아님: 공식 트램 페이지의 현재 교통상태를 그대로 분류"
            if row["source"] == "djtram_web"
            else "AI 모델 검증 전 현재 관측값만 제공"
        )
        result.append(
            {
                "segment_id": row["segment_id"],
                "segment_label": row["segment_label"],
                "zone": row["zone"],
                "forecast_at_kst": row["observed_at_kst"],
                "target_at_kst": None,
                "predicted_travel_time_sec": None,
                "baseline_travel_time_sec": None,
                "expected_delay_sec": None,
                "observed_speed_kmh": row["speed_kmh"],
                "observed_traffic_state": row["traffic_state"],
                "risk_grade": grade,
                "risk_basis": basis,
                "exposure_proxy": None,
                "model_status": readiness["status"],
                "confidence_or_warning": warning,
                "source_updated_at_kst": row["observed_at_kst"],
            }
        )
    return result


def load_route_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = sorted(ROUTE_REQUIRED_FIELDS - fields)
        if missing:
            raise ValueError(f"route CSV missing required fields: {', '.join(missing)}")
        rows = [dict(row) for row in reader]
    if not rows:
        raise ValueError("route CSV has no data rows")
    for index, row in enumerate(rows, start=2):
        try:
            datetime.fromisoformat(row["planned_at_kst"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid planned_at_kst at CSV row {index}") from exc
    return rows


def enrich_route(
    connection: sqlite3.Connection, route_rows: Iterable[dict[str, str]]
) -> list[dict[str, Any]]:
    current = {row["segment_id"]: row for row in latest_risk_rows(connection)}
    enriched: list[dict[str, Any]] = []
    for route in route_rows:
        observation = current.get(route["segment_id"])
        base = {
            "route_id": route["route_id"],
            "stop_order": route["stop_order"],
            "segment_id": route["segment_id"],
            "segment_label": None,
            "zone": None,
            "planned_at_kst": route["planned_at_kst"],
            "forecast_at_kst": None,
            "target_at_kst": None,
            "predicted_travel_time_sec": None,
            "baseline_travel_time_sec": None,
            "expected_delay_sec": None,
            "observed_speed_kmh": None,
            "observed_traffic_state": None,
            "risk_grade": "unknown",
            "risk_basis": "segment_not_found",
            "exposure_proxy": None,
            "model_status": "unavailable",
            "confidence_or_warning": "입력 segment_id를 현재 관측자료에서 찾지 못함",
            "source_updated_at_kst": None,
            "matched": False,
        }
        if observation:
            base.update(observation)
            base["matched"] = True
            base["planned_at_kst"] = route["planned_at_kst"]
            base["route_id"] = route["route_id"]
            base["stop_order"] = route["stop_order"]
        enriched.append(base)
    return enriched


def write_risk_json(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "0.1.0",
        "generated_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "records": rows,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_risk_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RISK_OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
