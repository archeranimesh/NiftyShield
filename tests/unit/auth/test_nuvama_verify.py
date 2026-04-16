"""Unit tests for src/auth/nuvama_verify.py.

All tests are fully offline — APIConnect is patched at module level.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.auth.nuvama_verify import (
    parse_holdings,
    verify,
    load_api_connect,
    NUVAMA_CONF_FILE,
)

_NUVAMA_ENV_VARS = ["NUVAMA_API_KEY", "NUVAMA_API_SECRET", "NUVAMA_SETTINGS_FILE"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Prevent dotenv env var leakage between tests."""
    for var in _NUVAMA_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_holdings_json(records: list[dict]) -> str:
    return json.dumps({"eq": {"data": {"rmsHdg": records}}})


def _sample_holding(
    cp_name: str = "RELIANCE INDUSTRIES LTD",
    total_qty: int = 10,
    ltp: float = 2900.0,
) -> dict:
    return {"cpName": cp_name, "totalQty": total_qty, "ltp": ltp}


# ---------------------------------------------------------------------------
# parse_holdings
# ---------------------------------------------------------------------------

def test_parse_holdings_returns_flat_list():
    raw = _make_holdings_json([_sample_holding()])
    result = parse_holdings(raw)
    assert len(result) == 1
    assert result[0]["company_name"] == "RELIANCE INDUSTRIES LTD"
    assert result[0]["total_qty"] == 10
    assert result[0]["ltp"] == 2900.0


def test_parse_holdings_strips_company_name_whitespace():
    raw = _make_holdings_json([_sample_holding(cp_name="  HDFC BANK  ")])
    result = parse_holdings(raw)
    assert result[0]["company_name"] == "HDFC BANK"


def test_parse_holdings_multiple_records():
    raw = _make_holdings_json([
        _sample_holding("INFOSYS", 5, 1800.0),
        _sample_holding("TCS", 3, 4100.0),
    ])
    result = parse_holdings(raw)
    assert len(result) == 2
    assert result[1]["company_name"] == "TCS"


def test_parse_holdings_empty_list():
    raw = _make_holdings_json([])
    result = parse_holdings(raw)
    assert result == []


def test_parse_holdings_raises_on_invalid_json():
    with pytest.raises(json.JSONDecodeError):
        parse_holdings("not json at all")


def test_parse_holdings_returns_empty_on_missing_key():
    # Both fallback paths fail gracefully — empty list, no exception.
    raw = json.dumps({"eq": {"data": {}}})
    result = parse_holdings(raw)
    assert result == []


def test_parse_holdings_returns_empty_on_wrong_top_level():
    # Totally unexpected structure — both paths silently return [].
    raw = json.dumps({"wrong_key": {}})
    result = parse_holdings(raw)
    assert result == []


# ---------------------------------------------------------------------------
# load_api_connect
# ---------------------------------------------------------------------------

