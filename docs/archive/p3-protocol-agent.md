---
model: claude-sonnet-4-5
description: P3 Nuvama protocol abstraction — AR-9a. Creates NuvamaClient protocol and MockNuvamaClient. Only touches src/nuvama/ and tests/. Safe to run in parallel with p3-sql-agent and p3-script-hygiene-agent.
---

You are executing Phase 1, Stream B of the P3 sprint for NiftyShield.

## Your Scope (files you may touch)

- `src/nuvama/protocol.py` — NEW
- `src/nuvama/mock_client.py` — NEW (not in tests/)
- `src/nuvama/reader.py` — type annotation only
- `src/nuvama/options_reader.py` — type annotation only (check if `api` param exists)
- `tests/unit/nuvama/test_protocol.py` — NEW

**Do NOT touch:** `scripts/`, `src/portfolio/`, `src/auth/`. Script wiring (AR-9b) is Phase 2.

---

## AR-9a: NuvamaClient Protocol Core

### Design decisions (read before coding)

**`@runtime_checkable` + normal import (not `TYPE_CHECKING`):**
The protocol is marked `@runtime_checkable` so `isinstance(mock, NuvamaClient)` works in tests.
This means `NuvamaClient` must be importable at runtime — do **not** guard the import in `reader.py` with `TYPE_CHECKING`. Use a plain import instead:

```python
# reader.py — correct
from src.nuvama.protocol import NuvamaClient  # normal import, not TYPE_CHECKING
```

**`MockNuvamaClient` lives in `src/nuvama/`, not `tests/`:**
This matches the project convention — `MockBrokerClient` lives in `src/client/mock_client.py`.
Any script or test can import it without coupling to the test tree.

---

### Step 1 — Create `src/nuvama/protocol.py`

```python
"""NuvamaClient protocol — abstracts Nuvama APIConnect SDK.

All callers accept NuvamaClient instead of the concrete APIConnect class,
enabling offline testing via MockNuvamaClient without importing the SDK.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class NuvamaClient(Protocol):
    """Minimal protocol over the Nuvama APIConnect SDK.

    Only Holdings() and NetPosition() are used in production.
    """

    def Holdings(self) -> str:  # noqa: N802
        """Return raw Holdings() response as a JSON string."""
        ...

    def NetPosition(self) -> str:  # noqa: N802
        """Return raw NetPosition() response as a JSON string."""
        ...
```

### Step 2 — Create `src/nuvama/mock_client.py`

```python
"""MockNuvamaClient — offline substitute for the Nuvama APIConnect SDK."""
from __future__ import annotations

import json


class MockNuvamaClient:
    """Satisfies the NuvamaClient protocol, returning fixture JSON strings.

    Lives in src/ (not tests/) so scripts and integration tests can import it
    without coupling to the test directory tree. Follows the same convention
    as MockBrokerClient in src/client/mock_client.py.

    Usage:
        from src.nuvama.mock_client import MockNuvamaClient
        mock = MockNuvamaClient(holdings_json=FIXTURE, net_position_json=FIXTURE)
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
        return self._holdings

    def NetPosition(self) -> str:  # noqa: N802
        return self._net_position
```

### Step 3 — Update `src/nuvama/reader.py`

```python
# Add at top of file (normal import — NOT under TYPE_CHECKING)
from src.nuvama.protocol import NuvamaClient

# Change fetch_nuvama_portfolio signature only:
def fetch_nuvama_portfolio(
    api: NuvamaClient,    # was: Any
    positions: dict[str, Decimal],
    snapshot_date: date,
    exclude_isins: frozenset[str] | None = None,
) -> NuvamaBondSummary:
    ...
```

Remove `Any` from the import if it's no longer used elsewhere in the file.

### Step 4 — Check `src/nuvama/options_reader.py`

Use `get_code_snippet` to inspect. If any function takes `api: Any`, apply the same `NuvamaClient` annotation.

### Step 5 — Tests in `tests/unit/nuvama/test_protocol.py`

```python
from src.nuvama.protocol import NuvamaClient
from src.nuvama.mock_client import MockNuvamaClient

def test_mock_client_satisfies_protocol():
    assert isinstance(MockNuvamaClient(), NuvamaClient)

def test_mock_client_returns_configured_holdings():
    mock = MockNuvamaClient(holdings_json='{"data": []}')
    assert mock.Holdings() == '{"data": []}'

def test_mock_client_returns_configured_net_position():
    mock = MockNuvamaClient(net_position_json='{"pos": []}')
    assert mock.NetPosition() == '{"pos": []}'

def test_mock_client_defaults_to_empty_json():
    mock = MockNuvamaClient()
    import json
    assert json.loads(mock.Holdings()) == {}
    assert json.loads(mock.NetPosition()) == {}
```

---

## Protocol

1. `get_code_snippet` on `fetch_nuvama_portfolio` and any function in `options_reader.py` with an `api` param.
2. Run `python -m pytest tests/unit/nuvama/ -v` — baseline green.
3. Create `src/nuvama/protocol.py`.
4. Create `src/nuvama/mock_client.py`.
5. Update `reader.py` + `options_reader.py` signatures.
6. Create `tests/unit/nuvama/test_protocol.py`.
7. Run `python -m pytest tests/unit/nuvama/ -v` — all green.
8. Run `python -m pytest tests/unit/ -v --tb=short` — 859+ passing.
9. One commit: `refactor(nuvama): introduce NuvamaClient protocol and MockNuvamaClient`.
