"""
Unit tests for BCI metrics API client.

This module tests the signature generation and API call functionality
for the BCI metrics data API.
"""
import unittest
from unittest.mock import patch, Mock
from typing import Optional
import hashlib
import time
import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the functions to test (assuming they're in a module called data_api)
# For now, we'll define them here for testing purposes

def generate_signature(params_to_sign: dict, secret_key: str) -> str:
    """
    Generate API signature according to documentation.

    Args:
        params_to_sign: Dictionary of parameters to sign
        secret_key: Secret key for signing

    Returns:
        MD5 signature in lowercase
    """
    # Sort parameters by ASCII code
    sorted_params = sorted(params_to_sign.items())

    # Create stringA: key1=value1&key2=value2...
    string_a_parts = [f"{key}={value}" for key, value in sorted_params]
    string_a = "&".join(string_a_parts)

    # Append secret key: stringA + "&key=" + secret_key
    string_sign_temp = f"{string_a}&key={secret_key}"

    # Generate MD5 and convert to lowercase
    sign = hashlib.md5(string_sign_temp.encode('utf-8')).hexdigest().lower()

    return sign


def get_bci_metrics(
    client: str,
    start_day: str,
    end_day: str,
    zbxxs: Optional[str] = None,
    csdbs: Optional[str] = None,
    app_id: Optional[str] = None,
    secret_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> dict:
    """
    Call the BCI metrics API (getZbcsdb).

    Args:
        client: Third-party identifier
        start_day: Query start date (YYYY-MM-DD)
        end_day: Query end date (YYYY-MM-DD)
        zbxxs: Metric information, comma-separated (optional)
        csdbs: CSDB information, comma-separated (optional)
        app_id: Platform-issued appId (defaults to env var BCI_APP_ID)
        secret_key: Platform-issued secret key (defaults to env var BCI_SECRET_KEY)
        base_url: API base URL (defaults to env var BCI_BASE_URL)

    Returns:
        API response as dictionary
    """
    # Load credentials from environment if not provided
    if app_id is None:
        app_id = os.getenv("BCI_APP_ID", "")
    if secret_key is None:
        secret_key = os.getenv("BCI_SECRET_KEY", "")
    if base_url is None:
        base_url = os.getenv("BCI_BASE_URL", "http://101.132.25.38:8891/bci/openapi/zbcsdb/getZbcsdb")

    # Prepare query parameters
    query_params = {
        "client": client,
        "startDay": start_day,
        "endDay": end_day,
    }

    # Add optional parameters
    if zbxxs:
        query_params["zbxxs"] = zbxxs
    if csdbs:
        query_params["csdbs"] = csdbs

    # Prepare header parameters
    timestamp = str(int(time.time()))
    import random
    nonce = str(random.randint(1000000000, 9999999999))

    # Prepare signature parameters (zbxxs and csdbs not included in signature)
    params_to_sign = {
        "appId": app_id,
        "client": client,
        "endDay": end_day,
        "nonce": nonce,
        "startDay": start_day,
        "timestamp": timestamp,
    }

    # Generate signature
    sign = generate_signature(params_to_sign, secret_key)

    # Prepare request headers
    headers = {
        "appId": app_id,
        "timestamp": timestamp,
        "nonce": nonce,
        "sign": sign,
        "Content-Type": "application/json;charset=UTF-8"
    }

    # Send GET request
    try:
        response = requests.get(
            base_url,
            headers=headers,
            params=query_params,
            timeout=10
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.HTTPError as http_err:
        return {"success": False, "message": f"HTTP error: {http_err}"}
    except requests.exceptions.RequestException as req_err:
        return {"success": False, "message": f"Request error: {req_err}"}


class TestSignatureGeneration(unittest.TestCase):
    """Test cases for signature generation function."""

    def setUp(self):
        """Set up test fixtures."""
        self.secret_key = os.getenv("BCI_SECRET_KEY", "test_secret_key")
        self.app_id = os.getenv("BCI_APP_ID", "test_app_id")
        self.test_params = {
            "appId": self.app_id,
            "client": self.app_id,
            "endDay": "2022-07-01",
            "nonce": "1234567890",
            "startDay": "2022-07-01",
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
        self.app_id = os.getenv("BCI_APP_ID", "test_app_id")
        self.client = self.app_id
        self.start_day = "2022-07-01"
        self.end_day = "2022-07-01"
        self.secret_key = os.getenv("BCI_SECRET_KEY", "test_secret_key")
        self.base_url = os.getenv("BCI_BASE_URL", "http://test.api.com")

    @patch('requests.get')
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
            client=self.client,
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

    @patch('requests.get')
    def test_get_bci_metrics_with_zbxxs(self, mock_get):
        """Test API call with zbxxs parameter."""
        mock_response = Mock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        zbxxs = "101-0003,101-0004"

        result = get_bci_metrics(
            client=self.client,
            start_day=self.start_day,
            end_day=self.end_day,
            zbxxs=zbxxs
        )

        # Verify zbxxs in params
        call_args = mock_get.call_args
        params = call_args[1]["params"]
        self.assertEqual(params["zbxxs"], zbxxs)

    @patch('requests.get')
    def test_get_bci_metrics_with_csdbs(self, mock_get):
        """Test API call with csdbs parameter."""
        mock_response = Mock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        csdbs = "055477ABB03B456E8B4B135E8193B25A"

        result = get_bci_metrics(
            client=self.client,
            start_day=self.start_day,
            end_day=self.end_day,
            csdbs=csdbs
        )

        # Verify csdbs in params
        call_args = mock_get.call_args
        params = call_args[1]["params"]
        self.assertEqual(params["csdbs"], csdbs)

    @patch('requests.get')
    def test_get_bci_metrics_http_error(self, mock_get):
        """Test API call with HTTP error."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_get.return_value = mock_response

        result = get_bci_metrics(
            client=self.client,
            start_day=self.start_day,
            end_day=self.end_day
        )

        # Should return error response
        self.assertFalse(result["success"])
        self.assertIn("message", result)
        self.assertIn("HTTP error", result["message"])

    @patch('requests.get')
    def test_get_bci_metrics_request_timeout(self, mock_get):
        """Test API call with timeout error."""
        mock_get.side_effect = requests.exceptions.Timeout("Request timeout")

        result = get_bci_metrics(
            client=self.client,
            start_day=self.start_day,
            end_day=self.end_day
        )

        # Should return error response
        self.assertFalse(result["success"])
        self.assertIn("Request error", result["message"])

    @patch('requests.get')
    def test_get_bci_metrics_connection_error(self, mock_get):
        """Test API call with connection error."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")

        result = get_bci_metrics(
            client=self.client,
            start_day=self.start_day,
            end_day=self.end_day
        )

        # Should return error response
        self.assertFalse(result["success"])
        self.assertIn("message", result)

    @patch('requests.get')
    def test_signature_included_in_request(self, mock_get):
        """Test that signature is properly generated and included."""
        mock_response = Mock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        get_bci_metrics(
            client=self.client,
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

    @patch('requests.get')
    def test_timeout_parameter(self, mock_get):
        """Test that timeout is set correctly."""
        mock_response = Mock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        get_bci_metrics(
            client=self.client,
            start_day=self.start_day,
            end_day=self.end_day
        )

        # Verify timeout is set
        call_args = mock_get.call_args
        self.assertEqual(call_args[1]["timeout"], 10)


class TestAPIParameterValidation(unittest.TestCase):
    """Test cases for API parameter validation."""

    @patch('requests.get')
    def test_date_format_validation(self, mock_get):
        """Test that dates are passed correctly."""
        mock_response = Mock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        start = "2022-01-01"
        end = "2022-12-31"

        get_bci_metrics(
            client=os.getenv("BCI_APP_ID", "test_client"),
            start_day=start,
            end_day=end
        )

        call_args = mock_get.call_args
        params = call_args[1]["params"]

        self.assertEqual(params["startDay"], start)
        self.assertEqual(params["endDay"], end)

    @patch('requests.get')
    def test_multiple_zbxxs_values(self, mock_get):
        """Test multiple zbxxs values with comma separation."""
        mock_response = Mock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        zbxxs = "101-0003,101-0004,101-0005"

        get_bci_metrics(
            client=os.getenv("BCI_APP_ID", "test_client"),
            start_day="2022-07-01",
            end_day="2022-07-01",
            zbxxs=zbxxs
        )

        call_args = mock_get.call_args
        params = call_args[1]["params"]

        self.assertEqual(params["zbxxs"], zbxxs)
        # Verify commas are preserved
        self.assertEqual(params["zbxxs"].count(","), 2)


if __name__ == "__main__":
    unittest.main()