def test_load_api_connect_raises_if_credentials_missing(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("")  # no credentials

    with pytest.raises(ValueError, match="NUVAMA_API_KEY"):
        load_api_connect(env_path)


def test_load_api_connect_raises_if_only_key_set(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("NUVAMA_API_KEY=key\n")

    with pytest.raises(ValueError, match="NUVAMA_API_SECRET"):
        load_api_connect(env_path)


def test_load_api_connect_raises_if_settings_file_missing(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "NUVAMA_API_KEY=key\n"
        "NUVAMA_API_SECRET=secret\n"
        f"NUVAMA_SETTINGS_FILE={tmp_path}/nonexistent.json\n"
    )

    with pytest.raises(FileNotFoundError, match="settings file not found"):
        load_api_connect(env_path)


def test_load_api_connect_does_not_pass_json_session_as_conf(tmp_path, monkeypatch):
    # Regression: session file (JSON) must NOT be passed as SDK conf — configparser
    # raises MissingSectionHeaderError on JSON content.
    session_file = tmp_path / "data_MYKEY.txt"
    session_file.write_text('{"vt": "token", "auth": "hash"}')

    env_path = tmp_path / ".env"
    env_path.write_text(
        f"NUVAMA_API_KEY=MYKEY\n"
        f"NUVAMA_API_SECRET=MYSECRET\n"
        f"NUVAMA_SETTINGS_FILE={session_file}\n"
    )

    # Point NUVAMA_CONF_FILE to a non-existent path → conf_arg is None (safe default)
    monkeypatch.setattr("src.auth.nuvama_verify.NUVAMA_CONF_FILE", str(tmp_path / "no_conf.ini"))

    mock_instance = MagicMock()
    mock_cls = MagicMock(return_value=mock_instance)

    with patch("src.auth.nuvama_verify.APIConnect", mock_cls):
        result = load_api_connect(env_path)

    call_args = mock_cls.call_args[0]
    assert call_args[0] == "MYKEY"
    assert call_args[1] == "MYSECRET"
    assert call_args[2] == ""           # empty request_id
    assert call_args[3] is False        # download_contract must be False
    assert call_args[4] is None         # conf_arg is None — not the JSON session file
    assert call_args[4] != str(session_file)
    assert result is mock_instance


def test_load_api_connect_uses_ini_conf_when_present(tmp_path, monkeypatch):
    session_file = tmp_path / "data_MYKEY.txt"
    session_file.write_text('{"vt": "token"}')
    conf_file = tmp_path / "settings.ini"
    conf_file.write_text("[GLOBAL]\nLOG_LEVEL = DEBUG\n")

    env_path = tmp_path / ".env"
    env_path.write_text(
        f"NUVAMA_API_KEY=MYKEY\n"
        f"NUVAMA_API_SECRET=MYSECRET\n"
        f"NUVAMA_SETTINGS_FILE={session_file}\n"
    )

    monkeypatch.setattr("src.auth.nuvama_verify.NUVAMA_CONF_FILE", str(conf_file))

    mock_cls = MagicMock(return_value=MagicMock())
    with patch("src.auth.nuvama_verify.APIConnect", mock_cls):
        load_api_connect(env_path)

    assert mock_cls.call_args[0][4] == str(conf_file)


def test_load_api_connect_changes_cwd_to_session_dir(tmp_path, monkeypatch):
    # SDK reads data_{api_key}.txt relative to CWD. We use chdir to the session
    # file's directory before init — no copying, no stray files in project root.
    session_file = tmp_path / "data_MYKEY.txt"
    session_file.write_text('{"vt": "token"}')

    env_path = tmp_path / ".env"
    env_path.write_text(
        f"NUVAMA_API_KEY=MYKEY\n"
        f"NUVAMA_API_SECRET=MYSECRET\n"
        f"NUVAMA_SETTINGS_FILE={session_file}\n"
    )

    monkeypatch.setattr("src.auth.nuvama_verify.NUVAMA_CONF_FILE", str(tmp_path / "no_conf.ini"))

    observed_cwd: list[Path] = []

    def recording_apiconnect(*args, **kwargs):
        observed_cwd.append(Path.cwd())
        return MagicMock()

    with patch("src.auth.nuvama_verify.APIConnect", side_effect=recording_apiconnect):
        load_api_connect(env_path)

    # CWD inside the SDK call must be tmp_path (the session directory)
    assert len(observed_cwd) == 1
    assert observed_cwd[0].resolve() == tmp_path.resolve()
    # CWD must be restored after the call
    assert Path.cwd() != tmp_path


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def test_verify_returns_true_on_valid_holdings(tmp_path):
    mock_api = MagicMock()
    mock_api.Holdings.return_value = _make_holdings_json([_sample_holding()])

    with patch("src.auth.nuvama_verify.load_api_connect", return_value=mock_api):
        result = verify(tmp_path / ".env")

    assert result is True


def test_verify_returns_false_on_json_decode_error(tmp_path):
    mock_api = MagicMock()
    mock_api.Holdings.return_value = "broken json {{{"

    with patch("src.auth.nuvama_verify.load_api_connect", return_value=mock_api):
        result = verify(tmp_path / ".env")

    assert result is False


def test_verify_returns_true_on_unexpected_schema_with_zero_holdings(tmp_path):
    # parse_holdings() has a two-path fallback that returns [] on unexpected
    # structure. verify() treats 0 holdings as a valid (active) session.
    mock_api = MagicMock()
    mock_api.Holdings.return_value = json.dumps({"unexpected": "shape"})

    with patch("src.auth.nuvama_verify.load_api_connect", return_value=mock_api):
        result = verify(tmp_path / ".env")

    assert result is True


def test_verify_returns_false_on_config_error(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("")  # no credentials — load_api_connect raises ValueError

    result = verify(env_path)
    assert result is False


def test_verify_returns_false_on_api_exception(tmp_path):
    mock_api = MagicMock()
    mock_api.Holdings.side_effect = RuntimeError("network timeout")

    with patch("src.auth.nuvama_verify.load_api_connect", return_value=mock_api):
        result = verify(tmp_path / ".env")

    assert result is False


def test_verify_shows_holdings_count(tmp_path, capsys):
    mock_api = MagicMock()
    mock_api.Holdings.return_value = _make_holdings_json([
        _sample_holding("HDFC BANK", 20, 1750.0),
        _sample_holding("INFOSYS", 15, 1820.0),
    ])

    with patch("src.auth.nuvama_verify.load_api_connect", return_value=mock_api):
        verify(tmp_path / ".env")

    out = capsys.readouterr().out
    assert "2 holding(s)" in out
    assert "HDFC BANK" in out
