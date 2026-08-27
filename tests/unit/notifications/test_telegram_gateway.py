"""Unit tests for src/notifications/telegram_gateway.py.

All tests are fully offline — aiohttp.ClientSession is patched throughout.
No network calls, no real bot token, no TELEGRAM_* env vars required.
"""

from __future__ import annotations

import datetime
import sqlite3
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from src.notifications.telegram_gateway import TelegramGateway, _build_keyboard

# ── Test fixtures / helpers ──────────────────────────────────────────


def _make_gateway(chat_id: str = "111") -> TelegramGateway:
    """Return a TelegramGateway configured with a fake token."""
    return TelegramGateway(
        bot_token="test-token",
        chat_id=chat_id,
        db_path="/tmp/nonexistent_test.db",
    )


def _make_http_mock(resp_data: dict, status: int = 200) -> MagicMock:
    """Build an aiohttp.ClientSession mock for POST and GET calls."""
    mock_resp = MagicMock()
    mock_resp.json = AsyncMock(return_value=resp_data)
    mock_resp.status = status
    if status >= 400:
        mock_resp.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=status, message="Error"
        )
    else:
        mock_resp.raise_for_status.return_value = None
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post.return_value = mock_resp
    mock_session.get.return_value = mock_resp
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    return mock_session


def _make_signal_event(
    valid_actions: list[str] | None = None,
    event_type: str = "TIME_STOP",
    severity: str = "ACTION",
    description: str = "Test signal",
) -> object:
    """Return a minimal SignalEvent with optional valid_actions payload."""
    from src.strategy.protocol import SignalEvent

    return SignalEvent(
        event_type=event_type,
        severity=severity,
        description=description,
        payload={"valid_actions": valid_actions if valid_actions is not None else ["CLOSE_FULL"]},
    )


def _make_pending_approvals_db() -> tuple[str, sqlite3.Connection]:
    """Create a temp SQLite DB with a pending_approvals table.

    Returns:
        Tuple of (db_path_str, connection). Caller is responsible for
        closing the connection.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE pending_approvals (
            id          INTEGER PRIMARY KEY,
            status      TEXT NOT NULL DEFAULT 'PENDING',
            expires_at  TEXT NOT NULL,
            resolved_at TEXT
        )
        """
    )
    conn.commit()
    return db_path, conn


# ── _build_keyboard ──────────────────────────────────────────────────


def test_build_keyboard_creates_one_row_per_action_plus_reject() -> None:
    keyboard = _build_keyboard(["CLOSE_FULL", "CLOSE_CALL_SPREAD"])
    assert len(keyboard) == 3  # 2 actions + Reject All
    assert keyboard[-1][0]["callback_data"] == "reject"


def test_build_keyboard_assigns_1indexed_ranks() -> None:
    keyboard = _build_keyboard(["CLOSE_FULL", "CLOSE_CALL_SPREAD", "CLOSE_PUT_SPREAD"])
    assert keyboard[0][0]["callback_data"] == "approve:1"
    assert keyboard[1][0]["callback_data"] == "approve:2"
    assert keyboard[2][0]["callback_data"] == "approve:3"
    assert keyboard[3][0]["callback_data"] == "reject"


def test_build_keyboard_uses_action_type_as_button_label() -> None:
    keyboard = _build_keyboard(["MONETIZE_PP"])
    assert keyboard[0][0]["text"] == "MONETIZE_PP"


def test_build_keyboard_empty_actions_returns_only_reject() -> None:
    keyboard = _build_keyboard([])
    assert len(keyboard) == 1
    assert keyboard[0][0]["callback_data"] == "reject"


# ── send_plain_message ───────────────────────────────────────────────


async def test_send_plain_message_returns_true_on_success() -> None:
    gw = _make_gateway()
    mock_send = AsyncMock(return_value=True)
    gw._notifier.send = mock_send  # type: ignore[method-assign]
    result = await gw.send_plain_message("hello")
    assert result is True
    mock_send.assert_awaited_once_with("hello")


async def test_send_plain_message_returns_false_on_network_error() -> None:
    gw = _make_gateway()
    mock_send = AsyncMock(return_value=False)
    gw._notifier.send = mock_send  # type: ignore[method-assign]
    result = await gw.send_plain_message("hello")
    assert result is False


