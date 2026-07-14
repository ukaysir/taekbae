from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median

from taekbae.config import KST


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def build_quality_report(connection: sqlite3.Connection) -> dict[str, object]:
    overall = connection.execute(
        """
        SELECT COUNT(*) AS records,
               COUNT(DISTINCT source || '|' || observed_at_kst) AS source_snapshots,
               COUNT(DISTINCT segment_id) AS segments,
               MIN(observed_at_kst) AS first_observed_at_kst,
               MAX(observed_at_kst) AS last_observed_at_kst,
               SUM(CASE WHEN speed_kmh < 0 OR speed_kmh > 180 THEN 1 ELSE 0 END)
                 AS invalid_speed_rows,
               SUM(CASE WHEN speed_kmh = 0 THEN 1 ELSE 0 END) AS zero_speed_rows
        FROM traffic_observations
        """
    ).fetchone()
    sources = [
        dict(row)
        for row in connection.execute(
            """
            SELECT source, COUNT(*) AS records,
                   COUNT(DISTINCT observed_at_kst) AS snapshots,
                   COUNT(DISTINCT segment_id) AS segments,
                   MIN(observed_at_kst) AS first_observed_at_kst,
                   MAX(observed_at_kst) AS last_observed_at_kst
            FROM traffic_observations
            GROUP BY source ORDER BY source
            """
        )
    ]
    zones = [
        dict(row)
        for row in connection.execute(
            """
            SELECT zone, COUNT(*) AS records,
                   COUNT(DISTINCT observed_at_kst) AS snapshots,
                   COUNT(DISTINCT segment_id) AS segments,
                   ROUND(AVG(speed_kmh), 2) AS mean_speed_kmh,
                   MIN(speed_kmh) AS min_speed_kmh,
                   MAX(speed_kmh) AS max_speed_kmh
            FROM traffic_observations
            WHERE zone IS NOT NULL
            GROUP BY zone ORDER BY zone
            """
        )
    ]
    runs = [
        dict(row)
        for row in connection.execute(
            """
            SELECT run_id, source, started_at_kst, ended_at_kst, status,
                   record_count, warning_count
            FROM collection_runs
            ORDER BY started_at_kst DESC LIMIT 20
            """
        )
    ]
    snapshot_rows = connection.execute(
        """
        SELECT source, observed_at_kst, COUNT(*) AS records,
               COUNT(DISTINCT segment_id) AS segments,
               COUNT(DISTINCT source_hash) AS response_hashes
        FROM traffic_observations
        GROUP BY source, observed_at_kst
        ORDER BY source, observed_at_kst
        """
    ).fetchall()
    snapshots_by_source: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in snapshot_rows:
        snapshots_by_source[str(row["source"])].append(row)
    continuity = []
    now = datetime.now(KST)
    for source, items in snapshots_by_source.items():
        timestamps = [_time(str(row["observed_at_kst"])) for row in items]
        intervals = [
            (right - left).total_seconds() / 60
            for left, right in zip(timestamps, timestamps[1:])
        ]
        scheduled_intervals = [value for value in intervals if value >= 5]
        segment_counts = [int(row["segments"]) for row in items]
        modal_segments = Counter(segment_counts).most_common(1)[0][0] if segment_counts else 0
        continuity.append(
            {
                "source": source,
                "snapshots": len(items),
                "modal_segments_per_snapshot": modal_segments,
                "min_segments_per_snapshot": min(segment_counts) if segment_counts else 0,
                "max_segments_per_snapshot": max(segment_counts) if segment_counts else 0,
                "non_modal_snapshot_count": sum(
                    count != modal_segments for count in segment_counts
                ),
                "median_interval_minutes_all": (
                    round(median(intervals), 3) if intervals else None
                ),
                "median_interval_minutes_ge_5": (
                    round(median(scheduled_intervals), 3) if scheduled_intervals else None
                ),
                "short_interval_count_lt_5": sum(value < 5 for value in intervals),
                "long_interval_count_gt_15": sum(value > 15 for value in intervals),
                "freshness_minutes": (
                    round((now - timestamps[-1]).total_seconds() / 60, 3)
                    if timestamps
                    else None
                ),
            }
        )
    changes = [
        dict(row)
        for row in connection.execute(
            """
            WITH ordered AS (
                SELECT source, segment_id, observed_at_kst, speed_kmh, source_hash,
                       LAG(speed_kmh) OVER (
                           PARTITION BY source, segment_id ORDER BY observed_at_kst
                       ) AS previous_speed,
                       LAG(source_hash) OVER (
                           PARTITION BY source, segment_id ORDER BY observed_at_kst
                       ) AS previous_hash
                FROM traffic_observations
            )
            SELECT source,
                   SUM(CASE WHEN previous_speed IS NOT NULL THEN 1 ELSE 0 END) AS comparisons,
                   SUM(CASE WHEN previous_speed IS NOT NULL AND speed_kmh != previous_speed
                            THEN 1 ELSE 0 END) AS speed_changed_rows,
                   SUM(CASE WHEN previous_hash IS NOT NULL AND source_hash != previous_hash
                            THEN 1 ELSE 0 END) AS response_hash_changed_rows,
                   ROUND(AVG(CASE WHEN previous_speed IS NOT NULL
                             THEN ABS(speed_kmh - previous_speed) END), 3)
                     AS mean_absolute_speed_change_kmh
            FROM ordered
            GROUP BY source ORDER BY source
            """
        )
    ]
    run_summary = [
        dict(row)
        for row in connection.execute(
            """
            SELECT source, COUNT(*) AS runs,
                   SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successful_runs,
                   SUM(CASE WHEN status = 'partial' THEN 1 ELSE 0 END) AS partial_runs,
                   SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_runs,
                   SUM(record_count) AS records_reported,
                   SUM(warning_count) AS warnings_reported
            FROM collection_runs
            GROUP BY source ORDER BY source
            """
        )
    ]
    return {
        "overall": dict(overall) if overall else {},
        "sources": sources,
        "zones": zones,
        "recent_runs": runs,
        "continuity": continuity,
        "changes": changes,
        "run_summary": run_summary,
    }
