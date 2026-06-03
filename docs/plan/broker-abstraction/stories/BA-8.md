# BA-8 — Wire Kite parsers into `factory.py` + integration smoke test

> Assigned to: Claude
> Phase: 3 — Kite/Zerodha Integration
> Priority: LOW
> Blocked by: BA-6 and BA-7 must be merged first

---

## Goal

Extend `factory.py` to support `upstox_env="kite"`. Mirror BA-5 exactly — add Kite selection
branch, extend the `upstox_env` Literal, and add a smoke test.

---

## Files to change

| File | Action |
|------|--------|
| `src/client/factory.py` | Add `"kite"` branch to `build_market_data_parser()` |
| `src/config.py` | Extend `upstox_env` Literal to include `"kite"` |
| `tests/unit/client/test_factory_parsers.py` | Extend — add Kite selection + smoke test cases |

---

## What to implement

Extend the selection logic in `build_market_data_parser()`:
- `upstox_env == "kite"` → `KiteMarketDataParser(adapter or _build_kite_adapter())`

`_build_kite_adapter()` constructs `KiteInstrumentKeyAdapter` with `data/instruments/kite_key_map.csv`.

Extend `src/config.py`:
```python
upstox_env: Literal["prod", "sandbox", "test", "dhan", "kite"] = "test"
```

---

## Tests — extend `tests/unit/client/test_factory_parsers.py`

Add:
1. **Kite selection:** `upstox_env="kite"` with injected mock adapter → returns `KiteMarketDataParser`.
2. **Smoke test — Kite parse:** with `upstox_env="kite"`, injected `KiteInstrumentKeyAdapter` using fixture CSV, and Kite chain fixture → valid `OptionChain`.
3. **Protocol conformance:** Kite parser satisfies `isinstance(..., MarketDataParser)`.

---

## Commit message

```
feat(client): wire Kite parsers into factory + smoke test

Why: completes Kite broker integration at the composition root.
What:
- src/client/factory.py: "kite" branch in build_market_data_parser()
- src/config.py: extend upstox_env Literal to include "kite"
- tests/unit/client/test_factory_parsers.py: 3 additional Kite tests
Ref: docs/plan/broker-abstraction/stories/BA-8.md
```

---

## Pre-baked graph context

```
search_graph("build_market_data_parser")  # existing function — add kite branch
search_graph("KiteMarketDataParser")       # confirm BA-6 shipped
search_graph("KiteInstrumentKeyAdapter")   # confirm BA-7 shipped
```
