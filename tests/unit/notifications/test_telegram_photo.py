"""Unit tests for TelegramNotifier.send_photo — fully offline, aiohttp patched."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.notifications.telegram import TelegramNotifier

_PNG = b"\x89PNG\r\n\x1a\nfake"


def _session_mock(status: int = 200, data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=data if data is not None else {"ok": True})
    resp.text = AsyncMock(return_value="bad request")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.post.return_value = resp
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


def _notifier(budget: int = 10) -> TelegramNotifier:
    return TelegramNotifier(bot_token="tok", chat_id="42", budget=budget)


async def _fields_sent(caption: str) -> tuple[MagicMock, dict[str, tuple]]:
    session = _session_mock()
    with (
        patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session),
        patch("src.notifications.telegram.aiohttp.FormData") as form_cls,
    ):
        await _notifier().send_photo(_PNG, caption=caption)
    calls = form_cls.return_value.add_field.call_args_list
    return session, {c.args[0]: (c.args[1], c.kwargs) for c in calls}


@pytest.mark.asyncio
async def test_send_photo_posts_multipart() -> None:
    session, fields = await _fields_sent("cap")
    assert session.post.call_args.args[0].endswith("/sendPhoto")
    assert fields["chat_id"][0] == "42"
    assert fields["photo"][0] == _PNG
    assert fields["photo"][1] == {"filename": "payoff.png", "content_type": "image/png"}
    assert fields["caption"][0] == "cap"
    assert fields["parse_mode"][0] == "MarkdownV2"


@pytest.mark.asyncio
async def test_send_photo_omits_caption_fields_when_empty() -> None:
    _, fields = await _fields_sent("")
    assert set(fields) == {"chat_id", "photo"}


@pytest.mark.asyncio
async def test_send_photo_ok_false_is_non_fatal() -> None:
    session = _session_mock(data={"ok": False, "description": "photo too large"})
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session):
        with patch("src.notifications.telegram.logger") as log:
            assert await _notifier().send_photo(_PNG) is False
    assert log.warning.call_args.args[0] == "telegram.send_photo.failed"


@pytest.mark.asyncio
async def test_eod_run_sends_all_text_and_photos() -> None:
    """8 text + 8 photos all deliver on a budget of 8: photos do not eat the text budget."""
    session = _session_mock()
    n = _notifier(budget=8)
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session):
        results = []
        for _ in range(8):
            results.append(await n.send("report"))
            results.append(await n.send_photo(_PNG))
    assert all(results)
    assert session.post.call_count == 16


@pytest.mark.asyncio
async def test_budget_still_caps_runaway() -> None:
    """Both caps still bind: extra texts and extra photos are suppressed independently."""
    session = _session_mock()
    n = TelegramNotifier(bot_token="tok", chat_id="42", budget=2, photo_budget=3)
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session):
        texts = [await n.send("t") for _ in range(5)]
        photos = [await n.send_photo(_PNG) for _ in range(5)]
    assert texts == [True, True, False, False, False]
    assert photos == [True, True, True, False, False]
    assert session.post.call_count == 5


@pytest.mark.asyncio
async def test_send_photo_non_200_is_non_fatal() -> None:
    session = _session_mock(status=400)
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session):
        with patch("src.notifications.telegram.logger") as log:
            ok = await _notifier().send_photo(_PNG)
    assert ok is False
    assert log.warning.call_args.args[0] == "telegram.send_photo.failed"


@pytest.mark.asyncio
async def test_send_photo_transport_error_is_non_fatal() -> None:
    session = _session_mock()
    session.post.side_effect = RuntimeError("boom")
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session):
        assert await _notifier().send_photo(_PNG) is False


@pytest.mark.asyncio
async def test_send_photo_respects_budget() -> None:
    session = _session_mock()
    n = _notifier(budget=0)
    with patch("src.notifications.telegram.aiohttp.ClientSession", return_value=session) as cs:
        assert await n.send_photo(_PNG) is False
    cs.assert_not_called()
    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_gateway_send_photo_delegates() -> None:
    from src.notifications.telegram_gateway import TelegramGateway

    gw = TelegramGateway("tok", "42", ":memory:")
    gw._notifier = MagicMock(send_photo=AsyncMock(return_value=True))
    await gw.send_photo(_PNG, caption="cap")
    gw._notifier.send_photo.assert_awaited_once_with(_PNG, caption="cap")


@pytest.mark.asyncio
async def test_gateway_send_photo_non_fatal() -> None:
    from src.notifications.telegram_gateway import TelegramGateway

    gw = TelegramGateway("tok", "42", ":memory:")
    gw._notifier = MagicMock(send_photo=AsyncMock(side_effect=RuntimeError("boom")))
    await gw.send_photo(_PNG)
