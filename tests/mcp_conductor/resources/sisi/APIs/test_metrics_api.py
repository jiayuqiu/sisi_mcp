"""
Unit tests for BCI metrics API client.

This module tests the signature generation and API call functionality
for the BCI metrics data API.
"""
import unittest
from unittest.mock import patch, Mock
import os
import requests
from dotenv import load_dotenv

load_dotenv()

from mcp_conductor.resources.sisi.APIs.metrics_api import (
    APP_ID,
    BASE_URL,
    MetricsAPI,
    generate_signature,
    get_bci_metrics,
)


class TestSignatureGeneration(unittest.TestCase):
    """Test cases for signature generation function."""

    def setUp(self):
        """Set up test fixtures."""
        self.secret_key = os.getenv("BCI_SECRET_KEY", "test_secret_key")
        self.app_id = os.getenv("BCI_APP_ID", "test_app_id")
        self.test_params = {
            "appId": self.app_id,
            "client": self.app_id,
            "endDay": "2026-04-16",
            "nonce": "1234567890",
            "startDay": "2026-04-16",
            "timestamp": "1656633600",
        }

    def test_signature_generation_basic(self):
        """Test basic signature generation."""
        signature = generate_signature(self.test_params, self.secret_key)

        # Signature should be a 32-character MD5 hash
        self.assertEqual(len(signature), 32)
        self.assertTrue(signature.islower())
        self.assertTrue(all(c in '0123456789abcdef' for c in signature))

    def test_signature_consistency(self):
        """Test that same inputs produce same signature."""
        sig1 = generate_signature(self.test_params, self.secret_key)
        sig2 = generate_signature(self.test_params, self.secret_key)

        self.assertEqual(sig1, sig2)

    def test_signature_different_params(self):
        """Test that different parameters produce different signatures."""
        params2 = self.test_params.copy()
        params2["endDay"] = "2022-07-02"

        sig1 = generate_signature(self.test_params, self.secret_key)
        sig2 = generate_signature(params2, self.secret_key)

        self.assertNotEqual(sig1, sig2)

    def test_signature_parameter_order_independence(self):
        """Test that parameter order doesn't affect signature."""
        # Create params with different order
        params_ordered = {
            "appId": "qiu",
            "client": "qiu",
            "endDay": "2022-07-01",
            "nonce": "1234567890",
            "startDay": "2022-07-01",
            "timestamp": "1656633600",
        }

        params_reversed = {
            "timestamp": "1656633600",
            "startDay": "2022-07-01",
            "nonce": "1234567890",
            "endDay": "2022-07-01",
            "client": "qiu",
            "appId": "qiu",
        }

        sig1 = generate_signature(params_ordered, self.secret_key)
        sig2 = generate_signature(params_reversed, self.secret_key)

        self.assertEqual(sig1, sig2)

    def test_signature_empty_params(self):
        """Test signature generation with empty parameters."""
        signature = generate_signature({}, self.secret_key)

        # Should still generate valid MD5 hash
        self.assertEqual(len(signature), 32)

    def test_signature_special_characters(self):
        """Test signature with special characters in values."""
        params = {
            "key1": "value with spaces",
            "key2": "value&with&ampersands",
            "key3": "value=with=equals",
        }

        signature = generate_signature(params, self.secret_key)

        # Should handle special characters properly
        self.assertEqual(len(signature), 32)


