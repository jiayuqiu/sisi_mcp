import json
import requests
import unittest
from unittest.mock import patch

from mcp_conductor.resources.sisi.APIs import canal_traffic


class MockResponse:
    def __init__(self, json_data, status_code=200, text=None):
        self._json = json_data
        self.status_code = status_code
        self.text = text if text is not None else json.dumps(json_data)

    def json(self):
        return self._json

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


class TestCanalTraffic(unittest.TestCase):
    def test_generate_signature_format_and_hex(self):
        params = {
            "appId": "qiu",
            "client": "clientA",
            "endDay": "2022-07-01",
            "nonce": "1234567890",
            "startDay": "2022-07-01",
            "timestamp": "1656633600",
        }

        sign = canal_traffic.generate_signature(params, canal_traffic.SECRET_KEY)

        self.assertIsInstance(sign, str)
        self.assertEqual(len(sign), 32)
        self.assertTrue(all(c in "0123456789abcdef" for c in sign))

    @patch("mcp_conductor.resources.sisi.APIs.canal_traffic.requests.get")
    def test_get_bci_metrics_success(self, mock_get):
        expected = {"success": True, "data": [{"id": 1}]}
        mock_get.return_value = MockResponse(expected, status_code=200)

        resp = canal_traffic.get_bci_metrics(
            client="clientA", start_day="2022-07-01", end_day="2022-07-01"
        )

        self.assertEqual(resp, expected)
        mock_get.assert_called_once()
        _, call_kwargs = mock_get.call_args
        self.assertEqual(call_kwargs["headers"].get("appId"), canal_traffic.APP_ID)
        self.assertIn("timestamp", call_kwargs["headers"])
        self.assertIn("nonce", call_kwargs["headers"])
        self.assertIn("sign", call_kwargs["headers"])
        self.assertEqual(call_kwargs["params"]["client"], "clientA")

    @patch("mcp_conductor.resources.sisi.APIs.canal_traffic.requests.get")
    def test_get_bci_metrics_with_optional_params(self, mock_get):
        expected = {"success": True, "data": []}
        mock_get.return_value = MockResponse(expected, status_code=200)

        resp = canal_traffic.get_bci_metrics(
            client="clientB",
            start_day="2022-07-01",
            end_day="2022-07-01",
            zbxxs="101-0003,101-0004",
            csdbs="CID",
        )

        self.assertEqual(resp, expected)
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["zbxxs"], "101-0003,101-0004")
        self.assertEqual(params["csdbs"], "CID")

    @patch("mcp_conductor.resources.sisi.APIs.canal_traffic.requests.get")
    def test_get_bci_metrics_http_error_returns_failure(self, mock_get):
        mock_get.return_value = MockResponse({"error": "srv"}, status_code=500)

        resp = canal_traffic.get_bci_metrics(
            client="clientC", start_day="2022-07-01", end_day="2022-07-01"
        )

        self.assertIsInstance(resp, dict)
        self.assertFalse(resp.get("success"))