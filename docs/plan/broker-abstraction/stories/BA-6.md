# BA-6 — Kite `MarketDataParser` implementation

> Assigned to: Antigravity
> Phase: 3 — Kite/Zerodha Integration
> Priority: LOW
> Blocked by: BA-1, BA-2 must be merged first. Can run in parallel with BA-7.

---

## Goal

Implement `KiteMarketDataParser` — a `MarketDataParser` that converts Zerodha Kite's option
chain API response into the canonical `OptionChain` model.

---

## Context: Kite option chain API

Kite Connect's option chain data is fetched via the instruments endpoint + quote endpoint
rather than a single option chain call. For parsing purposes, treat the input `raw` dict as
a pre-assembled dict keyed by Kite `tradingsymbol` (e.g. `"NFO:NIFTY24JUN23000CE"`).

Key differences from Upstox:
- Symbol format: `"NFO:NIFTY{DDMMMYY}{STRIKE}{CE/PE}"` e.g. `"NFO:NIFTY26JUN23000CE"`
- Strike and expiry are encoded in the symbol string — must be parsed out
- LTP is `last_price`
- OI is `oi`
- Volume is `volume`
- Greeks are NOT returned by Kite's quote endpoint — they must be computed externally
  (Black-Scholes, already available in `src/backtest/` or inject as None)
- `instrument_token` is Kite's numeric identifier (int)

Since Kite does not return Greeks, all Greek fields on `OptionLeg` (`delta`, `gamma`,
`theta`, `vega`, `iv`) must be `None` when parsed from Kite data. This is valid —
`OptionLeg` already defines these as `Optional`.

---

## Files to change

| File | Action |
|------|--------|
| `src/client/parsers/kite.py` | New — `KiteMarketDataParser` |
| `tests/unit/client/test_parsers_kite.py` | New — parser tests with fixture |
| `tests/fixtures/responses/kite_option_chain.json` | New — representative Kite fixture |

---

## What to implement

### `src/client/parsers/kite.py`

```python
class KiteMarketDataParser:
    """MarketDataParser for Kite Connect option chain data.

    Input: pre-assembled dict keyed by Kite tradingsymbol.
    Greeks are not available from Kite quotes — all Greek fields will be None.
    """

    def __init__(self, adapter: InstrumentKeyAdapter) -> None:
        self._adapter = adapter

    def parse_option_chain(self, raw: dict) -> OptionChain:
        ...
```

Symbol parsing helper (private):
```python
def _parse_kite_symbol(symbol: str) -> tuple[str, date, Decimal, str]:
    """Parse 'NFO:NIFTY26JUN23000CE' → (underlying, expiry, strike, option_type)."""
    ...
```

Parsing rules:
- `underlying` from `raw["underlying"]` (top-level key, caller must set it)
- `expiry` from `raw["expiry"]` (ISO date string `YYYY-MM-DD`, caller must set it)
- `spot_price` from `raw["spot_price"]` (Decimal)
- For each symbol in `raw["strikes"]` dict:
  - Parse underlying/expiry/strike/option_type from symbol string
  - `instrument_key` = `self._adapter.to_canonical(str(item["instrument_token"]))`
  - `ltp` = `Decimal(str(item["last_price"]))`
  - `oi` = `item["oi"]` (int)
  - `volume` = `item["volume"]` (int)
  - All Greeks → `None`
- Raise `ValueError` if `raw["strikes"]` is absent

---

## Tests — `tests/unit/client/test_parsers_kite.py`

1. **Happy path:** parse 2-strike fixture → `OptionChain` with correct strikes, legs, `None` Greeks.
2. **Decimal invariant:** LTP and spot_price are `Decimal`, not `float`.
3. **Greeks are None:** delta/gamma/theta/vega/iv on every leg are `None`.
4. **Symbol parser:** `_parse_kite_symbol("NFO:NIFTY26JUN23000CE")` → `("NIFTY", date(2026,6,26), Decimal("23000"), "CE")`.
5. **Missing strikes key:** `raw` dict without `"strikes"` → raises `ValueError`.
6. **`isinstance` check:** `isinstance(KiteMarketDataParser(mock_adapter), MarketDataParser)` → `True`.

---

## Commit message

```
feat(client): Kite MarketDataParser + fixture

Why: enables option chain ingestion from Kite without altering canonical models; Greek fields
     are None (Kite does not return them in quote responses).
What:
- src/client/parsers/kite.py: KiteMarketDataParser conforming to MarketDataParser protocol
- tests/unit/client/test_parsers_kite.py: 6 parser tests
- tests/fixtures/responses/kite_option_chain.json: 2-strike Kite fixture
Ref: docs/plan/broker-abstraction/stories/BA-6.md
```

---

## Pre-baked graph context

```
search_graph("OptionLeg")               # confirm Greek fields are Optional
search_graph("MarketDataParser")         # confirm BA-1 shipped
search_graph("DhanMarketDataParser")     # reference implementation to mirror
search_graph("InstrumentKeyAdapter")     # confirm BA-2 shipped
```