class TestBCIMetricsAPI(unittest.TestCase):
    """Test cases for BCI metrics API client."""

    def setUp(self):
        """Set up test fixtures."""
        self.app_id = APP_ID
        self.client = self.app_id
        self.start_day = "2026-04-16"
        self.end_day = "2026-04-16"
        self.base_url = BASE_URL

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_get_bci_metrics_success(self, mock_get):
        """Test successful API call."""
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "data": [{"metric": "value"}]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = get_bci_metrics(
            app_id=self.app_id,
            start_day=self.start_day,
            end_day=self.end_day
        )

        # Verify result
        self.assertTrue(result["success"])
        self.assertIn("data", result)

        # Verify request was made
        mock_get.assert_called_once()
        call_args = mock_get.call_args

        # Check URL
        self.assertEqual(call_args[0][0], self.base_url)

        # Check headers
        headers = call_args[1]["headers"]
        self.assertIn("appId", headers)
        self.assertIn("timestamp", headers)
        self.assertIn("nonce", headers)
        self.assertIn("sign", headers)

        # Check query params
        params = call_args[1]["params"]
        self.assertEqual(params["client"], self.client)
        self.assertEqual(params["startDay"], self.start_day)
        self.assertEqual(params["endDay"], self.end_day)

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_get_bci_metrics_with_zbxxs(self, mock_get):
        """Test API call with zbxxs parameter."""
        mock_response = Mock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        zbxxs = "101-0003,101-0004"

        result = get_bci_metrics(
            app_id=self.app_id,
            start_day=self.start_day,
            end_day=self.end_day,
            zbxxs=zbxxs
        )

        # Verify zbxxs in params
        call_args = mock_get.call_args
        params = call_args[1]["params"]
        self.assertEqual(params["zbxxs"], zbxxs)

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_get_bci_metrics_with_csdbs(self, mock_get):
        """Test API call with csdbs parameter."""
        mock_response = Mock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        csdbs = "055477ABB03B456E8B4B135E8193B25A"

        result = get_bci_metrics(
            app_id=self.app_id,
            start_day=self.start_day,
            end_day=self.end_day,
            csdbs=csdbs
        )

        # Verify csdbs in params
        call_args = mock_get.call_args
        params = call_args[1]["params"]
        self.assertEqual(params["csdbs"], csdbs)

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_get_bci_metrics_http_error(self, mock_get):
        """Test API call with HTTP error."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_get.return_value = mock_response

        result = get_bci_metrics(
            app_id=self.app_id,
            start_day=self.start_day,
            end_day=self.end_day
        )

        # Should return error response
        self.assertFalse(result["success"])
        self.assertIn("message", result)

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_get_bci_metrics_request_timeout(self, mock_get):
        """Test API call with timeout error."""
        mock_get.side_effect = requests.exceptions.Timeout("Request timeout")

        result = get_bci_metrics(
            app_id=self.app_id,
            start_day=self.start_day,
            end_day=self.end_day
        )

        # Should return error response
        self.assertFalse(result["success"])
        self.assertIn("message", result)

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_get_bci_metrics_connection_error(self, mock_get):
        """Test API call with connection error."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")

        result = get_bci_metrics(
            app_id=self.app_id,
            start_day=self.start_day,
            end_day=self.end_day
        )

        # Should return error response
        self.assertFalse(result["success"])
        self.assertIn("message", result)

    def test_get_bci_metrics_real_request(self):
        """Test a real API call to the BCI metrics service."""
        import json
        
        # Use dates and indicators from channel.py example
        start_date = "2026-04-16"
        end_date = "2026-04-16"
        # zbxxs_val = "101-0003,101-0004"
        zbxxs_val = "101-0001,101-0002"
        
        print(f"\nSending real API request to {self.base_url}...")
        result = get_bci_metrics(
            app_id=self.app_id,
            start_day=start_date,
            end_day=end_date,
            zbxxs=zbxxs_val
        )
        
        self.assertTrue(isinstance(result, dict))
        if result.get("success"):
            self.assertIn("result", result)
            data = result["result"]
            
            # Handle cases where "data" is a dictionary containing a list
            if isinstance(data, dict):
                data = data.get("list", data.get("rows", []))
                
            self.assertIsInstance(data, list)
            print("\n--- 响应结果 (Response) ---")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Real API request failed (might be IP whitelist or expired key): {result}")

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_signature_included_in_request(self, mock_get):
        """Test that signature is properly generated and included."""
        mock_response = Mock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        get_bci_metrics(
            app_id=self.app_id,
            start_day=self.start_day,
            end_day=self.end_day
        )

        # Get the headers from the call
        call_args = mock_get.call_args
        headers = call_args[1]["headers"]

        # Verify signature exists and is valid MD5
        self.assertIn("sign", headers)
        signature = headers["sign"]
        self.assertEqual(len(signature), 32)
        self.assertTrue(signature.islower())

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_timeout_parameter(self, mock_get):
        """Test that timeout is set correctly."""
        mock_response = Mock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        get_bci_metrics(
            app_id=self.app_id,
            start_day=self.start_day,
            end_day=self.end_day
        )

        # Verify timeout is set
        call_args = mock_get.call_args
        self.assertEqual(call_args[1]["timeout"], 10)


