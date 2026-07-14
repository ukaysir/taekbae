from __future__ import annotations

import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from taekbae.mapping_evidence import validate_mapping_evidence


class MappingEvidenceTests(unittest.TestCase):
    def test_validates_official_text_and_asset_hash(self) -> None:
        png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 1125, 1125)
        expected_hash = hashlib.sha256(png).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence.csv"
            evidence.write_text(
                "evidence_id,event_id,evidence_type,source_url,asset_url,expected_sha256,expected_text,road_name,place_name,confidence,checked_at_kst,interpretation\n"
                f"x1,e1,official_map,https://example.test/page,https://example.test/map.png,{expected_hash},계족로 통제,계족로,읍내삼거리,high,2026-07-15T00:00:00+09:00,fixture\n",
                encoding="utf-8",
            )

            def fetcher(url: str) -> tuple[int, bytes, str]:
                if url.endswith("map.png"):
                    return 200, png, "image/png"
                return 200, "<p>계족로   통제</p>".encode(), "text/html"

            report = validate_mapping_evidence(evidence, fetcher=fetcher)
        self.assertEqual("valid", report["status"])
        self.assertEqual(["e1"], report["high_confidence_verified_events"])
        self.assertEqual(1125, report["results"][0]["asset_width"])

    def test_rejects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence.csv"
            evidence.write_text(
                "evidence_id,event_id,evidence_type,source_url,asset_url,expected_sha256,expected_text,road_name,place_name,confidence,checked_at_kst,interpretation\n"
                "x1,e1,official_map,https://example.test/page,https://example.test/map.png,deadbeef,,계족로,읍내삼거리,high,2026-07-15T00:00:00+09:00,fixture\n",
                encoding="utf-8",
            )

            def fetcher(url: str) -> tuple[int, bytes, str]:
                return 200, b"different", "image/png" if url.endswith(".png") else "text/html"

            report = validate_mapping_evidence(evidence, fetcher=fetcher)
        self.assertEqual("invalid", report["status"])
        self.assertIn("asset_hash_mismatch", report["results"][0]["errors"])
