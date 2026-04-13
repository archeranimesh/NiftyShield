"""Unit tests for src/auth/dhan_verify.py.

All tests are fully offline — requests.get is mocked via unittest.mock.patch.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.auth.dhan_verify import (
    load_dhan_credentials,
    fetch_profile,
    fetch_holdings,
    parse_holdings,
    verify,
    _build_headers,
    DHAN_API_BASE,
)

# Env vars that can leak across tests if dotenv loads into os.environ
_DHAN_ENV_VARS = ["DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Prevent env var leakage between tests — dotenv writes to os.environ globally."""
    for var in _DHAN_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# _build_headers
# ---------------------------------------------------------------------------

def test_build_headers_includes_access_token():
    headers = _build_headers("my_jwt_token")
    assert headers["access-token"] == "my_jwt_token"
    assert headers["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# load_dhan_credentials
# ---------------------------------------------------------------------------

def test_load_credentials_happy_path(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("DHAN_CLIENT_ID=123456\nDHAN_ACCESS_TOKEN=eyJtoken\n")

    client_id, token = load_dhan_credentials(env_path)
    assert client_id == "123456"
    assert token == "eyJtoken"


def test_load_credentials_missing_client_id(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("DHAN_ACCESS_TOKEN=eyJtoken\n")

    with pytest.raises(ValueError, match="DHAN_CLIENT_ID"):
        load_dhan_credentials(env_path)


def test_load_credentials_missing_access_token(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("DHAN_CLIENT_ID=123456\n")

    with pytest.raises(ValueError, match="DHAN_ACCESS_TOKEN"):
        load_dhan_credentials(env_path)


def test_load_credentials_strips_whitespace(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("DHAN_CLIENT_ID= 123456 \nDHAN_ACCESS_TOKEN= eyJ \n")

    client_id, token = load_dhan_credentials(env_path)
    assert client_id == "123456"
    assert token == "eyJ"


# ---------------------------------------------------------------------------
# fetch_profile
# ---------------------------------------------------------------------------

def test_fetch_profile_happy_path():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "dhanClientId": "123456",
        "dhanClientName": "JOHN DOE",
    }
    mock_response.raise_for_status = MagicMock()

    with patch("src.auth.dhan_verify.requests.get", return_value=mock_response) as mock_get:
        result = fetch_profile("123456", "eyJtoken")

    mock_get.assert_called_once()
    call_url = mock_get.call_args[0][0]
    assert call_url == f"{DHAN_API_BASE}/profile"
    assert result["dhanClientName"] == "JOHN DOE"


def test_fetch_profile_http_error():
    import requests as req

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = req.HTTPError(
        response=mock_response
    )

    with patch("src.auth.dhan_verify.requests.get", return_value=mock_response):
        with pytest.raises(req.HTTPError):
            fetch_profile("123456", "bad_token")


# ---------------------------------------------------------------------------
# fetch_holdings
# ---------------------------------------------------------------------------

def test_fetch_holdings_returns_list():
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"tradingSymbol": "HDFC", "totalQty": 100, "avgCostPrice": 2655.0},
    ]
    mock_response.raise_for_status = MagicMock()

    with patch("src.auth.dhan_verify.requests.get", return_value=mock_response):
        result = fetch_holdings("123456", "eyJtoken")

    assert len(result) == 1
    assert result[0]["tradingSymbol"] == "HDFC"


def test_fetch_holdings_empty_list():
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()

    with patch("src.auth.dhan_verify.requests.get", return_value=mock_response):
        result = fetch_holdings("123456", "eyJtoken")

    assert result == []


def test_fetch_holdings_dict_with_data_key():
    """Some API versions may wrap holdings in a dict."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [{"tradingSymbol": "TCS", "totalQty": 50, "avgCostPrice": 3300.0}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("src.auth.dhan_verify.requests.get", return_value=mock_response):
        result = fetch_holdings("123456", "eyJtoken")

    assert len(result) == 1
    assert result[0]["tradingSymbol"] == "TCS"


# ---------------------------------------------------------------------------
# parse_holdings
# ---------------------------------------------------------------------------

def test_parse_holdings_multiple_records():
    raw = [
        {"tradingSymbol": "HDFC", "totalQty": 100, "avgCostPrice": 2655.0},
        {"tradingSymbol": "TCS", "totalQty": 50, "avgCostPrice": 3345.8},
    ]
    parsed = parse_holdings(raw)
    assert len(parsed) == 2
    assert parsed[0]["trading_symbol"] == "HDFC"
    assert parsed[1]["total_qty"] == 50


def test_parse_holdings_empty_list():
    assert parse_holdings([]) == []


def test_parse_holdings_missing_fields():
    """Missing fields should get default values, not raise."""
    raw = [{"tradingSymbol": "  RELIANCE  "}]
    parsed = parse_holdings(raw)
    assert len(parsed) == 1
    assert parsed[0]["trading_symbol"] == "RELIANCE"
    assert parsed[0]["total_qty"] == 0
    assert parsed[0]["avg_cost_price"] == 0.0


def test_parse_holdings_skips_malformed():
    """Malformed entries (non-dict) should be skipped."""
    raw = [None, {"tradingSymbol": "INFY", "totalQty": 10, "avgCostPrice": 1500.0}]
    parsed = parse_holdings(raw)
    assert len(parsed) == 1
    assert parsed[0]["trading_symbol"] == "INFY"


# ---------------------------------------------------------------------------
# verify (full flow)
# ---------------------------------------------------------------------------

def test_verify_returns_true_on_success(tmp_path, capsys):
    env_path = tmp_path / ".env"
    env_path.write_text("DHAN_CLIENT_ID=123456\nDHAN_ACCESS_TOKEN=eyJtoken\n")

    profile_resp = MagicMock()
    profile_resp.json.return_value = {
        "dhanClientId": "123456",
        "dhanClientName": "JOHN DOE",
    }
    profile_resp.raise_for_status = MagicMock()

    holdings_resp = MagicMock()
    holdings_resp.json.return_value = [
        {"tradingSymbol": "HDFC", "totalQty": 100, "avgCostPrice": 2655.0},
    ]
    holdings_resp.raise_for_status = MagicMock()

    def mock_get(url, **kwargs):
        if "profile" in url:
            return profile_resp
        return holdings_resp

    with patch("src.auth.dhan_verify.requests.get", side_effect=mock_get):
        result = verify(env_path)

    assert result is True
    captured = capsys.readouterr()
    assert "JOHN DOE" in captured.out
    assert "1 holding(s)" in captured.out


def test_verify_returns_false_on_missing_credentials(tmp_path, capsys):
    env_path = tmp_path / ".env"
    env_path.write_text("")

    result = verify(env_path)

    assert result is False
    captured = capsys.readouterr()
    assert "Configuration error" in captured.out


def test_verify_returns_false_on_http_401(tmp_path, capsys):
    import requests as req

    env_path = tmp_path / ".env"
    env_path.write_text("DHAN_CLIENT_ID=123456\nDHAN_ACCESS_TOKEN=expired_token\n")

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = req.HTTPError(
        response=mock_response
    )

    with patch("src.auth.dhan_verify.requests.get", return_value=mock_response):
        result = verify(env_path)

    assert result is False
    captured = capsys.readouterr()
    assert "expired or invalid" in captured.out


def test_verify_stdout_format(tmp_path, capsys):
    """Verify output format matches expected pattern."""
    env_path = tmp_path / ".env"
    env_path.write_text("DHAN_CLIENT_ID=123456\nDHAN_ACCESS_TOKEN=eyJtoken\n")

    profile_resp = MagicMock()
    profile_resp.json.return_value = {
        "dhanClientId": "123456",
        "dhanClientName": "TEST USER",
    }
    profile_resp.raise_for_status = MagicMock()

    holdings_resp = MagicMock()
    holdings_resp.json.return_value = []
    holdings_resp.raise_for_status = MagicMock()

    def mock_get(url, **kwargs):
        if "profile" in url:
            return profile_resp
        return holdings_resp

    with patch("src.auth.dhan_verify.requests.get", side_effect=mock_get):
        verify(env_path)

    captured = capsys.readouterr()
    assert "✓ Dhan session active" in captured.out
    assert "TEST USER" in captured.out
    assert "0 holding(s)" in captured.out
