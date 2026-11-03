"""Tests for the pre-call Dhan token guard (offline, no real token)."""

from datetime import timedelta

import pytest
import structlog

from src.client.chain_source import ChainRouter
from src.client.dhan_token_guard import DhanTokenGuard, TokenGuardedChainSource, notifier_alert
from src.client.exceptions import AuthenticationError
from src.client.source_health import SourceHealth
from src.models.contract import SourceId
from tests.unit.auth.test_dhan_token import NOW, make_jwt
from tests.unit.client.test_chain_source import GOOD, FakeChainSource, snap

SECRET_TAIL = "SECRETSIG"  # pragma: allowlist secret


class Inner:
    def __init__(self) -> None:
        self.calls = 0

    async def get_chain(self, underlying: str, expiry: str) -> str:
        self.calls += 1
        return "snap"


class Notifier:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_plain_message(self, text: str) -> bool:
        self.sent.append(text)
        return True

    async def send_approval_request(self, event: object, context_str: str) -> None:
        return None


def build(
    token: str | None, notifier: Notifier | None = None
) -> tuple[TokenGuardedChainSource, Inner, SourceHealth, Notifier]:
    notifier = notifier or Notifier()
    health = SourceHealth(alert=notifier_alert(notifier), clock=lambda: 0.0)
    guard = DhanTokenGuard(health, lambda: token, clock=lambda: NOW)
    inner = Inner()
    return TokenGuardedChainSource(inner, guard), inner, health, notifier


async def test_valid_token_passes_through() -> None:
    src, inner, health, notifier = build(make_jwt(NOW + timedelta(hours=9)))
    assert await src.get_chain("NIFTY", "2026-12-29") == "snap"
    assert inner.calls == 1 and notifier.sent == []
    assert not health.is_unhealthy(SourceId.DHAN, "chain")


async def test_stale_token_alerts_once_and_blocks_the_call() -> None:
    token = make_jwt(NOW - timedelta(hours=32), NOW - timedelta(hours=56)) + SECRET_TAIL
    src, inner, health, notifier = build(token)
    for _ in range(3):
        with pytest.raises(AuthenticationError):
            await src.get_chain("NIFTY", "2026-12-29")
    assert inner.calls == 0
    assert len(notifier.sent) == 1 and "expired" in notifier.sent[0]
    assert health.is_unhealthy(SourceId.DHAN, "chain")
    assert token not in notifier.sent[0] and SECRET_TAIL not in notifier.sent[0]


async def test_missing_token_alerts_once() -> None:
    src, inner, _, notifier = build(None)
    for _ in range(2):
        with pytest.raises(AuthenticationError):
            await src.get_chain("NIFTY", "2026-12-29")
    assert inner.calls == 0 and len(notifier.sent) == 1 and "missing" in notifier.sent[0]


async def test_router_falls_back_to_upstox_on_stale_token() -> None:
    dhan, dhan_inner, health, notifier = build(None)
    upstox = FakeChainSource(snap(GOOD))
    router = ChainRouter([(SourceId.DHAN, dhan), (SourceId.UPSTOX, upstox)], health=health)
    result = await router.get_chain("NIFTY", "2026-12-29")
    assert result.greeks_source is SourceId.UPSTOX
    assert dhan_inner.calls == 0 and len(notifier.sent) == 1


async def test_token_renewal_is_picked_up_without_restart() -> None:
    tokens = [None, make_jwt(NOW + timedelta(hours=20))]
    health = SourceHealth(clock=lambda: 0.0)
    guard = DhanTokenGuard(health, lambda: tokens[0], clock=lambda: NOW)
    with pytest.raises(AuthenticationError):
        await guard.ensure_usable()
    tokens[0] = tokens[1]
    await guard.ensure_usable()


async def test_notifier_failure_does_not_raise() -> None:
    class Boom(Notifier):
        async def send_plain_message(self, text: str) -> bool:
            raise RuntimeError("telegram down")

    src, inner, _, _ = build(None, Boom())
    with pytest.raises(AuthenticationError):  # the auth error, not the notifier's
        await src.get_chain("NIFTY", "2026-12-29")
    assert inner.calls == 0


async def test_token_never_appears_in_captured_logs() -> None:
    token = make_jwt(NOW - timedelta(hours=1)) + SECRET_TAIL
    src, *_ = build(token)
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(AuthenticationError):
            await src.get_chain("NIFTY", "2026-12-29")
    assert logs and SECRET_TAIL not in repr(logs) and token not in repr(logs)
