from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from taekbae.analysis import (
    assess_forecast_readiness,
    build_forecast_examples,
    evaluate_forecast_models,
)
from taekbae.config import KST
from taekbae.models import TrafficObservation
from taekbae.storage import connect, insert_observations


class AnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect(Path(self.temp.name) / "test.sqlite")
        start = datetime(2026, 7, 15, 8, 0, tzinfo=KST)
        observations = []
        for index in range(8):
            observed_at = (start + timedelta(minutes=10 * index)).isoformat(timespec="seconds")
            observations.append(
                TrafficObservation(
                    source="djtram_web",
                    observed_at_kst=observed_at,
                    segment_id="segment-a",
                    source_url="https://example.test",
                    source_hash=f"hash-{index}",
                    row_order=1,
                    speed_kmh=30 + index,
                    zone=1,
                    segment_label="테스트 구간",
                    traffic_state="원활",
                )
            )
        insert_observations(self.connection, observations)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp.cleanup()

    def test_builds_only_past_feature_future_target_rows(self) -> None:
        examples = build_forecast_examples(self.connection)
        self.assertEqual(3, len(examples))
        first = examples[0]
        self.assertEqual(32.0, first["value_now"])
        self.assertEqual(31.0, first["value_lag_10"])
        self.assertEqual(30.0, first["value_lag_20"])
        self.assertEqual(35.0, first["target_value"])
        forecast_at = datetime.fromisoformat(first["forecast_at_kst"])
        target_at = datetime.fromisoformat(first["target_at_kst"])
        self.assertEqual(timedelta(minutes=30), target_at - forecast_at)

    def test_readiness_reports_threshold_evidence(self) -> None:
        report = assess_forecast_readiness(
            self.connection,
            min_snapshots=8,
            min_span_hours=1,
            min_examples=3,
            min_distinct_dates=1,
        )
        self.assertEqual("ready", report["status"])
        self.assertEqual(8, report["actual"]["snapshots"])
        self.assertEqual(3, report["actual"]["forecast_examples"])

        default_report = assess_forecast_readiness(self.connection)
        self.assertEqual("insufficient_data", default_report["status"])
        self.assertIn("snapshots", default_report["missing_requirements"])

    def test_chronological_ai_evaluation_runs_on_synthetic_fixture(self) -> None:
        start = datetime(2026, 7, 15, 10, 0, tzinfo=KST)
        observations = []
        for segment_index in range(2):
            for index in range(50):
                observed_at = (start + timedelta(minutes=10 * index)).isoformat(
                    timespec="seconds"
                )
                observations.append(
                    TrafficObservation(
                        source="synthetic_test",
                        observed_at_kst=observed_at,
                        segment_id=f"segment-{segment_index}",
                        source_url="fixture://synthetic",
                        source_hash=f"fixture-{index}",
                        row_order=segment_index + 1,
                        speed_kmh=25 + segment_index * 3 + (index % 12),
                        zone=segment_index + 1,
                    )
                )
        insert_observations(self.connection, observations)
        model_path = Path(self.temp.name) / "model.joblib"
        report = evaluate_forecast_models(
            self.connection,
            source="synthetic_test",
            min_snapshots=20,
            min_span_hours=3,
            min_examples=20,
            min_distinct_dates=1,
            model_output=model_path,
        )
        self.assertEqual("evaluated", report["status"])
        self.assertEqual("chronological_80_20_by_target_timestamp", report["split"]["method"])
        self.assertGreater(report["split"]["train_rows"], 0)
        self.assertGreater(report["split"]["test_rows"], 0)
        self.assertTrue(model_path.exists())
        self.assertIn("persistence_baseline", report["metrics"])
        self.assertIn("hist_gradient_boosting", report["metrics"])
