# BA-3 — Dhan `MarketDataParser` implementation

> Assigned to: Antigravity
> Phase: 2 — Dhan Integration
> Priority: LOW
> Blocked by: BA-1, BA-2 must be merged first

---

## Goal

Implement `DhanMarketDataParser` — a `MarketDataParser` that converts Dhan's option chain
API response into the canonical `OptionChain` model. No downstream consumer changes.
No DB or Parquet schema changes.

---

## Context: Dhan option chain API

Dhan's option chain endpoint returns a structure broadly similar to Upstox but with
different field names and numeric security IDs instead of `EXCHANGE_SEGMENT|TOKEN` keys.

Key differences from Upstox response:
- Strike price is `strikePrice` (float) vs Upstox `strike_price`
- Call/put legs are nested under `callOption` / `putOption` dicts
- Greeks are under `greeks` sub-dict: `delta`, `gamma`, `theta`, `vega`, `iv`
- Instrument ID is `securityId` (string of numeric ID, e.g. `"49081"`)
- LTP is `lastTradedPrice`
- OI is `openInterest`
- Volume is `volume`

The `DhanInstrumentKeyAdapter` (BA-4) handles `securityId` → canonical key translation.
The parser receives raw Dhan API dicts and must produce `OptionChain` with canonical keys
already resolved via the adapter.

**If Dhan API response format is unavailable at implementation time:** build the parser
against a locally defined fixture dict (see test section). Do not make live API calls.

---

## Files to change

| File | Action |
|------|--------|
| `src/client/parsers/dhan.py` | New — `DhanMarketDataParser` |
| `tests/unit/client/test_parsers_dhan.py` | New — parser tests with fixture |
| `tests/fixtures/responses/dhan_option_chain.json` | New — representative Dhan fixture |

---

## What to implement

### `src/client/parsers/dhan.py`

```python
class DhanMarketDataParser:
    """MarketDataParser for Dhan option chain API responses.

    Requires a DhanInstrumentKeyAdapter to resolve securityId → canonical key.
    Constructor injection only — never import a concrete adapter directly.
    """

    def __init__(self, adapter: InstrumentKeyAdapter) -> None:
        self._adapter = adapter

    def parse_option_chain(self, raw: dict) -> OptionChain:
        ...
```

Parsing rules:
- `underlying` from `raw["underlyingSymbol"]` or `raw["underlying"]` (probe actual API)
- `expiry` from `raw["expiryDate"]` — ISO date string `YYYY-MM-DD`
- `spot_price` from `raw["underlyingSpotPrice"]` — `Decimal(str(value))`
- For each strike in `raw["data"]`:
  - `strike` = `Decimal(str(item["strikePrice"]))`
  - CE/PE legs: extract LTP, OI, volume, IV, delta, gamma, theta, vega from respective sub-dicts
  - `instrument_key` = `self._adapter.to_canonical(item["callOption"]["securityId"])` (CE) / PE equivalent
  - All price/monetary fields → `Decimal(str(value))` — never float
  - Missing/null Greek values → `None`

Raise `ValueError` with a descriptive message if required top-level keys are absent.

---

## Fixture — `tests/fixtures/responses/dhan_option_chain.json`

Construct a minimal 2-strike fixture (one ITM, one OTM) that covers:
- Both CE and PE legs present
- At least one Greek populated, at least one Greek null (realistic — Dhan nulls deep OTM Greeks)
- `securityId` values that match entries in the Dhan adapter fixture (BA-4)

---

## Tests — `tests/unit/client/test_parsers_dhan.py`

1. **Happy path:** parse 2-strike fixture → `OptionChain` with correct `underlying`, `expiry`, `spot_price`, both strikes, all legs.
2. **Decimal invariant:** every price field on every leg is `Decimal`, not `float`.
3. **Null Greeks:** leg with null IV/delta → corresponding fields are `None`, not zero.
4. **Missing required key:** `raw` dict missing `"data"` key → raises `ValueError`.
5. **`isinstance` check:** `isinstance(DhanMarketDataParser(mock_adapter), MarketDataParser)` → `True`.

Use `unittest.mock.MagicMock` for the adapter — no concrete adapter dependency in parser tests.

---

## Commit message

```
feat(client): Dhan MarketDataParser + fixture

Why: enables option chain ingestion from Dhan without altering canonical models or storage.
What:
- src/client/parsers/dhan.py: DhanMarketDataParser conforming to MarketDataParser protocol
- tests/unit/client/test_parsers_dhan.py: 5 parser tests
- tests/fixtures/responses/dhan_option_chain.json: 2-strike Dhan fixture
Ref: docs/plan/broker-abstraction/stories/BA-3.md
```

---

## Pre-baked graph context

```
search_graph("OptionChain")              # canonical model fields — read before writing parser
search_graph("OptionChainStrike")        # strike-level fields
search_graph("OptionLeg")               # leg-level fields including Greeks
search_graph("MarketDataParser")         # protocol — confirm BA-1 shipped
search_graph("InstrumentKeyAdapter")     # protocol — confirm BA-2 shipped
search_graph("UpstoxMarketDataParser")   # reference implementation to mirror
```
