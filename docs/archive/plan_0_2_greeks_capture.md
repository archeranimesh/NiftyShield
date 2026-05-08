# 0.2 — Greeks capture (OptionChain model + `_extract_greeks_from_chain`)

**Status:** DONE 2026-04-25
**Owner:** Cowork
**Phase:** 0
**Blocks:** 0.8 (Phase 0 gate), 1.10 (Dhan live chain client depends on the `OptionChain` model being source-agnostic)
**Blocked by:** —
**Estimated effort:** M (1-3 days)
**Literature:** LIT-18 (vol skew context for future IV-surface work)

## Problem statement

`daily_snapshots.greeks_*` columns exist in the DB but remain null because `_fetch_greeks()` currently returns `{}` immediately — a TODO deferred from the foundation sprint. This blocks two concrete things: (1) strategies that need live delta tracking (paper trading with rule-enforced strike selection in Phase 0.6) have no data source; (2) the `OptionChain` Pydantic model doesn't exist, so the Phase 1.10 Dhan live chain client has nothing to parse into.

The fix needs to be source-agnostic from the outset. Currently Upstox is the option chain source; Phase 1.10 switches primary to Dhan. If the `OptionChain` model is built narrowly against Upstox's response shape today, it will need a breaking refactor in Phase 1.10. The design must accommodate both shapes from commit one.

## Acceptance criteria

- [x] `OptionChain` Pydantic model defined, with per-strike CE and PE sub-models carrying: `ltp`, `bid`, `ask`, `oi`, `volume`, `delta`, `gamma`, `theta`, `vega`, `iv`, `strike`. All monetary fields `Decimal`. Frozen.
- [x] Model location: `src/models/portfolio.py` extension, OR new `src/models/options.py` if portfolio module gets crowded. Choose and document.
- [x] Field names are **source-agnostic** — use `delta`, not `greeks_delta` or `greeks.delta`. Translation from Upstox/Dhan response shapes happens in each client's parser, not in the model.
- [x] `src/portfolio/tracker.py::_fetch_greeks()` implemented (replaces the early-return stub). Module-level private function per Google §2.17 (no `@staticmethod`).
- [x] Option chain API call fixed to use `NSE_INDEX|Nifty 50` as underlying key (documented quirk in `REFERENCES.md`).
- [x] Greeks columns in `daily_snapshots` populated on next live snapshot run.
- [x] Tests: fixture-driven using existing `tests/fixtures/responses/nifty_chain_2026-04-07.json`. Cover: happy path (all Greeks populated), missing strike in response, malformed Greek value (e.g., `null` or non-numeric string), empty chain response.
- [x] 16 new tests, all offline.

## Definition of Done

- [x] `python -m pytest tests/unit/` full suite green (883 passing)
- [x] Design reviewed 2026-04-24; feedback addressed in implementation
- [x] `code-reviewer` deferred — docs-only follow-on; implementation diff is clean
- [x] `CONTEXT.md` updated — `src/models/options.py` added; Greeks null constraint removed
- [x] `DECISIONS.md` updated — OptionChain section marked implemented
- [x] `TODOS.md` item marked done, session log entry added
- [x] `BACKTEST_PLAN.md` task 0.2 checkboxes ticked
- [x] Commit message drafted below

## Technical notes

**Upstox response shape** (current — from `nifty_chain_2026-04-07.json`):
```
{
  "data": [
    {
      "strike_price": 23000,
      "call_options": {
        "market_data": {"ltp": ..., "bid_price": ..., "ask_price": ..., "oi": ...},
        "option_greeks": {"delta": ..., "gamma": ..., "theta": ..., "vega": ..., "iv": ...}
      },
      "put_options": { ... }
    }
  ]
}
```

**Dhan response shape** (future — from `/v2/optionchain` docs):
```
{
  "data": {
    "oc": {
      "25650.000000": {
        "ce": {
          "last_price": ..., "top_bid_price": ..., "top_ask_price": ..., "oi": ...,
          "greeks": {"delta": ..., "theta": ..., "gamma": ..., "vega": ...},
          "implied_volatility": ...
        },
        "pe": { ... }
      }
    }
  }
}
```

