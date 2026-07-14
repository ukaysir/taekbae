from __future__ import annotations

import json
import unittest

from taekbae.sources.kma import KmaApiError, parse_weather_page


class KmaParserTests(unittest.TestCase):
    def test_parses_hourly_weather_json(self) -> None:
        raw = json.dumps(
            {
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                    "body": {
                        "pageNo": 1,
                        "numOfRows": 10,
                        "totalCount": 1,
                        "items": {
                            "item": [
                                {
                                    "tm": "2026-07-14 10:00",
                                    "stnId": "133",
                                    "stnNm": "대전",
                                    "ta": "25.1",
                                    "rn": "",
                                    "ws": "1.2",
                                    "hm": "71",
                                }
                            ]
                        },
                    },
                }
            },
            ensure_ascii=False,
        ).encode("utf-8")
        page = parse_weather_page(raw)
        self.assertEqual(1, page.total_count)
        self.assertEqual(1, len(page.observations))
        observation = page.observations[0]
        self.assertEqual(133, observation.station_id)
        self.assertEqual("대전", observation.station_name)
        self.assertEqual(25.1, observation.temperature_c)
        self.assertIsNone(observation.rainfall_mm)

    def test_surfaces_json_service_error(self) -> None:
        raw = b'{"response":{"header":{"resultCode":"30","resultMsg":"KEY ERROR"}}}'
        with self.assertRaises(KmaApiError) as context:
            parse_weather_page(raw)
        self.assertEqual("30", context.exception.code)

    def test_surfaces_xml_service_error(self) -> None:
        raw = b"<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>AUTH ERROR</errMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"
        with self.assertRaises(KmaApiError) as context:
            parse_weather_page(raw)
        self.assertEqual("30", context.exception.code)
