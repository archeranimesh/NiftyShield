"""Tests for create_broker_client alias in src/client/factory.py.

Regression guard: paper_snapshot.py imports ``create_broker_client`` from
``src.client.factory``.  This alias must remain importable and must delegate
correctly to the underlying ``create_client`` implementation.
"""

from __future__ import annotations

import pytest

from src.client.factory import create_broker_client
from src.client.mock_client import MockBrokerClient
from src.client.protocol import BrokerClient
from src.client.upstox_live import UpstoxLiveClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_live_init(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        UpstoxLiveClient,
        "__init__",
        lambda self, token=None: setattr(self, "_market", None),
    )


# ---------------------------------------------------------------------------
# create_broker_client alias
# ---------------------------------------------------------------------------


class TestCreateBrokerClientAlias:
    """create_broker_client must be a transparent alias for create_client."""

    def test_test_env_returns_mock_broker_client(self) -> None:
        """Happy path: alias works for the offline test env."""
        client = create_broker_client(env="test")
        assert isinstance(client, MockBrokerClient)

    def test_satisfies_broker_client_protocol(self) -> None:
        """Returned object must satisfy the BrokerClient protocol."""
        client = create_broker_client(env="test")
        assert isinstance(client, BrokerClient)

    def test_prod_env_returns_upstox_live_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Happy path: alias works for prod (stubbed init, no real token needed)."""
        _stub_live_init(monkeypatch)
        client = create_broker_client(env="prod", token="fake-token")
        assert isinstance(client, UpstoxLiveClient)

    def test_invalid_env_raises_value_error(self) -> None:
        """Edge case: invalid env must raise ValueError, same as create_client."""
        with pytest.raises(ValueError, match="unknown"):
            create_broker_client(env="unknown")