async def test_send_plain_message_never_raises_on_exception() -> None:
    gw = _make_gateway()
    gw._notifier.send = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    # TelegramNotifier.send never raises; if somehow it does, gateway must handle it
    # Here we verify the contract by wrapping in try — if send_plain_message raised,
    # the test would fail.
    try:
        await gw.send_plain_message("test")
    except Exception:  # pragma: no cover
        pytest.fail("send_plain_message must not propagate exceptions")


# ── send_approval_request ────────────────────────────────────────────


async def test_send_approval_request_returns_message_id_on_success() -> None:
    gw = _make_gateway()
    mock_session = _make_http_mock({"ok": True, "result": {"message_id": 42}})
    with patch(
        "src.notifications.telegram_gateway.aiohttp.ClientSession",
        return_value=mock_session,
    ):
        result = await gw.send_approval_request(
            event=_make_signal_event(["CLOSE_FULL"]),
            context_str="Strategy: paper_csp_nifty_v1\nSignal: TIME_STOP",
        )
    assert result == 42


async def test_send_approval_request_sends_buttons_for_valid_actions() -> None:
    """2 valid_actions → 3 keyboard buttons (2 action + Reject All)."""
    gw = _make_gateway()
    mock_session = _make_http_mock({"ok": True, "result": {"message_id": 1}})
    with patch(
        "src.notifications.telegram_gateway.aiohttp.ClientSession",
        return_value=mock_session,
    ):
        await gw.send_approval_request(
            event=_make_signal_event(["CLOSE_FULL", "CLOSE_CALL_SPREAD"]),
            context_str="context",
        )
    payload = mock_session.post.call_args[1]["json"]
    keyboard = payload["reply_markup"]["inline_keyboard"]
    assert len(keyboard) == 3  # 2 actions + Reject All
    assert keyboard[-1][0]["callback_data"] == "reject"


async def test_send_approval_request_returns_none_on_api_failure() -> None:
    gw = _make_gateway()
    mock_session = _make_http_mock({"ok": False, "description": "Forbidden"})
    with patch(
        "src.notifications.telegram_gateway.aiohttp.ClientSession",
        return_value=mock_session,
    ):
        result = await gw.send_approval_request(
            event=_make_signal_event(),
            context_str="context",
        )
    assert result is None


async def test_send_approval_request_returns_none_on_http_exception() -> None:
    gw = _make_gateway()
    mock_session = _make_http_mock({}, status=500)
    with patch(
        "src.notifications.telegram_gateway.aiohttp.ClientSession",
        return_value=mock_session,
    ):
        result = await gw.send_approval_request(
            event=_make_signal_event(),
            context_str="context",
        )
    assert result is None


async def test_send_approval_request_uses_markdown_v2_parse_mode() -> None:
    """ClientSession for sendMessage in send_approval_request must use parse_mode MarkdownV2."""
    gw = _make_gateway()
    mock_session = _make_http_mock({"ok": True, "result": {"message_id": 1}})
    with patch(
        "src.notifications.telegram_gateway.aiohttp.ClientSession",
        return_value=mock_session,
    ):
        await gw.send_approval_request(
            event=_make_signal_event(),
            context_str="context",
        )
    payload = mock_session.post.call_args[1]["json"]
    assert payload["parse_mode"] == "MarkdownV2"


async def test_send_approval_request_escapes_reserved_characters() -> None:
    """Dynamic event fields containing MarkdownV2 reserved chars survive escaped, not raw."""
    gw = _make_gateway()
    mock_session = _make_http_mock({"ok": True, "result": {"message_id": 1}})
    with patch(
        "src.notifications.telegram_gateway.aiohttp.ClientSession",
        return_value=mock_session,
    ):
        await gw.send_approval_request(
            event=_make_signal_event(
                event_type="DELTA_STOP(final)",
                description="delta breach_v2 at 0.40 (final)",
            ),
            context_str="context",
        )
    payload = mock_session.post.call_args[1]["json"]
    text = payload["text"]
    assert "DELTA_STOP(final)" not in text
    assert r"DELTA\_STOP\(final\)" in text
    assert "delta breach_v2 at 0.40 (final)" not in text
    assert r"delta breach\_v2 at 0\.40 \(final\)" in text


