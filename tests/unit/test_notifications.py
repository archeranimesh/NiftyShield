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

_ENTITY_PARSE_ERROR_DESCRIPTION = (
    "Bad Request: can't parse entities: Can't find end of the entity starting at byte offset 455"
)

# Telegram env var leakage guard moved to tests/unit/conftest.py's
# session-autouse clean_telegram_env fixture — every test needs this, not
# just this file's.


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


async def test_send_uses_markdownv2_parse_mode() -> None:
    mock_session = _make_mock_session({"ok": True})
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        await notifier.send("msg")
        payload = mock_session.post.call_args[1]["json"]
        assert payload["parse_mode"] == "MarkdownV2"
        assert "<pre>" not in payload["text"]


async def test_send_does_not_auto_escape() -> None:
    """send() passes text through verbatim — escaping is the caller's job.

    Proves the new caller-responsibility model introduced by the
    MarkdownV2 migration (MD-1's escape_markdown()/mdcode()), not a
    silent regression of the old HTML auto-escaping behavior.
    """
    mock_session = _make_mock_session({"ok": True})
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        raw_text = "P&L: +3,250 (delta-neutral)."
        await notifier.send(raw_text)
        payload = mock_session.post.call_args[1]["json"]
        assert payload["text"] == raw_text


async def test_send_returns_false_on_telegram_entity_parse_error() -> None:
    """Regression test for the original DELTA_WARN bug this epic fixes.

    An unescaped MarkdownV2 reserved character (e.g. a lone underscore)
    makes Telegram reject the send with a 400 + entity-parse description.
    send() must swallow this like any other failure — return False, log
    a warning, never raise — per the non-fatal notification contract.
    """
    mock_session = _make_mock_session(
        {"ok": False, "description": _ENTITY_PARSE_ERROR_DESCRIPTION}, status=400
    )
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        result = await notifier.send("DELTA_WARN triggered")
        assert result is False


async def test_send_passes_correct_chat_id() -> None:
    mock_session = _make_mock_session({"ok": True})
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="CHATID_999")
        await notifier.send("msg")
        payload = mock_session.post.call_args[1]["json"]
        assert payload["chat_id"] == "CHATID_999"


# ── TelegramNotifier.send — error paths ──────────────────────────


async def test_send_logs_telegram_400_response_body() -> None:
    """BUG-042 B042.4: the 400 body (entity-parse offset) must reach the log."""
    body = "Bad Request: can't parse entities: Character '.' is reserved at byte offset 12"
    mock_session = _make_mock_session({"ok": False}, status=400)
    mock_session.post.return_value.text = AsyncMock(return_value=body)
    with (
        patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session),
        patch("src.notifications.telegram.logger") as mock_logger,
    ):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        assert await notifier.send("a.b") is False
    args = mock_logger.warning.call_args.args
    assert 400 in args
    assert body in args


async def test_send_400_with_unreadable_body_still_returns_false() -> None:
    mock_session = _make_mock_session({"ok": False}, status=400)
    mock_session.post.return_value.text = AsyncMock(side_effect=RuntimeError("closed"))
    with (
        patch("src.notifications.telegram.aiohttp.ClientSession", return_value=mock_session),
        patch("src.notifications.telegram.logger") as mock_logger,
    ):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        assert await notifier.send("hello") is False
    assert "<unreadable body>" in mock_logger.warning.call_args.args


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


# ── TelegramNotifier.send — BUG-042 plain-text fallback ──────────


def _make_resp(status: int, data: dict | None = None, body: str = "") -> MagicMock:
    """One context-managed aiohttp response with a JSON payload and text body."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=data or {})
    resp.text = AsyncMock(return_value=body)
    resp.raise_for_status.return_value = None
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


def _make_session(*responses: MagicMock | Exception) -> MagicMock:
    """Session whose successive post() calls yield ``responses`` in order."""
    session = MagicMock()
    session.post.side_effect = list(responses)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


async def test_send_entity_parse_400_resends_once_as_plain_text() -> None:
    session = _make_session(
        _make_resp(400, body=_ENTITY_PARSE_ERROR_DESCRIPTION),
        _make_resp(200, {"ok": True}),
    )
    with (
        patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session),
        patch("src.notifications.telegram.logger") as mock_logger,
    ):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        assert await notifier.send("P&L -11.08 (net)") is True

    assert session.post.call_count == 2
    first, second = (c.kwargs["json"] for c in session.post.call_args_list)
    assert first["parse_mode"] == "MarkdownV2"
    assert second == {"chat_id": "789", "text": "P&L -11.08 (net)"}  # same text, no escaping
    mock_logger.error.assert_called_once()
    assert mock_logger.error.call_args.args == ("telegram.entity_parse_plain_text_fallback",)
    assert mock_logger.error.call_args.kwargs["body"] == _ENTITY_PARSE_ERROR_DESCRIPTION


async def test_send_other_400_is_not_retried() -> None:
    session = _make_session(_make_resp(400, body="Bad Request: chat not found"))
    with (
        patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session),
        patch("src.notifications.telegram.logger") as mock_logger,
    ):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        assert await notifier.send("hello") is False
    assert session.post.call_count == 1
    mock_logger.error.assert_not_called()


async def test_send_entity_parse_text_on_non_400_is_not_retried() -> None:
    session = _make_session(_make_resp(500, body=_ENTITY_PARSE_ERROR_DESCRIPTION))
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        assert await notifier.send("hello") is False
    assert session.post.call_count == 1


async def test_send_success_posts_exactly_once() -> None:
    session = _make_session(_make_resp(200, {"ok": True}))
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        assert await notifier.send("hello") is True
    assert session.post.call_count == 1


async def test_send_plain_text_resend_rejected_returns_false_no_second_retry() -> None:
    session = _make_session(
        _make_resp(400, body=_ENTITY_PARSE_ERROR_DESCRIPTION),
        _make_resp(400, body=_ENTITY_PARSE_ERROR_DESCRIPTION),
    )
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        assert await notifier.send("hello") is False
    assert session.post.call_count == 2  # at most one retry


async def test_send_plain_text_resend_raising_stays_non_fatal() -> None:
    session = _make_session(
        _make_resp(400, body=_ENTITY_PARSE_ERROR_DESCRIPTION),
        aiohttp.ServerTimeoutError("timed out"),
    )
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789")
        assert await notifier.send("hello") is False


async def test_send_plain_text_resend_does_not_burn_budget() -> None:
    session = _make_session(
        _make_resp(400, body=_ENTITY_PARSE_ERROR_DESCRIPTION),
        _make_resp(200, {"ok": True}),
        _make_resp(200, {"ok": True}),
    )
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session):
        notifier = TelegramNotifier(bot_token="tok", chat_id="789", budget=2)
        assert await notifier.send("a.b") is True
        assert await notifier.send("second") is True


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
