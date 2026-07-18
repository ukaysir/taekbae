from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "restore_cloud_state.ps1"


class CloudRestoreScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_refuses_to_restore_over_running_local_processes(self) -> None:
        self.assertIn("collector.pid", self.script)
        self.assertIn("dashboard.pid", self.script)
        self.assertIn("Refusing to restore", self.script)

    def test_verifies_release_digest_and_preserves_existing_state(self) -> None:
        self.assertIn("Get-FileHash", self.script)
        self.assertIn("SHA-256 mismatch", self.script)
        self.assertIn("backupDir", self.script)
        self.assertIn("Copy-Item", self.script)
        self.assertNotIn("Remove-Item", self.script)

    def test_restores_only_collector_data_and_flags_external_assets(self) -> None:
        self.assertIn("data\\raw\\djtram_web", self.script)
        self.assertIn("data\\processed\\traffic.sqlite", self.script)
        self.assertIn("NODELINKDATA_2024-11-29.zip", self.script)
        self.assertIn("sbiz_stores_daejeon_202603.csv", self.script)


if __name__ == "__main__":
    unittest.main()