async def test_send_approval_request_escapes_backtick_in_context_str() -> None:
    """A stray backtick in context_str must not break the message or open a code span."""
    gw = _make_gateway()
    mock_session = _make_http_mock({"ok": True, "result": {"message_id": 1}})
    context_with_backtick = "leg=`NSE_FO|65900` credit=120.5"
    with patch(
        "src.notifications.telegram_gateway.aiohttp.ClientSession",
        return_value=mock_session,
    ):
        result = await gw.send_approval_request(
            event=_make_signal_event(),
            context_str=context_with_backtick,
        )
    assert result == 1
    payload = mock_session.post.call_args[1]["json"]
    text = payload["text"]
    # The raw backtick must not survive unescaped — it must be backslash-escaped.
    assert "`NSE_FO" not in text
    assert r"\`NSE\_FO\|65900\`" in text


async def test_send_approval_request_strategy_id_with_underscore_survives() -> None:
    """A strategy_id/instrument label with an underscore in context_str must render
    as literal text, not silently open/break a MarkdownV2 italic entity (same
    regression-test pattern as ROLL-1's DELTA_WARN-class coverage)."""
    gw = _make_gateway()
    mock_session = _make_http_mock({"ok": True, "result": {"message_id": 1}})
    context_with_ids = "Strategy: paper_ic_nifty_v2_monthly\nLeg: NIFTY_25AUG_24500_CE"
    with patch(
        "src.notifications.telegram_gateway.aiohttp.ClientSession",
        return_value=mock_session,
    ):
        result = await gw.send_approval_request(
            event=_make_signal_event(),
            context_str=context_with_ids,
        )
    assert result == 1
    payload = mock_session.post.call_args[1]["json"]
    text = payload["text"]
    assert "paper_ic_nifty_v2_monthly" not in text
    assert r"paper\_ic\_nifty\_v2\_monthly" in text
    assert "NIFTY_25AUG_24500_CE" not in text
    assert r"NIFTY\_25AUG\_24500\_CE" in text


async def test_send_approval_request_returns_none_on_empty_valid_actions() -> None:
    """Missing/empty valid_actions → return None without posting to Telegram."""
    gw = _make_gateway()
    mock_session = _make_http_mock({"ok": True, "result": {"message_id": 7}})
    with patch(
        "src.notifications.telegram_gateway.aiohttp.ClientSession",
        return_value=mock_session,
    ):
        result = await gw.send_approval_request(
            event=_make_signal_event([]),
            context_str="context",
        )
    assert result is None
    mock_session.post.assert_not_called()


# ── Auth guard ───────────────────────────────────────────────────────


async def test_auth_guard_drops_callback_from_unknown_sender() -> None:
    gw = _make_gateway(chat_id="111")
    on_approved = AsyncMock()
    on_rejected = AsyncMock()

    cq = {
        "from": {"id": 999},  # unknown sender
        "message": {"message_id": 10, "chat": {"id": 999}},
        "data": "approve:1",
    }
    await gw._handle_callback(cq, on_approved, on_rejected)
    on_approved.assert_not_awaited()
    on_rejected.assert_not_awaited()


async def test_auth_guard_routes_approve_from_correct_sender() -> None:
    gw = _make_gateway(chat_id="111")
    on_approved = AsyncMock()
    on_rejected = AsyncMock()

    cq = {
        "from": {"id": 111},  # matches chat_id
        "message": {"message_id": 42, "chat": {"id": 111}},
        "data": "approve:2",
    }
    await gw._handle_callback(cq, on_approved, on_rejected)
    on_approved.assert_awaited_once_with(42, 2)
    on_rejected.assert_not_awaited()


async def test_auth_guard_drops_non_allowlisted_sender_in_matching_chat() -> None:
    """Regression (FR-7 row 9): a group-chat member other than the configured
    sender must be rejected even when the callback's chat.id matches
    self._chat_id. Chat membership is not a valid stand-in for sender
    identity — only sender_id == self._chat_id authorises approve/reject.
    """
    gw = _make_gateway(chat_id="-1001234567")
    on_approved = AsyncMock()
    on_rejected = AsyncMock()

    cq = {
        "from": {"id": 999},  # different user in the same group chat
        "message": {"message_id": 7, "chat": {"id": -1001234567}},
        "data": "approve:1",
    }
    await gw._handle_callback(cq, on_approved, on_rejected)
    on_approved.assert_not_awaited()
    on_rejected.assert_not_awaited()


async def test_auth_guard_routes_reject_from_correct_sender() -> None:
    gw = _make_gateway(chat_id="111")
    on_approved = AsyncMock()
    on_rejected = AsyncMock()

    cq = {
        "from": {"id": 111},
        "message": {"message_id": 55, "chat": {"id": 111}},
        "data": "reject",
    }
    await gw._handle_callback(cq, on_approved, on_rejected)
    on_rejected.assert_awaited_once_with(55)
    on_approved.assert_not_awaited()


