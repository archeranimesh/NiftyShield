"""Unit tests for src/notifications/telegram.py.

All tests are fully offline — aiohttp.ClientSession is patched throughout.
No network, no real bot token, no TELEGRAM_* env vars required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from src.notifications.telegram import (
    TelegramNotifier,
    _html_escape,
    build_notifier,
    escape_mdv2,
)

# Env vars that can leak across tests if dotenv loads into os.environ — several
# scripts/ modules (e.g. paper_3track_roll.py) call load_dotenv() unconditionally
# at import time, which is never undone by monkeypatch since monkeypatch only
# reverts changes it made itself. Same pattern as tests/unit/auth/test_dhan_verify.py.
_TELEGRAM_ENV_VARS = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_MESSAGE_BUDGET"]


@pytest.fixture(autouse=True)
def clean_telegram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent env var leakage between tests — dotenv writes to os.environ globally."""
    for var in _TELEGRAM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


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


# ── TelegramNotifier.send — mocks ───────────────────────────────


def _make_mock_session(resp_data: dict, status: int = 200) -> MagicMock:
    """Mock aiohttp.ClientSession with a context-managed post() response."""
    mock_resp = MagicMock()
    mock_resp.json = AsyncMock(return_value=resp_data)
    mock_resp.status = status
    if status >= 400:
        mock_resp.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=status, message="Error"
        )
    else:
        mock_resp.raise_for_status.return_value = None

    # mock_resp used as 'async with session.post(...) as resp:'
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post.return_value = mock_resp
    # mock_session used as 'async with aiohttp.ClientSession(...) as session:'
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    return mock_session


# ── TelegramNotifier.send — happy path ───────────────────────────


async def test_send_returns_true_on_success() -> None:
    mock_session = _make_mock_session({"ok": True, "result": {"message_id": 42}})
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="fake-token", chat_id="123")
        assert await notifier.send("hello") is True


async def test_send_posts_to_correct_url() -> None:
    mock_session = _make_mock_session({"ok": True})
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="MY_TOKEN", chat_id="456")
        await notifier.send("test")
        # ClientSession instantiation url is not where post happens
        # It's session.post(url, ...)
        url = mock_session.post.call_args[0][0]
        assert "MY_TOKEN" in url
        assert "sendMessage" in url


async def test_send_uses_html_parse_mode() -> None:
    mock_session = _make_mock_session({"ok": True})
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        await notifier.send("msg")
        payload = mock_session.post.call_args[1]["json"]
        assert payload["parse_mode"] == "HTML"


async def test_send_wraps_text_in_pre_block() -> None:
    mock_session = _make_mock_session({"ok": True})
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        await notifier.send("hello")
        payload = mock_session.post.call_args[1]["json"]
        assert payload["text"].startswith("<pre>")
        assert payload["text"].endswith("</pre>")


async def test_send_escapes_html_in_message() -> None:
    """'&' in the P&L summary must not break HTML parse_mode."""
    mock_session = _make_mock_session({"ok": True})
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        await notifier.send("P&L: +3,250")
        payload = mock_session.post.call_args[1]["json"]
        assert "&amp;" in payload["text"]
        assert "&L" not in payload["text"]


async def test_send_passes_correct_chat_id() -> None:
    mock_session = _make_mock_session({"ok": True})
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="CHATID_999")
        await notifier.send("msg")
        payload = mock_session.post.call_args[1]["json"]
        assert payload["chat_id"] == "CHATID_999"


# ── TelegramNotifier.send — error paths ──────────────────────────


async def test_send_returns_false_on_request_exception() -> None:
    # Patch ClientSession to raise on creation or entering context
    with patch("src.notifications.telegram.aiohttp.ClientSession") as mock_cls:
        mock_cls.side_effect = Exception("unreachable")
        notifier = TelegramNotifier(bot_token="tok", chat_id="123")
        assert await notifier.send("hello") is False


async def test_send_returns_false_on_timeout() -> None:
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.post.side_effect = aiohttp.ServerTimeoutError("timed out")

    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="123")
        assert await notifier.send("hello") is False


async def test_send_returns_false_on_http_error() -> None:
    mock_session = _make_mock_session({}, status=401)
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="123")
        assert await notifier.send("hello") is False


async def test_send_returns_false_when_api_ok_is_false() -> None:
    mock_session = _make_mock_session({"ok": False, "description": "chat not found"})
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="bad_id")
        assert await notifier.send("hello") is False


async def test_send_does_not_raise_on_any_failure() -> None:
    """send() must be non-fatal — no exception should escape."""
    with patch("src.notifications.telegram.aiohttp.ClientSession") as mock_cls:
        mock_cls.side_effect = RuntimeError("unexpected crash")
        notifier = TelegramNotifier(bot_token="tok", chat_id="123")
        # Would raise if exception propagates
        result = await notifier.send("hello")
        assert result is False


# ── TelegramNotifier.send — budget limits ────────────────────────


async def test_send_respects_message_budget() -> None:
    mock_session = _make_mock_session({"ok": True})
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="123", budget=2)
        assert await notifier.send("msg 1") is True
        assert await notifier.send("msg 2") is True
        assert await notifier.send("msg 3") is False
        assert mock_session.post.call_count == 2


async def test_send_with_zero_budget_suppresses_all() -> None:
    mock_session = _make_mock_session({"ok": True})
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="123", budget=0)
        assert await notifier.send("msg") is False
        assert mock_session.post.call_count == 0


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


def test_build_notifier_reads_budget_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TELEGRAM_MESSAGE_BUDGET", "42")
    notifier = build_notifier()
    assert notifier is not None
    assert notifier._budget == 42


def test_build_notifier_defaults_budget_on_invalid_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TELEGRAM_MESSAGE_BUDGET", "not-an-int")
    notifier = build_notifier()
    assert notifier is not None
    assert notifier._budget == 10
