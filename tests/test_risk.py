from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taekbae.models import TrafficObservation
from taekbae.risk import enrich_route, latest_risk_rows, load_route_csv
from taekbae.storage import connect, insert_observations


class RiskContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.connection = connect(self.root / "test.sqlite")
        insert_observations(
            self.connection,
            [
                TrafficObservation(
                    source="djtram_web",
                    observed_at_kst="2026-07-15T09:00:00+09:00",
                    segment_id="segment-a",
                    source_url="https://example.test",
                    source_hash="hash",
                    row_order=1,
                    speed_kmh=12,
                    zone=12,
                    segment_label="중앙로 하행",
                    traffic_state="정체",
                )
            ],
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.temp.cleanup()

    def test_current_state_is_not_mislabeled_as_prediction(self) -> None:
        rows = latest_risk_rows(self.connection)
        self.assertEqual("high", rows[0]["risk_grade"])
        self.assertEqual("official_current_traffic_state", rows[0]["risk_basis"])
        self.assertIsNone(rows[0]["predicted_travel_time_sec"])
        self.assertIn("예측 아님", rows[0]["confidence_or_warning"])

    def test_route_contract_matches_and_preserves_plan_time(self) -> None:
        route = [
            {
                "route_id": "route-1",
                "stop_order": "1",
                "segment_id": "segment-a",
                "planned_at_kst": "2026-07-15T10:30:00+09:00",
            }
        ]
        enriched = enrich_route(self.connection, route)
        self.assertTrue(enriched[0]["matched"])
        self.assertEqual(route[0]["planned_at_kst"], enriched[0]["planned_at_kst"])

    def test_route_csv_rejects_missing_fields(self) -> None:
        path = self.root / "bad.csv"
        path.write_text("route_id,segment_id\nr1,s1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            load_route_csv(path)
