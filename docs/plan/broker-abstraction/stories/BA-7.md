# BA-7 — Kite `InstrumentKeyAdapter` implementation

> Assigned to: Antigravity
> Phase: 3 — Kite/Zerodha Integration
> Priority: LOW
> Blocked by: BA-2 must be merged first. Can run in parallel with BA-6.

---

## Goal

Implement `KiteInstrumentKeyAdapter` — translates between Kite's numeric `instrument_token`
(int, stored as string) and the canonical `NSE_FO|<token>` key format.

Same pattern as `DhanInstrumentKeyAdapter` (BA-4): CSV-backed, bidirectional, O(1) lookup.

---

## Mapping file

`data/instruments/kite_key_map.csv` — columns:

```
kite_instrument_token,canonical_key,symbol,expiry,strike,option_type
12345678,NSE_FO|79653,NIFTY,2026-06-26,23000,CE
...
```

Create a minimal 4-row sample (2 strikes × CE/PE) for testing. Production population is a
separate operational task (not part of this story).

---

## Files to change

| File | Action |
|------|--------|
| `src/client/adapters/kite.py` | New — `KiteInstrumentKeyAdapter` |
| `data/instruments/kite_key_map.csv` | New — sample mapping (4 rows + header) |
| `tests/unit/client/test_adapters_kite.py` | New — adapter tests |
| `tests/fixtures/instruments/kite_key_map_fixture.csv` | New — test fixture (4 rows) |

---

## What to implement

Mirror `DhanInstrumentKeyAdapter` exactly — substitute `kite_instrument_token` for
`dhan_security_id` as the broker-side key column.

`to_broker` converts canonical `NSE_FO|<token>` → Kite instrument token string.
`to_canonical` converts Kite instrument token string → canonical key.
Both raise `KeyError` with descriptive message on miss.

---

## Tests — `tests/unit/client/test_adapters_kite.py`

Mirror BA-4 test list exactly:
1. Happy path `to_canonical`
2. Happy path `to_broker`
3. Round-trip
4. Unknown `to_canonical` → `KeyError`
5. Unknown `to_broker` → `KeyError`
6. Missing CSV → `FileNotFoundError`
7. `isinstance` check → `True`

---

## Commit message

```
feat(client): Kite InstrumentKeyAdapter + sample key map

Why: provides canonical ↔ Kite instrument_token translation without mutating stored keys.
What:
- src/client/adapters/kite.py: KiteInstrumentKeyAdapter with O(1) bidirectional lookup
- data/instruments/kite_key_map.csv: 4-row sample mapping
- tests/unit/client/test_adapters_kite.py: 7 adapter tests
- tests/fixtures/instruments/kite_key_map_fixture.csv: test fixture
Ref: docs/plan/broker-abstraction/stories/BA-7.md
```

---

## Pre-baked graph context

```
search_graph("InstrumentKeyAdapter")       # protocol
search_graph("DhanInstrumentKeyAdapter")   # reference implementation to mirror exactly
```