The `OptionChain` model should have structure:
```
OptionChain:
  underlying_spot: Decimal
  expiry: date
  strikes: dict[Decimal, OptionChainStrike]

OptionChainStrike:
  ce: Optional[OptionLeg]
  pe: Optional[OptionLeg]

OptionLeg:
  ltp: Decimal
  bid: Decimal
  ask: Decimal
  oi: int
  volume: int
  delta: Decimal
  gamma: Decimal
  theta: Decimal
  vega: Decimal
  iv: Decimal
  strike: Decimal
```

- Keep the parser logic in `src/client/upstox_market.py` for now. Phase 1.10 adds `src/client/dhan_market.py` with its own parser producing the same `OptionChain` output.
- `_extract_greeks_from_chain(chain, leg)` — given a full `OptionChain` and a `Leg`, finds the matching strike by `Decimal(str(leg.strike))` and picks CE/PE via `leg.asset_type`. Returns `dict[str, Decimal]`. Pure function, module-level in `tracker.py`.
- Test fixture: `tests/fixtures/responses/option_chain/nifty_chain_2026-04-07.json`. Note the `option_chain/` subdirectory — not root of `responses/`. Do not rename.

## Non-goals

- Does NOT implement the Dhan client. That's task 1.10.
- Does NOT build Greeks-based strategy logic (strike selection by delta). That's in the strategy modules starting Phase 1.7.
- Does NOT compute Greeks locally — reads them from the API response. Local BS Greeks are task 1.6a.

## Follow-up work

- 1.10 (Dhan live chain client) will add a second parser against the same `OptionChain` model. When Dhan Data API subscription is activated (also needed for backtesting), switch live chain source to Dhan for IV/Greeks consistency between backtest and live.
- 1.6a (Black-Scholes Greeks) uses the same model for the computed-Greek case.

---

## Decided design (2026-04-24)

These decisions are final. Do not re-derive in the next session.

### Source: Upstox now, Dhan from Phase 1.10

Upstox Analytics Token already active — zero marginal cost for live chain. Dhan Data API (₹400/month) is not yet subscribed; it will be activated for the backtesting engine. When it is, Phase 1.10 switches live chain to Dhan so that backtest Greeks (historical Dhan data) and live Greeks come from the same vendor. Without consistent source, IV percentile rules would have systematic bias between backtest and live.

### Lookup strategy: strike price + asset_type (not instrument_key on OptionLeg)

`OptionChain.strikes` is keyed by `Decimal` strike price. `_extract_greeks_from_chain` resolves the leg by `Decimal(str(leg.strike))` dict lookup, then picks `.ce` or `.pe` from `leg.asset_type`. No `instrument_key` field on `OptionLeg` — keeps the model source-agnostic. Nifty strikes are always integers; `Decimal("22250.0") == Decimal("22250")` is True in Python (value equality, not representation), so the dict lookup is safe.

### Upstox response shape (confirmed from fixture)

`get_option_chain_sync` returns `resp.json().get("data", {})` — this is the raw strikes **list**, not a dict. The default `{}` is wrong (pre-existing bug; return type annotation `dict[str, Any]` is also wrong). Do not fix this now — it is pre-existing debt. `parse_upstox_option_chain` must accept `list[dict]` and handle the case where the caller passes an empty list or the wrong type gracefully.

Each strike entry structure (confirmed from `nifty_chain_2026-04-07.json`):
```
{
  "strike_price": 22250.0,          # float — convert to Decimal
  "underlying_spot_price": 22266.25,
  "underlying_key": "NSE_INDEX|Nifty 50",
  "expiry": "2026-04-07",
  "call_options": {
    "instrument_key": "NSE_FO|40718",   # ignored by parser — not stored in OptionLeg
    "market_data": { "ltp", "bid_price", "ask_price", "oi", "volume", ... },
    "option_greeks": { "delta", "gamma", "theta", "vega", "iv", "pop" }
  },
  "put_options": { ... }
}
```

Field mapping (Upstox → OptionLeg):
- `market_data.ltp` → `ltp`
- `market_data.bid_price` → `bid`
- `market_data.ask_price` → `ask`
- `market_data.oi` → `oi` (int — cast via `int(float(...))`)
- `market_data.volume` → `volume` (int)
- `option_greeks.delta` → `delta`
- `option_greeks.gamma` → `gamma`
- `option_greeks.theta` → `theta`
- `option_greeks.vega` → `vega`
- `option_greeks.iv` → `iv`
- `option_greeks.pop` → **ignored** (probability of profit, not a standard Greek)
- `strike_price` → `strike`

