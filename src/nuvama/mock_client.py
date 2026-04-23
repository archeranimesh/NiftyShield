"""MockNuvamaClient — offline substitute for the Nuvama APIConnect SDK.

Lives in src/nuvama/ (not tests/) so scripts and integration tests can import
it without coupling to the test directory tree. Follows the same convention
as MockBrokerClient in src/client/mock_client.py.
"""
from __future__ import annotations

import json


class MockNuvamaClient:
    """Satisfies the NuvamaClient protocol, returning fixture JSON strings.

    Usage:
        from src.nuvama.mock_client import MockNuvamaClient
        mock = MockNuvamaClient(
            holdings_json=HOLDINGS_FIXTURE,
            net_position_json=NETPOS_FIXTURE,
        )
        result = fetch_nuvama_portfolio(mock, positions, date.today())
    """

    def __init__(
        self,
        holdings_json: str | None = None,
        net_position_json: str | None = None,
    ) -> None:
        self._holdings = holdings_json or json.dumps({})
        self._net_position = net_position_json or json.dumps({})

    def Holdings(self) -> str:  # noqa: N802
        """Return configured holdings fixture JSON string."""
        return self._holdings

    def NetPosition(self) -> str:  # noqa: N802
        """Return configured net position fixture JSON string."""
        return self._net_position
