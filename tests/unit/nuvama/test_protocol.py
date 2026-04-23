"""Tests for NuvamaClient protocol and MockNuvamaClient.

Verifies that:
1. MockNuvamaClient structurally satisfies the NuvamaClient protocol.
2. Fixture JSON is returned verbatim.
3. Defaults produce valid empty-JSON strings.
"""
from __future__ import annotations

import json

import pytest

from src.nuvama.mock_client import MockNuvamaClient
from src.nuvama.protocol import NuvamaClient


class TestNuvamaClientProtocol:
    def test_mock_client_satisfies_protocol(self) -> None:
        """MockNuvamaClient must be an instance of the runtime_checkable protocol."""
        mock = MockNuvamaClient()
        assert isinstance(mock, NuvamaClient)

    def test_mock_client_returns_configured_holdings(self) -> None:
        fixture = '{"data": [{"isin": "INF001"}]}'
        mock = MockNuvamaClient(holdings_json=fixture)
        assert mock.Holdings() == fixture

    def test_mock_client_returns_configured_net_position(self) -> None:
        fixture = '{"pos": [{"trade_symbol": "NIFTY24DEC24000CE"}]}'
        mock = MockNuvamaClient(net_position_json=fixture)
        assert mock.NetPosition() == fixture

    def test_mock_client_defaults_to_empty_json(self) -> None:
        mock = MockNuvamaClient()
        assert json.loads(mock.Holdings()) == {}
        assert json.loads(mock.NetPosition()) == {}

    def test_mock_client_holdings_and_position_independent(self) -> None:
        """Holdings and NetPosition fixtures are stored independently."""
        h_fixture = '{"holdings": true}'
        np_fixture = '{"positions": true}'
        mock = MockNuvamaClient(holdings_json=h_fixture, net_position_json=np_fixture)
        assert mock.Holdings() == h_fixture
        assert mock.NetPosition() == np_fixture
        assert mock.Holdings() != mock.NetPosition()
