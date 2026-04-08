"""Unit tests for src/notifications/telegram.py.

All tests are fully offline — requests.post is patched throughout.
No network, no real bot token, no TELEGRAM_* env vars required.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.notifications.telegram import (
    TelegramNotifier,
    _html_escape,
    build_notifier,
    escape_mdv2,
)


# ── _html_escape ──────────────────────────────────────────────────


def test_html_escape_ampersand() -> None:
    assert _html_escape("a & b") == "a &amp; b"


def test_html_escape_lt_gt() -> None:
    assert _html_escape("<tag>") == "&lt;tag&gt;"


def test_html_escape_all_three() -> None:
    assert _html_escape("a & <b>") == "a &amp; &lt;b&gt;"


def test_html_escape_plain_text_unchanged() -> None:
    text = "NiftyShield P&L: +3,250"
    # only & is special here
    assert _html_escape(text) == "NiftyShield P&amp;L: +3,250"


def test_html_escape_empty_string() -> None:
    assert _html_escape("") == ""


# ── escape_mdv2 ───────────────────────────────────────────────────


def test_escape_mdv2_dots_and_parens() -> None:
    assert escape_mdv2("3.14 (pi)") == r"3\.14 \(pi\)"


def test_escape_mdv2_plus_sign() -> None:
    assert escape_mdv2("+3,250") == r"\+3,250"


def test_escape_mdv2_plain_text_unchanged() -> None:
    assert escape_mdv2("hello world") == "hello world"


# ── TelegramNotifier.send — happy path ───────────────────────────


def _make_ok_response() -> MagicMock:
    """Mock requests.Response with ok=True API body."""
    resp = MagicMock()
    resp.json.return_value = {"ok": True, "result": {"message_id": 42}}
    resp.raise_for_status.return_value = None
    return resp


def test_send_returns_true_on_success() -> None:
    with patch("src.notifications.telegram.requests.post") as mock_post:
        mock_post.return_value = _make_ok_response()
        notifier = TelegramNotifier(bot_token="fake-token", chat_id="123")
        assert notifier.send("hello") is True


def test_send_posts_to_correct_url() -> None:
    with patch("src.notifications.telegram.requests.post") as mock_post:
        mock_post.return_value = _make_ok_response()
        notifier = TelegramNotifier(bot_token="MY_TOKEN", chat_id="456")
        notifier.send("test")
        url = mock_post.call_args[0][0]
        assert "MY_TOKEN" in url
        assert "sendMessage" in url


def test_send_uses_html_parse_mode() -> None:
    with patch("src.notifications.telegram.requests.post") as mock_post:
        mock_post.return_value = _make_ok_response()
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        notifier.send("msg")
        payload = mock_post.call_args[1]["json"]
        assert payload["parse_mode"] == "HTML"


def test_send_wraps_text_in_pre_block() -> None:
    with patch("src.notifications.telegram.requests.post") as mock_post:
        mock_post.return_value = _make_ok_response()
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        notifier.send("hello")
        payload = mock_post.call_args[1]["json"]
        assert payload["text"].startswith("<pre>")
        assert payload["text"].endswith("</pre>")


def test_send_escapes_html_in_message() -> None:
    """'&' in the P&L summary must not break HTML parse_mode."""
    with patch("src.notifications.telegram.requests.post") as mock_post:
        mock_post.return_value = _make_ok_response()
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        notifier.send("P&L: +3,250")
        payload = mock_post.call_args[1]["json"]
        assert "&amp;" in payload["text"]
        assert "&L" not in payload["text"]


def test_send_passes_correct_chat_id() -> None:
    with patch("src.notifications.telegram.requests.post") as mock_post:
        mock_post.return_value = _make_ok_response()
        notifier = TelegramNotifier(bot_token="tok", chat_id="CHATID_999")
        notifier.send("msg")
        payload = mock_post.call_args[1]["json"]
        assert payload["chat_id"] == "CHATID_999"


# ── TelegramNotifier.send — error paths ──────────────────────────


def test_send_returns_false_on_request_exception() -> None:
    with patch("src.notifications.telegram.requests.post") as mock_post:
        mock_post.side_effect = requests.ConnectionError("unreachable")
        notifier = TelegramNotifier(bot_token="tok", chat_id="123")
        assert notifier.send("hello") is False


def test_send_returns_false_on_timeout() -> None:
    with patch("src.notifications.telegram.requests.post") as mock_post:
        mock_post.side_effect = requests.Timeout("timed out")
        notifier = TelegramNotifier(bot_token="tok", chat_id="123")
        assert notifier.send("hello") is False


def test_send_returns_false_on_http_error() -> None:
    with patch("src.notifications.telegram.requests.post") as mock_post:
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")
        mock_post.return_value = resp
        notifier = TelegramNotifier(bot_token="tok", chat_id="123")
        assert notifier.send("hello") is False


def test_send_returns_false_when_api_ok_is_false() -> None:
    with patch("src.notifications.telegram.requests.post") as mock_post:
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"ok": False, "description": "chat not found"}
        mock_post.return_value = resp
        notifier = TelegramNotifier(bot_token="tok", chat_id="bad_id")
        assert notifier.send("hello") is False


def test_send_does_not_raise_on_any_failure() -> None:
    """send() must be non-fatal — no exception should escape."""
    with patch("src.notifications.telegram.requests.post") as mock_post:
        mock_post.side_effect = Exception("unexpected crash")
        notifier = TelegramNotifier(bot_token="tok", chat_id="123")
        # Would raise if exception propagates
        result = notifier.send("hello")
        assert result is False


# ── build_notifier ────────────────────────────────────────────────


def test_build_notifier_returns_none_when_token_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert build_notifier() is None


def test_build_notifier_returns_none_when_only_token_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "some-token")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert build_notifier() is None


def test_build_notifier_returns_none_when_only_chat_id_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    assert build_notifier() is None


def test_build_notifier_returns_notifier_when_both_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "real-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "654321")
    notifier = build_notifier()
    assert isinstance(notifier, TelegramNotifier)


def test_build_notifier_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leading/trailing whitespace in env vars must not cause a false None."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "  tok  ")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "  123  ")
    assert build_notifier() is not None


def test_build_notifier_returns_none_for_blank_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "   ")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    assert build_notifier() is None
