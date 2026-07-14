from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_DECISIONS = {"include_pilot", "candidate", "excluded"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def validate_event_mapping(
    connection: sqlite3.Connection,
    *,
    events_path: Path,
    mapping_path: Path,
    verified_scope_events: set[str] | None = None,
) -> dict[str, Any]:
    events = {row["event_id"]: row for row in _read_csv(events_path)}
    mappings = _read_csv(mapping_path)
    current_segments = {
        str(row["segment_id"]): str(row["segment_label"] or "")
        for row in connection.execute(
            """
            WITH latest AS (
                SELECT source, segment_id, segment_label,
                       ROW_NUMBER() OVER (
                           PARTITION BY source, segment_id ORDER BY observed_at_kst DESC
                       ) AS row_number
                FROM traffic_observations
                WHERE source = 'djtram_web'
            )
            SELECT segment_id, segment_label FROM latest WHERE row_number = 1
            """
        )
    }
    errors: list[dict[str, Any]] = []
    duplicate_pairs: Counter[tuple[str, str]] = Counter()
    by_event: dict[str, list[dict[str, str]]] = defaultdict(list)
    for index, row in enumerate(mappings, start=2):
        event_id = row.get("event_id", "")
        segment_id = row.get("segment_id", "")
        duplicate_pairs[(event_id, segment_id)] += 1
        by_event[event_id].append(row)
        if event_id not in events:
            errors.append({"row": index, "field": "event_id", "error": "unknown_event"})
        if segment_id not in current_segments:
            errors.append({"row": index, "field": "segment_id", "error": "unknown_segment"})
        elif row.get("segment_label", "") != current_segments[segment_id]:
            errors.append({"row": index, "field": "segment_label", "error": "label_mismatch"})
        if row.get("confidence") not in VALID_CONFIDENCE:
            errors.append({"row": index, "field": "confidence", "error": "invalid_value"})
        if row.get("decision") not in VALID_DECISIONS:
            errors.append({"row": index, "field": "decision", "error": "invalid_value"})
    for (event_id, segment_id), count in duplicate_pairs.items():
        if count > 1:
            errors.append(
                {
                    "event_id": event_id,
                    "segment_id": segment_id,
                    "error": "duplicate_event_segment_pair",
                    "count": count,
                }
            )

    event_summary = []
    for event_id, event in events.items():
        rows = by_event.get(event_id, [])
        decisions = Counter(row.get("decision") for row in rows)
        confidence = Counter(row.get("confidence") for row in rows)
        event_summary.append(
            {
                "event_id": event_id,
                "status": event.get("status_as_of_2026_07_14"),
                "mapping_rows": len(rows),
                "include_pilot_segments": decisions.get("include_pilot", 0),
                "candidate_segments": decisions.get("candidate", 0),
                "excluded_segments": decisions.get("excluded", 0),
                "high_confidence_segments": confidence.get("high", 0),
                "medium_confidence_segments": confidence.get("medium", 0),
                "low_confidence_segments": confidence.get("low", 0),
            }
        )
    high_confidence_segment_events = {
        row["event_id"]
        for row in mappings
        if row.get("decision") == "include_pilot" and row.get("confidence") == "high"
    }
    eligible_mapping_events = {
        row["event_id"]
        for row in mappings
        if row.get("decision") == "include_pilot"
        and row.get("confidence") in {"high", "medium"}
    }
    verified_scope_events = verified_scope_events or set()
    qualified_pilot_events = eligible_mapping_events & verified_scope_events
    gate_passed = not errors and len(qualified_pilot_events) >= 2
    return {
        "status": "valid" if not errors else "invalid",
        "gate_2_status": "passed" if gate_passed else "partial",
        "gate_2_rule": (
            "at least two events with verified high-confidence official scope evidence "
            "and included medium/high-confidence observed segments"
        ),
        "verified_high_scope_events": sorted(verified_scope_events),
        "eligible_mapping_events": sorted(eligible_mapping_events),
        "qualified_pilot_events": sorted(qualified_pilot_events),
        "high_confidence_segment_events": sorted(high_confidence_segment_events),
        "events": len(events),
        "mapping_rows": len(mappings),
        "mapped_events": len(by_event),
        "event_summary": event_summary,
        "errors": errors,
        "limitations": [
            "fallback page has no official link ID or coordinates",
            "duplicate labels are distinguished by page occurrence order",
            "medium-confidence duplicate occurrences are included as a conservative exposure set",
            "scope evidence must pass live URL, text, and asset-hash verification",
        ],
    }


def write_mapping_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
