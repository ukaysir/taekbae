from __future__ import annotations

import unittest
import ssl
import urllib.request
from datetime import datetime
from unittest.mock import MagicMock, patch

from taekbae.config import KST
from taekbae.sources.djtram import (
    DjTramParseError,
    _open_tram_request,
    fetch_zone,
    parse_zone_page,
)


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

    def test_fetch_uses_verified_legacy_key_context_for_official_host(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = SAMPLE
        response.status = 200

        with patch(
            "taekbae.sources.djtram.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            page = fetch_zone(1)

        self.assertEqual(2, len(page.observations))
        self.assertEqual(1, urlopen.call_count)
        context = urlopen.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(ssl.CERT_REQUIRED, context.verify_mode)

    def test_non_official_host_uses_default_tls_settings(self) -> None:
        request = urllib.request.Request("https://example.com/")
        response = MagicMock()
        with patch(
            "taekbae.sources.djtram.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            returned = _open_tram_request(request, timeout=7)

        self.assertIs(response, returned)
        self.assertEqual(1, urlopen.call_count)
        urlopen.assert_called_once_with(request, timeout=7)


if __name__ == "__main__":
    unittest.main()