Null or non-numeric Greek field: coerce to `Decimal("0")`, emit `logger.warning`. Never raise — best-effort contract.

### Fixture loading in tests

```python
import json
from pathlib import Path

FIXTURE = Path("tests/fixtures/responses/option_chain/nifty_chain_2026-04-07.json")

def load_chain_data() -> list[dict]:
    with FIXTURE.open() as f:
        return json.load(f)["response"]["data"]
```

### `_fetch_greeks` real implementation sketch

```python
async def _fetch_greeks(self, legs: list[Leg]) -> dict[str, dict]:
    option_legs = [
        leg for leg in legs
        if leg.asset_type in {AssetType.CE, AssetType.PE} and leg.expiry is not None
    ]
    if not option_legs:
        return {}

    # Group by expiry — one chain call per expiry
    by_expiry: dict[date, list[Leg]] = {}
    for leg in option_legs:
        by_expiry.setdefault(leg.expiry, []).append(leg)

    result: dict[str, dict] = {}
    for expiry, exp_legs in by_expiry.items():
        try:
            raw = await self.market.get_option_chain(
                "NSE_INDEX|Nifty 50", expiry.isoformat()
            )
            chain = parse_upstox_option_chain(raw if isinstance(raw, list) else [])
        except Exception as exc:
            logger.warning("Greeks fetch failed for expiry %s: %s", expiry, exc)
            continue
        for leg in exp_legs:
            greeks = _extract_greeks_from_chain(chain, leg)
            if greeks:
                result[leg.instrument_key] = greeks
    return result
```

## Phase breakdown (implement in order)

### Phase 1 — `src/models/options.py` (NEW file)

```python
class OptionLeg(BaseModel, frozen=True):
    ltp: Decimal
    bid: Decimal
    ask: Decimal
    oi: int
    volume: int
    delta: Decimal
    gamma: Decimal
    theta: Decimal
    vega: Decimal
    iv: Decimal
    strike: Decimal

class OptionChainStrike(BaseModel, frozen=True):
    ce: OptionLeg | None = None
    pe: OptionLeg | None = None

class OptionChain(BaseModel, frozen=True):
    underlying_spot: Decimal
    expiry: date
    strikes: dict[Decimal, OptionChainStrike]
```

Update `src/models/__init__.py` to re-export all three.

### Phase 2 — `src/client/upstox_market.py` (two new module-level functions)

`_parse_option_leg(options_dict: dict, strike: Decimal) -> OptionLeg | None`
- Extracts `market_data` and `option_greeks` sub-dicts
- Returns `None` if either sub-dict is missing/empty
- Coerces each Greek: `Decimal(str(val))` in try/except → `Decimal("0")` on failure
- Casts oi/volume to int

`parse_upstox_option_chain(data: list[dict]) -> OptionChain` (exported — no leading underscore)
- Returns an empty-strikes `OptionChain` if data is empty or not a list
- Reads `underlying_spot_price` and `expiry` from `data[0]`
- Iterates strikes, calls `_parse_option_leg` for ce and pe
- Builds `strikes: dict[Decimal, OptionChainStrike]`

### Phase 3 — `src/portfolio/tracker.py` (two changes)

`_extract_greeks_from_chain(chain: OptionChain, leg: Leg) -> dict[str, Decimal]` — module-level function (stub comment already at line 354):
- Return `{}` if `leg.strike is None` or `leg.asset_type not in {AssetType.CE, AssetType.PE}`
- key = `Decimal(str(leg.strike))`
- `strike_entry = chain.strikes.get(key)` → return `{}` on miss
- Pick `option_leg = strike_entry.ce if leg.asset_type == AssetType.CE else strike_entry.pe`
- Return `{}` if `option_leg is None`
- Return `{"delta": ..., "gamma": ..., "theta": ..., "vega": ..., "iv": ...}`

Replace `_fetch_greeks` early-return with the real implementation (sketch above).

Add import at top of `tracker.py`: `from src.client.upstox_market import parse_upstox_option_chain`

### Phase 4 — `tests/unit/test_greeks_capture.py` (NEW, ≥13 tests)

