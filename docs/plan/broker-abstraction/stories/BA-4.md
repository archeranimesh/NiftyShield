# BA-4 — Dhan `InstrumentKeyAdapter` implementation

> Assigned to: Antigravity
> Phase: 2 — Dhan Integration
> Priority: LOW
> Blocked by: BA-2 must be merged first. Can run in parallel with BA-3.

---

## Goal

Implement `DhanInstrumentKeyAdapter` — an `InstrumentKeyAdapter` that translates between
Dhan's numeric `securityId` strings and the canonical `NSE_FO|<token>` key format.

Translation is lookup-table driven, backed by a CSV mapping file that pairs Dhan security IDs
with Upstox instrument tokens. The mapping file is generated offline (see note below) and
committed to `data/instruments/dhan_key_map.csv`. It is never modified at runtime.

**Stored keys are never mutated.** The adapter translates at the API boundary only.

---

## Mapping file

`data/instruments/dhan_key_map.csv` — columns:

```
dhan_security_id,canonical_key,symbol,expiry,strike,option_type
49081,NSE_FO|79653,NIFTY,2026-06-26,23000,CE
...
```

The file does not exist yet — create a minimal 4-row sample (2 strikes × CE/PE) for testing.
Production population is a separate operational task (not part of this story).

---

## Files to change

| File | Action |
|------|--------|
| `src/client/adapters/dhan.py` | New — `DhanInstrumentKeyAdapter` |
| `data/instruments/dhan_key_map.csv` | New — sample mapping (4 rows + header) |
| `tests/unit/client/test_adapters_dhan.py` | New — adapter tests |
| `tests/fixtures/instruments/dhan_key_map_fixture.csv` | New — test fixture (4 rows) |

---

## What to implement

### `src/client/adapters/dhan.py`

```python
class DhanInstrumentKeyAdapter:
    """InstrumentKeyAdapter for Dhan numeric securityId ↔ canonical key translation.

    Loads the mapping from a CSV file at construction time. Raises FileNotFoundError
    if the CSV does not exist. Both directions are O(1) lookup via pre-built dicts.
    """

    def __init__(self, map_path: Path) -> None:
        self._dhan_to_canonical: dict[str, str] = {}
        self._canonical_to_dhan: dict[str, str] = {}
        self._load(map_path)

    def _load(self, map_path: Path) -> None:
        # Read CSV, populate both dicts
        ...

    def to_broker(self, canonical_key: str) -> str:
        # canonical → dhan security ID
        ...

    def to_canonical(self, broker_symbol: str) -> str:
        # dhan security ID → canonical key
        ...
```

Both `to_broker` and `to_canonical` raise `KeyError` with a descriptive message when the
key is not found in the map. Do not silently return the input.

---

## Tests — `tests/unit/client/test_adapters_dhan.py`

Use `tests/fixtures/instruments/dhan_key_map_fixture.csv` (4-row fixture) for all tests —
never reference `data/instruments/dhan_key_map.csv` in unit tests.

1. **Happy path `to_canonical`:** known Dhan security ID → correct canonical key.
2. **Happy path `to_broker`:** known canonical key → correct Dhan security ID.
3. **Round-trip:** `to_canonical(to_broker(canonical_key)) == canonical_key` for all fixture rows.
4. **Unknown `to_canonical`:** unknown Dhan ID → raises `KeyError`.
5. **Unknown `to_broker`:** unknown canonical key → raises `KeyError`.
6. **Missing CSV:** `DhanInstrumentKeyAdapter(Path("/nonexistent.csv"))` → raises `FileNotFoundError`.
7. **`isinstance` check:** `isinstance(DhanInstrumentKeyAdapter(fixture_path), InstrumentKeyAdapter)` → `True`.

---

## Commit message

```
feat(client): Dhan InstrumentKeyAdapter + sample key map

Why: provides the canonical ↔ Dhan securityId translation layer without mutating stored keys.
What:
- src/client/adapters/dhan.py: DhanInstrumentKeyAdapter with O(1) bidirectional lookup
- data/instruments/dhan_key_map.csv: 4-row sample mapping (production population is separate)
- tests/unit/client/test_adapters_dhan.py: 7 adapter tests
- tests/fixtures/instruments/dhan_key_map_fixture.csv: test fixture
Ref: docs/plan/broker-abstraction/stories/BA-4.md
```

---

## Pre-baked graph context

```
search_graph("InstrumentKeyAdapter")      # protocol — confirm BA-2 shipped
search_graph("UpstoxInstrumentKeyAdapter") # reference implementation
search_graph("instrument_key")             # confirm field name convention in models
```

Also check `REFERENCES.md` for Upstox instrument key format examples before writing the CSV.
