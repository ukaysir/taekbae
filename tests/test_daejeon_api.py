from __future__ import annotations

import unittest
import urllib.parse
from unittest.mock import MagicMock, patch

from taekbae.sources.daejeon_api import DaejeonApiError, fetch_api_page, parse_api_page


SUCCESS = b"""<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
<body><numOfRows>10</numOfRows><pageNo>1</pageNo><totalCnt>1</totalCnt><items>
<item><linkID>AN3020005700</linkID><roadName>Expo</roadName><speed>30</speed>
<travelT>17</travelT><congestion>1</congestion><startNodeName>A</startNodeName>
<endNodeName>B</endNodeName><udType>1</udType></item></items></body></response>"""

INVALID_KEY = b"""<response><header><resultCode>30</resultCode>
<resultMsg>SERVICE KEY IS NOT REGISTERED ERROR.</resultMsg></header>
<body><totalCnt>1</totalCnt></body></response>"""

CURRENT_SCHEMA = b"""<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg>
<numOfRows>10</numOfRows><pageNo>1</pageNo><totalCnt>1</totalCnt></header>
<body><TRAFFIC-LIST><TRAFFIC><linkID>AN3020005700</linkID><roadName>Expo</roadName>
<speed>31</speed><travelT>16</travelT><congestion>1</congestion>
<startNodeName>A</startNodeName><endNodeName>B</endNodeName><udType>1</udType>
</TRAFFIC></TRAFFIC-LIST></body></response>"""


class DaejeonApiParserTests(unittest.TestCase):
    def test_parses_success_page(self) -> None:
        page = parse_api_page(SUCCESS)
        self.assertEqual(page.total_count, 1)
        self.assertEqual(len(page.observations), 1)
        row = page.observations[0]
        self.assertEqual(row.link_id, "AN3020005700")
        self.assertEqual(row.speed_kmh, 30.0)
        self.assertEqual(row.travel_time_sec, 17.0)

    def test_surfaces_service_error_without_key(self) -> None:
        with self.assertRaises(DaejeonApiError) as context:
            parse_api_page(INVALID_KEY)
        self.assertEqual(context.exception.code, "30")
        self.assertIn("NOT REGISTERED", context.exception.message)

    def test_parses_current_traffic_element_schema(self) -> None:
        page = parse_api_page(CURRENT_SCHEMA)
        self.assertEqual(1, page.total_count)
        self.assertEqual(1, len(page.observations))
        self.assertEqual(31.0, page.observations[0].speed_kmh)

    @patch("taekbae.sources.daejeon_api.urllib.request.urlopen")
    def test_fetch_uses_documented_lowercase_service_key(self, urlopen: MagicMock) -> None:
        response = MagicMock()
        response.read.return_value = CURRENT_SCHEMA
        response.status = 200
        urlopen.return_value.__enter__.return_value = response

        fetch_api_page("abc%2B123", num_rows=10)

        request = urlopen.call_args.args[0]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        self.assertEqual(["abc+123"], query["serviceKey"])
        self.assertNotIn("ServiceKey", query)


if __name__ == "__main__":
    unittest.main()
