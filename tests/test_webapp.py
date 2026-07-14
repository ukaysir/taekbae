from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taekbae.models import TrafficObservation
from taekbae.storage import connect, insert_observations
from taekbae.webapp import build_dashboard_payload, dashboard_html


class DashboardTests(unittest.TestCase):
    def test_payload_exposes_observation_only_notice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            connection = connect(root / "test.sqlite")
            try:
                insert_observations(
                    connection,
                    [
                        TrafficObservation(
                            source="djtram_web",
                            observed_at_kst="2026-07-15T09:00:00+09:00",
                            segment_id="segment-a",
                            source_url="https://example.test",
                            source_hash="hash",
                            row_order=1,
                            speed_kmh=35,
                            zone=1,
                            traffic_state="원활",
                        )
                    ],
                )
                payload = build_dashboard_payload(connection, events_path=root / "missing.csv")
            finally:
                connection.close()
        self.assertEqual("observation_monitoring", payload["status"]["mode"])
        self.assertIn("예측이 아닙니다", payload["status"]["notice"])
        self.assertEqual(1, len(payload["segments"]))
        self.assertEqual(1, payload["quality"]["continuity"][0]["snapshots"])
        self.assertIn("/api/dashboard", dashboard_html())