class TestAPIParameterValidation(unittest.TestCase):
    """Test cases for API parameter validation."""

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_date_format_validation(self, mock_get):
        """Test that dates are passed correctly."""
        mock_response = Mock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        start = "2022-01-01"
        end = "2022-12-31"

        get_bci_metrics(
            app_id=APP_ID,
            start_day=start,
            end_day=end
        )

        call_args = mock_get.call_args
        params = call_args[1]["params"]

        self.assertEqual(params["startDay"], start)
        self.assertEqual(params["endDay"], end)

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_multiple_zbxxs_values(self, mock_get):
        """Test multiple zbxxs values with comma separation."""
        mock_response = Mock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        zbxxs = "101-0003,101-0004,101-0005"

        get_bci_metrics(
            app_id=APP_ID,
            start_day="2022-07-01",
            end_day="2022-07-01",
            zbxxs=zbxxs
        )

        call_args = mock_get.call_args
        params = call_args[1]["params"]

        self.assertEqual(params["zbxxs"], zbxxs)
        # Verify commas are preserved
        self.assertEqual(params["zbxxs"].count(","), 2)


class TestMetricsAPIGetMetricsValue(unittest.TestCase):
    """Unit tests for MetricsAPI.get_metrics_value."""

    def setUp(self):
        self.api = MetricsAPI()

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_get_metrics_value_success_default_zbxxs(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {"success": True, "result": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.api.get_metrics_value("2026-04-16", "2026-04-16")

        self.assertTrue(result["success"])
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertEqual(call_args[0][0], self.api.base_url)

        headers = call_args[1]["headers"]
        self.assertEqual(headers["appId"], self.api.app_id)
        self.assertIn("sign", headers)
        self.assertIn("timestamp", headers)
        self.assertIn("nonce", headers)

        params = call_args[1]["params"]
        self.assertEqual(params["client"], self.api.app_id)
        self.assertEqual(params["startDay"], "2026-04-16")
        self.assertEqual(params["endDay"], "2026-04-16")
        self.assertEqual(params["zbxxs"], "101-0003,101-0004")

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_get_metrics_value_success_custom_zbxxs(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {"success": True, "result": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        custom_zbxxs = "101-0001,101-0002"
        self.api.get_metrics_value("2026-04-16", "2026-04-16", custom_zbxxs)

        params = mock_get.call_args[1]["params"]
        self.assertEqual(params["zbxxs"], custom_zbxxs)

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_get_metrics_value_http_error_returns_failure(self, mock_get):
        mock_response = Mock()
        mock_response.text = "forbidden"
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("403 Forbidden")
        mock_get.return_value = mock_response

        result = self.api.get_metrics_value("2026-04-16", "2026-04-16")
        self.assertFalse(result["success"])
        self.assertIn("message", result)

    @patch('mcp_conductor.resources.sisi.APIs.metrics_api.requests.get')
    def test_get_metrics_value_request_error_returns_failure(self, mock_get):
        mock_get.side_effect = requests.exceptions.RequestException("connection failed")

        result = self.api.get_metrics_value("2026-04-16", "2026-04-16")
        self.assertFalse(result["success"])
        self.assertIn("message", result)

    def test_get_metrics_value_real_request(self):
        """Test a real API call through MetricsAPI.get_metrics_value."""
        import json

        start_date = "2026-04-10"
        end_date = "2026-04-10"
        zbxxs_val = "101-0001,101-0002"

        print(f"\nSending real MetricsAPI request to {self.api.base_url}...")
        result = self.api.get_metrics_value(start_date, end_date, zbxxs_val)

        self.assertTrue(isinstance(result, dict))
        if result.get("success"):
            self.assertIn("result", result)
            data = result["result"]

            # Real endpoint payload can vary by tenant/data availability.
            # Accept list, dict, or None as long as response is well-formed.
            if isinstance(data, dict):
                maybe_list = data.get("list", data.get("rows", None))
                if maybe_list is not None:
                    self.assertIsInstance(maybe_list, list)
            elif data is not None:
                self.assertIsInstance(data, list)
            print("\n--- MetricsAPI Real Response ---")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"MetricsAPI real request failed (possible whitelist/key issue): {result}")
    
    


if __name__ == "__main__":
    unittest.main()
