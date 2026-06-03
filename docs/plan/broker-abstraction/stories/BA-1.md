# BA-1 — Define `MarketDataParser` protocol + move Upstox parser to conform

> Assigned to: Claude
> Phase: 1 — Parser Protocol + Upstox Conformance
> Priority: LOW

---

## Goal

Introduce a typed `MarketDataParser` protocol as the standard interface for converting
broker-native option chain responses into the canonical `OptionChain` model. Move the
existing Upstox parser to conform to this protocol without changing any downstream consumer.

**Storage is frozen.** `src/models/options.py` is read-only for this task.
No Parquet schema, SQLite schema, or model field names change.

---

## Files to change

| File | Action |
|------|--------|
| `src/client/parsers/__init__.py` | New package (single comment line) |
| `src/client/parsers/protocol.py` | New — `MarketDataParser` protocol |
| `src/client/parsers/upstox.py` | New — move `parse_upstox_option_chain` here, conforming to protocol |
| `src/client/upstox_market.py` | Keep existing function; add deprecation shim that delegates to new module |
| `tests/unit/client/test_parsers_protocol.py` | New — protocol conformance tests |

---

## What to implement

### `src/client/parsers/protocol.py`

```python
from typing import Protocol, runtime_checkable
from src.models.options import OptionChain

@runtime_checkable
class MarketDataParser(Protocol):
    """Converts broker-native option chain payload to canonical OptionChain.

    Implementors must not expose broker-specific field names past this boundary.
    The returned OptionChain is the sole representation used by storage, paper
    trading, and backtests — its schema is frozen.
    """

    def parse_option_chain(self, raw: dict) -> OptionChain:
        """Parse a broker-native option chain response.

        Args:
            raw: The raw response dict as returned by the broker API.

        Returns:
            Canonical OptionChain. All monetary/price fields use Decimal.

        Raises:
            ValueError: If the payload is missing required fields or is malformed.
        """
        ...
```

`@runtime_checkable` is required so `isinstance(parser, MarketDataParser)` works in
`factory.py` guard clauses.

### `src/client/parsers/upstox.py`

Move the body of `parse_upstox_option_chain` from `src/client/upstox_market.py` into a
class `UpstoxMarketDataParser` that implements `MarketDataParser`:

```python
class UpstoxMarketDataParser:
    """MarketDataParser implementation for Upstox option chain API responses."""

    def parse_option_chain(self, raw: dict) -> OptionChain:
        # existing logic verbatim — do not alter field names or Decimal handling
        ...
```

The class must satisfy `isinstance(UpstoxMarketDataParser(), MarketDataParser)`.

### `src/client/upstox_market.py` — deprecation shim

Keep `parse_upstox_option_chain` as a module-level function for backward compatibility.
Delegate to `UpstoxMarketDataParser`:

```python
import warnings
from src.client.parsers.upstox import UpstoxMarketDataParser

_parser = UpstoxMarketDataParser()

def parse_upstox_option_chain(raw: dict) -> OptionChain:
    """Deprecated: use UpstoxMarketDataParser directly."""
    warnings.warn(
        "parse_upstox_option_chain is deprecated; use UpstoxMarketDataParser",
        DeprecationWarning,
        stacklevel=2,
    )
    return _parser.parse_option_chain(raw)
```

Existing callers (`scripts/pipeline/upstox_chain_snapshot.py` etc.) continue to work
unchanged — the shim is the migration path.

---

## Tests — `tests/unit/client/test_parsers_protocol.py`

1. **Happy path:** `isinstance(UpstoxMarketDataParser(), MarketDataParser)` → `True`.
2. **Protocol structural check:** a class with `parse_option_chain(self, raw: dict) -> OptionChain` satisfies the protocol even without explicit inheritance.
3. **Non-conforming class:** a class without `parse_option_chain` does **not** satisfy `isinstance(..., MarketDataParser)`.
4. **Shim delegation:** calling `parse_upstox_option_chain(raw)` with a valid fixture returns the same result as `UpstoxMarketDataParser().parse_option_chain(raw)`.
5. **Shim deprecation warning:** calling `parse_upstox_option_chain` emits `DeprecationWarning`.

Use the fixture from `tests/fixtures/responses/` for the Upstox chain payload.
No network calls.

---

## Commit message

```
feat(client): introduce MarketDataParser protocol + conform Upstox parser

Why: establishes the seam for multi-broker option chain parsing without touching
     canonical models or downstream storage consumers.
What:
- src/client/parsers/__init__.py: new package stub
- src/client/parsers/protocol.py: MarketDataParser runtime-checkable Protocol
- src/client/parsers/upstox.py: UpstoxMarketDataParser conforming to protocol
- src/client/upstox_market.py: deprecation shim delegating to new class
- tests/unit/client/test_parsers_protocol.py: 5 conformance + shim tests
Ref: docs/plan/broker-abstraction/stories/BA-1.md
```

---

## Pre-baked graph context

Run these before opening any source file:

```
search_graph("parse_upstox_option_chain")   # callers + current location
search_graph("OptionChain")                 # canonical model fields
search_graph("BrokerClient")               # existing protocol pattern to mirror
```

Expected: `parse_upstox_option_chain` lives in `src/client/upstox_market.py`;
`OptionChain` is in `src/models/options.py` (frozen Pydantic); `BrokerClient` is in
`src/client/protocol.py` as a `@runtime_checkable Protocol` — mirror that pattern exactly.