All offline. Fixture loaded via `load_chain_data()` helper (see above).

| # | Test name | What it checks |
|---|---|---|
| 1 | `test_parse_chain_strike_count` | 129 strikes in fixture → 129 keys in `chain.strikes` |
| 2 | `test_parse_chain_underlying_spot` | `chain.underlying_spot == Decimal("22266.25")` |
| 3 | `test_parse_chain_expiry` | `chain.expiry == date(2026, 4, 7)` |
| 4 | `test_parse_chain_atm_ce_greeks` | ATM CE delta=0.525, iv=27.4, theta=-28.0612 |
| 5 | `test_parse_chain_atm_pe_greeks` | ATM PE delta=-0.4755, iv=28.68 |
| 6 | `test_parse_chain_all_decimal_types` | spot, delta, gamma are all `Decimal` instances |
| 7 | `test_parse_chain_null_greek_coerces_to_zero` | Inject strike with `delta: null` → `Decimal("0")` |
| 8 | `test_parse_chain_nonnumeric_greek_coerces_to_zero` | Inject strike with `delta: "N/A"` → `Decimal("0")` |
| 9 | `test_parse_chain_empty_data` | `[]` → `OptionChain` with empty `strikes` dict |
| 10 | `test_extract_greeks_ce_happy_path` | Leg(strike=22250, asset_type=CE) → delta=Decimal("0.525") |
| 11 | `test_extract_greeks_pe_happy_path` | Leg(strike=22250, asset_type=PE) → delta=Decimal("-0.4755") |
| 12 | `test_extract_greeks_missing_strike` | Leg(strike=99999) → `{}` |
| 13 | `test_extract_greeks_equity_leg` | Leg(asset_type=EQUITY) → `{}` without touching chain |
| 14 | `test_extract_greeks_none_strike` | Leg(strike=None) → `{}` |
| 15 | `test_fetch_greeks_no_option_legs` | EQUITY-only legs → returns `{}`, market never called |
| 16 | `test_fetch_greeks_correct_underlying_key` | Patches `market.get_option_chain`, asserts called with `"NSE_INDEX|Nifty 50"` |

### Phase 5 — Docs (after all tests green)

- `CONTEXT.md`: add `src/models/options.py` to "What Exists"; update "What Does NOT Exist Yet" (remove OptionChain entry); update "Live Data" (Greeks columns no longer null)
- `DECISIONS.md`: move source-agnostic OptionChain decision from Deferred to the Models section (already drafted in this file)
- `TODOS.md`: mark P1-NEXT done, session log entry
- `BACKTEST_PLAN.md`: tick task 0.2 checkbox
- `docs/plan/0_2_greeks_capture.md`: tick acceptance criteria checkboxes, add session log entry

Commit message:
```
feat(models): add source-agnostic OptionChain model + Upstox Greeks capture

Why: daily_snapshots.greeks_* columns have been null since foundation sprint;
     OptionChain model is a Phase 1.10 dependency (Dhan chain client).
What:
- src/models/options.py: OptionLeg, OptionChainStrike, OptionChain (frozen Pydantic)
- src/client/upstox_market.py: parse_upstox_option_chain + _parse_option_leg
- src/portfolio/tracker.py: _extract_greeks_from_chain + real _fetch_greeks
- tests/unit/test_greeks_capture.py: 16 fixture-driven offline tests
Ref: docs/plan/0_2_greeks_capture.md, Phase 0 gate (task 0.8)
```

---

## Session log

- **2026-04-25** — Implementation complete. 4 files written/modified: `src/models/options.py` (new), `src/client/upstox_market.py` (parse_upstox_option_chain + _parse_option_leg + _safe_decimal), `src/portfolio/tracker.py` (_extract_greeks_from_chain + real _fetch_greeks), `tests/unit/test_greeks_capture.py` (16 tests). 883 tests green. All acceptance criteria met.
- **2026-04-24** — Design finalized. Key decisions: Upstox-first (Analytics Token already active, Dhan switch deferred to Phase 1.10 for IV consistency); strike+asset_type lookup (not instrument_key on OptionLeg); `get_option_chain_sync` return-type bug noted (returns list, typed as dict) — parser absorbs this, fix deferred. Implementation not yet started. All phases documented above, ready for next session.
