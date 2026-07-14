from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taekbae.models import TrafficObservation
from taekbae.storage import connect, insert_observations


class StorageTests(unittest.TestCase):
    def test_insert_is_idempotent_for_same_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            connection = connect(Path(directory) / "test.sqlite")
            try:
                row = TrafficObservation(
                    source="test",
                    observed_at_kst="2026-07-14T12:00:00+09:00",
                    segment_id="segment-1",
                    source_url="https://example.invalid",
                    source_hash="abc",
                    row_order=1,
                    speed_kmh=20.0,
                )
                self.assertEqual(insert_observations(connection, [row]), 1)
                self.assertEqual(insert_observations(connection, [row]), 0)
                count = connection.execute("SELECT COUNT(*) FROM traffic_observations").fetchone()[0]
                self.assertEqual(count, 1)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
