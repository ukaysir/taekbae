from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from taekbae.config import KST
from taekbae.finalization import finalize_snapshot
from taekbae.models import TrafficObservation
from taekbae.storage import connect, insert_observations


class FinalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 7, 17, 9, 0, tzinfo=KST)
        self.db_path = self.root / "data/processed/traffic.sqlite"
        self.source_validation = self.root / "outputs/tables/source_validation_runtime.json"
        self.mapping_validation = self.root / "outputs/tables/mapping_validation.json"
        self.mapping_evidence = self.root / "outputs/tables/mapping_evidence_validation.json"
        self.route_input = self.root / "examples/route_sample.csv"
        self._write_preflight_reports()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_json(self, path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def _write_preflight_reports(self) -> None:
        self._write_json(
            self.source_validation,
            {
                "tested_at_kst": self.now.isoformat(),
                "sources": {
                    "daejeon_openapi": {"operational_usable": False},
                    "kma_asos_hourly": {"operational_usable": False},
                    "daejeon_tram_web": {"operational_usable": True},
                    "standard_node_link": {"hash_verified": True},
                    "tram_event_scope_mapping": {"operational_usable": True},
                },
            },
        )
        self._write_json(
            self.mapping_validation,
            {
                "status": "valid",
                "gate_2_status": "passed",
                "scope_evidence_status": "valid",
                "errors": [],
                "verified_high_scope_events": ["event-a", "event-b"],
            },
        )
        self._write_json(
            self.mapping_evidence,
            {
                "status": "valid",
                "errors": [],
                "high_confidence_verified_events": ["event-a", "event-b"],
            },
        )

    def _outputs(self) -> dict[str, Path]:
        return {
            "status_output": self.root / "outputs/tables/finalization_status.json",
            "manifest_output": self.root / "outputs/tables/finalization_manifest.json",
            "readiness_output": self.root / "outputs/tables/final_readiness.json",
            "quality_output": self.root / "outputs/tables/final_quality.json",
            "model_report_output": self.root / "outputs/tables/model_evaluation.json",
            "model_output": self.root / "outputs/models/forecast.joblib",
            "risk_csv_output": self.root / "outputs/api/current_risk.csv",
            "risk_json_output": self.root / "outputs/api/current_risk.json",
            "route_csv_output": self.root / "outputs/api/route_risk.csv",
            "route_json_output": self.root / "outputs/api/route_risk.json",
            "frozen_db_dir": self.root / "data/processed/frozen",
        }

    def _run(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "repo_root": self.root,
            "db_path": self.db_path,
            "source_validation_path": self.source_validation,
            "mapping_validation_path": self.mapping_validation,
            "mapping_evidence_path": self.mapping_evidence,
            "route_input_path": self.route_input,
            "now": self.now,
            **self._outputs(),
        }
        arguments.update(overrides)
        return finalize_snapshot(**arguments)  # type: ignore[arg-type]

    def test_insufficient_data_writes_pending_status_without_freezing(self) -> None:
        connection = connect(self.db_path)
        try:
            start = self.now - timedelta(hours=1)
            observations = []
            for index in range(8):
                observations.append(
                    TrafficObservation(
                        source="djtram_web",
                        observed_at_kst=(start + timedelta(minutes=10 * index)).isoformat(),
                        segment_id="segment-a",
                        source_url="https://example.test",
                        source_hash=f"hash-{index}",
                        row_order=1,
                        speed_kmh=30 + index,
                        zone=1,
                    )
                )
            insert_observations(connection, observations)
        finally:
            connection.close()
        self.route_input.parent.mkdir(parents=True, exist_ok=True)
        self.route_input.write_text(
            "route_id,stop_order,segment_id,planned_at_kst\n"
            "route-1,1,segment-a,2026-07-17T10:00:00+09:00\n",
            encoding="utf-8",
        )

        report = self._run()

        self.assertEqual("pending", report["status"])
        self.assertFalse(report["finalized"])
        self.assertFalse(report["frozen_database_created"])
        self.assertIn("readiness:snapshots", report["preflight"]["blockers"])
        self.assertFalse(self._outputs()["manifest_output"].exists())
        self.assertFalse(self._outputs()["model_report_output"].exists())
        self.assertFalse(self._outputs()["frozen_db_dir"].exists())

    def test_invalid_mapping_is_blocked_even_when_data_is_short(self) -> None:
        connection = connect(self.db_path)
        connection.close()
        self.route_input.parent.mkdir(parents=True, exist_ok=True)
        self.route_input.write_text(
            "route_id,stop_order,segment_id,planned_at_kst\n"
            "route-1,1,segment-a,2026-07-17T10:00:00+09:00\n",
            encoding="utf-8",
        )
        mapping = json.loads(self.mapping_validation.read_text(encoding="utf-8"))
        mapping["gate_2_status"] = "partial"
        self._write_json(self.mapping_validation, mapping)

        report = self._run()

        self.assertEqual("blocked", report["status"])
        self.assertIn("mapping_gate_2_not_passed", report["preflight"]["blockers"])
        self.assertFalse(report["frozen_database_created"])

    def test_ready_data_freezes_evaluates_and_hashes_artifacts(self) -> None:
        connection = connect(self.db_path)
        try:
            start = self.now - timedelta(hours=9)
            observations = []
            for segment_index in range(2):
                for index in range(50):
                    observations.append(
                        TrafficObservation(
                            source="djtram_web",
                            observed_at_kst=(start + timedelta(minutes=10 * index)).isoformat(),
                            segment_id=f"segment-{segment_index}",
                            source_url="https://example.test",
                            source_hash=f"hash-{index}",
                            row_order=segment_index + 1,
                            speed_kmh=25 + segment_index * 3 + (index % 12),
                            zone=segment_index + 1,
                            segment_label=f"구간 {segment_index}",
                            traffic_state="원활",
                        )
                    )
            insert_observations(connection, observations)
        finally:
            connection.close()
        self.route_input.parent.mkdir(parents=True, exist_ok=True)
        self.route_input.write_text(
            "route_id,stop_order,segment_id,planned_at_kst\n"
            "route-1,1,segment-0,2026-07-17T10:00:00+09:00\n"
            "route-1,2,segment-1,2026-07-17T10:10:00+09:00\n",
            encoding="utf-8",
        )

        report = self._run(
            min_snapshots=20,
            min_span_hours=3.0,
            min_examples=20,
            min_distinct_dates=1,
        )

        self.assertTrue(report["finalized"])
        self.assertIn(
            report["status"],
            {"finalized_ai_candidate_validated", "finalized_observation_only"},
        )
        self.assertEqual(2, report["route_records"])
        self.assertEqual(2, report["route_matched"])
        self.assertFalse(report["prediction_fields_active"])

        outputs = self._outputs()
        manifest = json.loads(outputs["manifest_output"].read_text(encoding="utf-8"))
        self.assertEqual("ok", manifest["frozen_database_integrity"])
        self.assertEqual(0, manifest["route_contract"]["unmatched"])
        self.assertGreater(len(manifest["artifacts"]), 10)
        for artifact in manifest["artifacts"]:
            path = self.root / artifact["path"]
            self.assertTrue(path.is_file(), artifact["path"])
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(artifact["sha256"], actual)

        model_report = json.loads(outputs["model_report_output"].read_text(encoding="utf-8"))
        self.assertEqual("outputs/models/forecast.joblib", model_report["model_output"])
        risk_payload = json.loads(outputs["risk_json_output"].read_text(encoding="utf-8"))
        self.assertTrue(
            all(row["model_status"] == "ready_for_evaluation" for row in risk_payload["records"])
        )
        self.assertTrue(
            all(row["predicted_travel_time_sec"] is None for row in risk_payload["records"])
        )