# ── Timeout scanner ──────────────────────────────────────────────────


async def test_timeout_scanner_expires_stale_pending_row() -> None:
    db_path, conn = _make_pending_approvals_db()
    past_iso = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
    ).isoformat()
    conn.execute(
        "INSERT INTO pending_approvals (status, expires_at) VALUES ('PENDING', ?)",
        (past_iso,),
    )
    conn.commit()
    conn.close()

    gw = TelegramGateway(bot_token="tok", chat_id="1", db_path=db_path)
    await gw.scan_expired_approvals()

    check_conn = sqlite3.connect(db_path)
    row = check_conn.execute(
        "SELECT status, resolved_at FROM pending_approvals WHERE id = 1"
    ).fetchone()
    check_conn.close()

    assert row[0] == "EXPIRED"
    assert row[1] is not None


async def test_timeout_scanner_leaves_non_expired_rows_untouched() -> None:
    db_path, conn = _make_pending_approvals_db()
    future_iso = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    ).isoformat()
    conn.execute(
        "INSERT INTO pending_approvals (status, expires_at) VALUES ('PENDING', ?)",
        (future_iso,),
    )
    conn.commit()
    conn.close()

    gw = TelegramGateway(bot_token="tok", chat_id="1", db_path=db_path)
    await gw.scan_expired_approvals()

    check_conn = sqlite3.connect(db_path)
    row = check_conn.execute("SELECT status FROM pending_approvals WHERE id = 1").fetchone()
    check_conn.close()

    assert row[0] == "PENDING"


async def test_timeout_scanner_non_fatal_on_missing_table() -> None:
    """Scanner must not raise when pending_approvals table doesn't exist yet."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    gw = TelegramGateway(bot_token="tok", chat_id="1", db_path=db_path)
    # Should complete without raising
    await gw.scan_expired_approvals()


# ── ClientTimeout assertions ─────────────────────────────────────────


async def test_send_approval_request_session_has_timeout() -> None:
    """ClientSession for sendMessage in send_approval_request must use total=10."""
    gw = _make_gateway()
    mock_session = _make_http_mock({"ok": True, "result": {"message_id": 1}})
    with patch(
        "src.notifications.telegram_gateway.aiohttp.ClientSession",
        return_value=mock_session,
    ) as mock_cls:
        await gw.send_approval_request(
            event=_make_signal_event(["CLOSE_FULL"]),
            context_str="context",
        )
    _, kwargs = mock_cls.call_args
    timeout = kwargs.get("timeout")
    assert isinstance(timeout, aiohttp.ClientTimeout)
    assert timeout.total == 10


async def test_get_updates_session_has_timeout() -> None:
    """ClientSession for getUpdates in _get_updates must use total=40."""
    gw = _make_gateway()
    mock_session = _make_http_mock({"ok": True, "result": []})
    with patch(
        "src.notifications.telegram_gateway.aiohttp.ClientSession",
        return_value=mock_session,
    ) as mock_cls:
        await gw._get_updates(0)
    _, kwargs = mock_cls.call_args
    timeout = kwargs.get("timeout")
    assert isinstance(timeout, aiohttp.ClientTimeout)
    assert timeout.total == 40


async def test_send_notification_session_has_timeout() -> None:
    """ClientSession for sendMessage in send_notification must use total=10."""
    gw = _make_gateway()
    mock_session = _make_http_mock({"ok": True})
    with patch(
        "src.notifications.telegram_gateway.aiohttp.ClientSession",
        return_value=mock_session,
    ) as mock_cls:
        await gw.send_notification("hello")
    _, kwargs = mock_cls.call_args
    timeout = kwargs.get("timeout")
    assert isinstance(timeout, aiohttp.ClientTimeout)
    assert timeout.total == 10


async def test_send_notification_uses_markdown_v2_parse_mode() -> None:
    """ClientSession for sendMessage in send_notification must use parse_mode MarkdownV2."""
    gw = _make_gateway()
    mock_session = _make_http_mock({"ok": True})
    with patch(
        "src.notifications.telegram_gateway.aiohttp.ClientSession",
        return_value=mock_session,
    ):
        await gw.send_notification("hello")
    payload = mock_session.post.call_args[1]["json"]
    assert payload["parse_mode"] == "MarkdownV2"
