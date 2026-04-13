"""Unit tests for src/auth/dhan_login.py.

All tests are fully offline — no network calls.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.auth.dhan_login import (
    build_login_url,
    validate_token,
    save_token,
    login,
    DHAN_WEB_URL,
)

# Env vars that can leak across tests if dotenv loads into os.environ
_DHAN_ENV_VARS = ["DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Prevent env var leakage between tests — dotenv writes to os.environ globally."""
    for var in _DHAN_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# build_login_url
# ---------------------------------------------------------------------------

def test_build_login_url_returns_dhan_web():
    url = build_login_url()
    assert url == DHAN_WEB_URL


def test_build_login_url_contains_dhan_domain():
    url = build_login_url()
    assert "dhan.co" in url


# ---------------------------------------------------------------------------
# validate_token
# ---------------------------------------------------------------------------

def test_validate_token_strips_whitespace():
    assert validate_token("  eyJabc123  ") == "eyJabc123"


def test_validate_token_returns_clean_token():
    token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9"
    assert validate_token(token) == token


def test_validate_token_raises_on_empty_string():
    with pytest.raises(ValueError, match="empty"):
        validate_token("")


def test_validate_token_raises_on_whitespace_only():
    with pytest.raises(ValueError, match="empty"):
        validate_token("   ")


# ---------------------------------------------------------------------------
# save_token
# ---------------------------------------------------------------------------

def test_save_token_writes_to_env(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("DHAN_CLIENT_ID=123456\n")

    save_token(env_path, "eyJtoken123")

    content = env_path.read_text()
    assert "DHAN_ACCESS_TOKEN" in content
    assert "eyJtoken123" in content


def test_save_token_upserts_existing_key(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text('DHAN_ACCESS_TOKEN="old_token"\n')

    save_token(env_path, "new_token")

    content = env_path.read_text()
    assert "new_token" in content
    assert content.count("DHAN_ACCESS_TOKEN") == 1


def test_save_token_preserves_other_vars(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("DHAN_CLIENT_ID=123456\nOTHER_VAR=keep_me\n")

    save_token(env_path, "mytoken")

    content = env_path.read_text()
    assert "OTHER_VAR" in content
    assert "DHAN_ACCESS_TOKEN" in content


# ---------------------------------------------------------------------------
# login (full flow)
# ---------------------------------------------------------------------------

def test_login_raises_if_client_id_missing(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("")

    with pytest.raises(ValueError, match="DHAN_CLIENT_ID"):
        login(env_path)


def test_login_raises_if_empty_input(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("DHAN_CLIENT_ID=123456\n")

    monkeypatch.setattr("builtins.input", lambda _: "")

    with patch("webbrowser.open"):
        with pytest.raises(ValueError, match="empty"):
            login(env_path)


def test_login_full_flow(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("DHAN_CLIENT_ID=123456\n")

    test_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.test"
    monkeypatch.setattr("builtins.input", lambda _: test_token)

    with patch("webbrowser.open") as mock_browser:
        login(env_path)

    mock_browser.assert_called_once_with(DHAN_WEB_URL)

    content = env_path.read_text()
    assert "DHAN_ACCESS_TOKEN" in content
    assert test_token in content


def test_login_full_flow_with_whitespace_token(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("DHAN_CLIENT_ID=123456\n")

    monkeypatch.setattr("builtins.input", lambda _: "  eyJtoken  ")

    with patch("webbrowser.open"):
        login(env_path)

    content = env_path.read_text()
    assert "eyJtoken" in content
