from __future__ import annotations

import zipfile
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter
from reportlab.pdfgen import canvas

from taekbae.submission import (
    FILE_SPECS,
    HWP_MAGIC,
    create_submission_zip,
    validate_submission_manifest,
)


def _pdf(path: Path, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    with path.open("wb") as handle:
        writer.write(handle)


def _text_pdf(path: Path, text: str) -> None:
    document = canvas.Canvas(str(path), pagesize=(595, 842))
    document.drawString(72, 780, text)
    document.save()


def _valid_manifest(root: Path) -> dict[str, object]:
    files = {
        "application": root / "application.pdf",
        "proposal_hwp": root / "proposal.hwp",
        "proposal_pdf": root / "proposal.pdf",
        "analysis_hwp": root / "analysis.hwp",
        "analysis_pdf": root / "analysis.pdf",
        "consent_pledge_pdf": root / "consent.pdf",
        "reviewer_draw_pdf": root / "draw.pdf",
    }
    _pdf(files["application"], 1)
    _pdf(files["proposal_pdf"], 8)
    _pdf(files["analysis_pdf"], 3)
    _pdf(files["consent_pledge_pdf"], 2)
    _pdf(files["reviewer_draw_pdf"], 1)
    files["proposal_hwp"].write_bytes(HWP_MAGIC + b"proposal")
    files["analysis_hwp"].write_bytes(HWP_MAGIC + b"analysis")
    return {
        "team_name": "물류연결팀",
        "files": {role: str(path) for role, path in files.items()},
        "confirmations": {
            "participant_eligibility_confirmed": True,
            "latest_notice_checked": True,
            "organizer_rights_clause_clarified": True,
            "originality_and_source_rights_confirmed": True,
            "hwp_pdf_content_matched": True,
            "all_required_signatures_present": True,
            "exactly_seven_draw_numbers_marked": True,
        },
    }


class SubmissionPackageTests(unittest.TestCase):
    def test_draft_mark_in_pdf_blocks_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            manifest = _valid_manifest(root)
            _text_pdf(Path(manifest["files"]["proposal_pdf"]), "DRAFT review copy")
            report = validate_submission_manifest(manifest, base_dir=root)
            self.assertEqual(report["status"], "invalid")
            self.assertTrue(
                any("draft_mark" in error for error in report["errors"])
            )

    def test_missing_confirmations_block_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            manifest = _valid_manifest(root)
            manifest["confirmations"] = {}
            report = validate_submission_manifest(manifest, base_dir=root)
            self.assertEqual(report["status"], "invalid")
            self.assertTrue(
                any("confirmation missing" in error for error in report["errors"])
            )

    def test_secret_value_in_file_blocks_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            manifest = _valid_manifest(root)
            secret = "not-a-real-secret-value"
            proposal = Path(manifest["files"]["proposal_hwp"])
            proposal.write_bytes(proposal.read_bytes() + secret.encode())
            report = validate_submission_manifest(
                manifest, base_dir=root, service_key=secret
            )
            self.assertEqual(report["status"], "invalid")
            self.assertEqual(report["credential_hits"], 1)
            self.assertTrue(
                any("credential value found" in error for error in report["errors"])
            )

    def test_proposal_over_ten_pages_blocks_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            manifest = _valid_manifest(root)
            _pdf(Path(manifest["files"]["proposal_pdf"]), 11)
            report = validate_submission_manifest(manifest, base_dir=root)
            self.assertEqual(report["status"], "invalid")
            self.assertTrue(
                any("1-10 pages" in error for error in report["errors"])
            )

    def test_valid_manifest_builds_flat_official_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            manifest = _valid_manifest(root)
            report = validate_submission_manifest(manifest, base_dir=root)
            self.assertEqual(report["status"], "valid")
            output, errors = create_submission_zip(report, output_dir=root / "out")
            self.assertEqual(errors, [])
            self.assertIsNotNone(output)
            assert output is not None
            self.assertEqual(output.name, "[공모전_물류연결팀].zip")
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(len(archive.namelist()), len(FILE_SPECS))
                self.assertTrue(all("/" not in name for name in archive.namelist()))
                self.assertIn("2. 제안서.hwp", archive.namelist())
                self.assertIn("3. 분석 과정 보고서.pdf", archive.namelist())


if __name__ == "__main__":
    unittest.main()
