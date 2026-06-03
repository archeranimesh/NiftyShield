# BA-2 — Define `InstrumentKeyAdapter` protocol + Upstox adapter

> Assigned to: Claude
> Phase: 1 — Parser Protocol + Upstox Conformance
> Priority: LOW
> Blocked by: BA-1 must be merged first

---

## Goal

Introduce a typed `InstrumentKeyAdapter` protocol to normalize the impedance mismatch
between the canonical instrument key format (Upstox-style `NSE_FO|<token>`) and
broker-native symbol formats (Dhan numeric IDs, Kite `NFO:NIFTY24JUN23000CE` strings, etc.).

Adapters translate **at fetch time only**. Stored keys (`instrument_key` in DB and Parquet)
are never mutated — they remain Upstox-format strings, as established in `REFERENCES.md`.
This is a one-way translation: broker-native → canonical on ingest; canonical → broker-native
when placing orders.

---

## Files to change

| File | Action |
|------|--------|
| `src/client/adapters/__init__.py` | New package (single comment line) |
| `src/client/adapters/protocol.py` | New — `InstrumentKeyAdapter` protocol |
| `src/client/adapters/upstox.py` | New — Upstox adapter (identity: keys are already canonical) |
| `tests/unit/client/test_adapters_protocol.py` | New — protocol conformance + Upstox adapter tests |

---

## What to implement

### `src/client/adapters/protocol.py`

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class InstrumentKeyAdapter(Protocol):
    """Translates between canonical instrument keys and broker-native symbols.

    Canonical key format: Upstox-style "EXCHANGE_SEGMENT|TOKEN" e.g. "NSE_FO|79653".
    This format is stored in DB and Parquet — it must never be altered at rest.

    Adapters perform translation only at the API boundary:
    - to_broker(canonical_key) called before placing an order via broker API.
    - to_canonical(broker_symbol) called when ingesting broker-native data.
    """

    def to_broker(self, canonical_key: str) -> str:
        """Convert canonical instrument key to broker-native symbol.

        Args:
            canonical_key: Upstox-style key, e.g. "NSE_FO|79653".

        Returns:
            Broker-native symbol string.

        Raises:
            KeyError: If the canonical key is not found in the broker's lookup.
        """
        ...

    def to_canonical(self, broker_symbol: str) -> str:
        """Convert broker-native symbol to canonical instrument key.

        Args:
            broker_symbol: Broker-native symbol, e.g. Dhan numeric security ID.

        Returns:
            Canonical key string in "EXCHANGE_SEGMENT|TOKEN" format.

        Raises:
            KeyError: If the broker symbol has no known canonical mapping.
        """
        ...
```

### `src/client/adapters/upstox.py`

Upstox keys are already canonical — the adapter is an identity transform:

```python
class UpstoxInstrumentKeyAdapter:
    """InstrumentKeyAdapter for Upstox — keys are already in canonical format."""

    def to_broker(self, canonical_key: str) -> str:
        return canonical_key

    def to_canonical(self, broker_symbol: str) -> str:
        return broker_symbol
```

Simple, but important: it makes the Upstox adapter interchangeable with Dhan/Kite adapters
in `factory.py` without special-casing.

---

## Tests — `tests/unit/client/test_adapters_protocol.py`

1. **Protocol conformance:** `isinstance(UpstoxInstrumentKeyAdapter(), InstrumentKeyAdapter)` → `True`.
2. **Identity round-trip:** `adapter.to_broker(key) == key` and `adapter.to_canonical(key) == key` for a sample Upstox key.
3. **Non-conforming class:** a class with only `to_broker` (missing `to_canonical`) does not satisfy the protocol.
4. **Structural conformance:** a third-party class with both methods but no explicit inheritance satisfies `isinstance(..., InstrumentKeyAdapter)`.

---

## Commit message

```
feat(client): introduce InstrumentKeyAdapter protocol + Upstox identity adapter

Why: establishes the translation seam for broker-native ↔ canonical instrument keys
     without mutating stored keys in DB or Parquet.
What:
- src/client/adapters/__init__.py: new package stub
- src/client/adapters/protocol.py: InstrumentKeyAdapter runtime-checkable Protocol
- src/client/adapters/upstox.py: UpstoxInstrumentKeyAdapter (identity transform)
- tests/unit/client/test_adapters_protocol.py: 4 conformance tests
Ref: docs/plan/broker-abstraction/stories/BA-2.md
```

---

## Pre-baked graph context

```
search_graph("BrokerClient")        # mirror the @runtime_checkable Protocol pattern
search_graph("instrument_key")      # confirm field name in OptionLeg / trades table
search_graph("MarketDataParser")    # confirm BA-1 shipped before starting this task
```

Expected: `instrument_key` appears on `OptionLeg` (str field) and in `trades` SQLite table.
`MarketDataParser` must exist before starting — abort if graph returns zero results.
