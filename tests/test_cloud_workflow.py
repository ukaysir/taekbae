from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "collect-djtram.yml"


class CloudCollectionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_collects_only_public_tram_source_without_secret_injection(self) -> None:
        self.assertIn("collect-djtram --zones 1,12", self.workflow)
        self.assertNotIn("DATA_GO_KR_SERVICE_KEY", self.workflow)
        self.assertNotIn(".private", self.workflow)

    def test_preserves_latest_and_previous_release_assets(self) -> None:
        self.assertIn("collector-state.tar.gz", self.workflow)
        self.assertIn("collector-state.previous.tar.gz", self.workflow)
        self.assertIn("--clobber", self.workflow)

    def test_has_bounded_collection_window_and_serial_execution(self) -> None:
        self.assertIn('COLLECTION_END_AT: "2026-07-21T04:00:00Z"', self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)
        self.assertIn("gh workflow disable collect-djtram.yml", self.workflow)


if __name__ == "__main__":
    unittest.main()
