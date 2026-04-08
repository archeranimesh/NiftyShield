"""Unit tests for src/client/factory.py — fully offline.

All prod/sandbox tests monkeypatch UpstoxLiveClient.__init__ to avoid any
token validation or UpstoxMarketClient instantiation.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.client.factory import VALID_ENVS, create_client
from src.client.mock_client import MockBrokerClient
from src.client.protocol import BrokerClient
from src.client.upstox_live import UpstoxLiveClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_live_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace UpstoxLiveClient.__init__ with a no-op to avoid token setup."""
    monkeypatch.setattr(
        UpstoxLiveClient,
        "__init__",
        lambda self, token=None: setattr(self, "_market", None),
    )


# ---------------------------------------------------------------------------
# env="test"
# ---------------------------------------------------------------------------


class TestCreateClientTest:
    def test_returns_mock_broker_client(self) -> None:
        client = create_client("test")
        assert isinstance(client, MockBrokerClient)

    def test_initial_margin_forwarded(self) -> None:
        client = create_client("test", initial_margin=100_000.0)
        assert isinstance(client, MockBrokerClient)
        assert client._margin_available == Decimal("100000.0")

    def test_satisfies_broker_client_protocol(self) -> None:
        client = create_client("test")
        assert isinstance(client, BrokerClient)


# ---------------------------------------------------------------------------
# env="prod"
# ---------------------------------------------------------------------------


class TestCreateClientProd:
    def test_returns_upstox_live_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_live_init(monkeypatch)
        client = create_client("prod", token="fake-prod-token")
        assert isinstance(client, UpstoxLiveClient)

    def test_satisfies_broker_client_protocol(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_live_init(monkeypatch)
        client = create_client("prod", token="fake-prod-token")
        assert isinstance(client, BrokerClient)


# ---------------------------------------------------------------------------
# env="sandbox"
# ---------------------------------------------------------------------------


class TestCreateClientSandbox:
    def test_returns_upstox_live_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_live_init(monkeypatch)
        client = create_client("sandbox", token="fake-sandbox-token")
        assert isinstance(client, UpstoxLiveClient)

    def test_satisfies_broker_client_protocol(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_live_init(monkeypatch)
        client = create_client("sandbox", token="fake-sandbox-token")
        assert isinstance(client, BrokerClient)

    def test_falls_back_to_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_live_init(monkeypatch)
        monkeypatch.setenv("UPSTOX_SANDBOX_TOKEN", "env-sandbox-token")
        # No token= kwarg — should pick up the env var without error.
        client = create_client("sandbox")
        assert isinstance(client, UpstoxLiveClient)


# ---------------------------------------------------------------------------
# Invalid env
# ---------------------------------------------------------------------------


class TestCreateClientInvalidEnv:
    def test_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="unknown"):
            create_client("unknown")

    def test_error_message_contains_valid_envs_hint(self) -> None:
        with pytest.raises(ValueError, match="prod"):
            create_client("bad-env")
