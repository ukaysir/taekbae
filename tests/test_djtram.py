from __future__ import annotations

import unittest
from datetime import datetime

from taekbae.config import KST
from taekbae.sources.djtram import DjTramParseError, parse_zone_page


SAMPLE = """
<html><body>
<div class="swiper-slide"><p class="txt">계족로 상행(읍내삼거리 에서 대한통운)</p>
<span class="tag-smoothly"><i>원활 39km</i></span></div>
<div class="swiper-slide"><p class="txt">계족로 상행(읍내삼거리 에서 대한통운)</p>
<span class="tag-retard"><i>지체 17km</i></span></div>
</body></html>
""".encode()


class DjTramParserTests(unittest.TestCase):
    def test_parses_rows_and_duplicate_identity(self) -> None:
        page = parse_zone_page(
            SAMPLE,
            zone=1,
            observed_at=datetime(2026, 7, 14, 12, 0, tzinfo=KST),
        )
        self.assertEqual(len(page.observations), 2)
        self.assertEqual(page.duplicate_label_count, 1)
        first, second = page.observations
        self.assertNotEqual(first.segment_id, second.segment_id)
        self.assertEqual(first.road_name, "계족로")
        self.assertEqual(first.direction, "상행")
        self.assertEqual(first.start_name, "읍내삼거리")
        self.assertEqual(first.end_name, "대한통운")
        self.assertEqual(first.speed_kmh, 39.0)
        self.assertEqual(second.traffic_state, "지체")

    def test_rejects_page_without_rows(self) -> None:
        with self.assertRaises(DjTramParseError):
            parse_zone_page(b"<html></html>", zone=1)

    def test_rejects_invalid_zone(self) -> None:
        with self.assertRaises(ValueError):
            parse_zone_page(SAMPLE, zone=15)


if __name__ == "__main__":
    unittest.main()
