from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "render_submission.py"
SPEC = importlib.util.spec_from_file_location("render_submission", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
render_submission = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_submission)


class RenderSubmissionTests(unittest.TestCase):
    def test_pdf_command_disables_headers_on_legacy_and_current_edge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            html = root / "document.html"
            target = root / "document.pdf"
            profile = root / "edge-profile"
            html.write_text("<html><body>test</body></html>", encoding="utf-8")
            target.write_bytes(b"%PDF-placeholder")

            completed = SimpleNamespace(returncode=0, stdout="", stderr="")
            with (
                patch.object(
                    render_submission, "edge_path", return_value=Path("msedge.exe")
                ),
                patch.object(
                    render_submission.subprocess, "run", return_value=completed
                ) as run,
            ):
                render_submission.print_pdf(html, target, profile)

            command = run.call_args.args[0]
            self.assertIn("--print-to-pdf-no-header", command)
            self.assertIn("--no-pdf-header-footer", command)


if __name__ == "__main__":
    unittest.main()
