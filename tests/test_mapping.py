from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taekbae.mapping import validate_event_mapping
from taekbae.models import TrafficObservation
from taekbae.storage import connect, insert_observations


class MappingValidationTests(unittest.TestCase):
    def test_valid_mapping_can_still_leave_gate_partial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = root / "events.csv"
            mapping = root / "mapping.csv"
            events.write_text(
                "event_id,status_as_of_2026_07_14\ne1,scheduled_active\n",
                encoding="utf-8",
            )
            mapping.write_text(
                "event_id,segment_id,segment_label,mapping_method,confidence,decision,reason,checked_at_kst\n"
                "e1,s1,구간 1,exact,high,include_pilot,fixture,2026-07-15T00:00:00+09:00\n",
                encoding="utf-8",
            )
            connection = connect(root / "test.sqlite")
            try:
                insert_observations(
                    connection,
                    [
                        TrafficObservation(
                            source="djtram_web",
                            observed_at_kst="2026-07-15T00:00:00+09:00",
                            segment_id="s1",
                            source_url="fixture://page",
                            source_hash="hash",
                            row_order=1,
                            speed_kmh=30,
                            segment_label="구간 1",
                        )
                    ],
                )
                report = validate_event_mapping(
                    connection, events_path=events, mapping_path=mapping
                )
            finally:
                connection.close()
        self.assertEqual("valid", report["status"])
        self.assertEqual("partial", report["gate_2_status"])
        self.assertEqual(["e1"], report["high_confidence_segment_events"])
        self.assertEqual([], report["qualified_pilot_events"])

    def test_verified_scope_and_medium_mapping_can_pass_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = root / "events.csv"
            mapping = root / "mapping.csv"
            events.write_text(
                "event_id,status_as_of_2026_07_14\ne1,active\ne2,active\n",
                encoding="utf-8",
            )
            mapping.write_text(
                "event_id,segment_id,segment_label,mapping_method,confidence,decision,reason,checked_at_kst\n"
                "e1,s1,구간 1,official_scope,medium,include_pilot,duplicate label,2026-07-15T00:00:00+09:00\n"
                "e2,s2,구간 2,exact,high,include_pilot,exact label,2026-07-15T00:00:00+09:00\n",
                encoding="utf-8",
            )
            connection = connect(root / "test.sqlite")
            try:
                insert_observations(
                    connection,
                    [
                        TrafficObservation(
                            source="djtram_web",
                            observed_at_kst="2026-07-15T00:00:00+09:00",
                            segment_id=segment_id,
                            source_url="fixture://page",
                            source_hash="hash",
                            row_order=index,
                            speed_kmh=30,
                            segment_label=f"구간 {index}",
                        )
                        for index, segment_id in enumerate(("s1", "s2"), start=1)
                    ],
                )
                report = validate_event_mapping(
                    connection,
                    events_path=events,
                    mapping_path=mapping,
                    verified_scope_events={"e1", "e2"},
                )
            finally:
                connection.close()
        self.assertEqual("passed", report["gate_2_status"])
        self.assertEqual(["e1", "e2"], report["qualified_pilot_events"])
