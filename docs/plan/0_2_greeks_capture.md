# 0.2 — Greeks capture (OptionChain model + `_extract_greeks_from_chain`)

**Status:** NOT STARTED
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

- [ ] `OptionChain` Pydantic model defined, with per-strike CE and PE sub-models carrying: `ltp`, `bid`, `ask`, `oi`, `volume`, `delta`, `gamma`, `theta`, `vega`, `iv`, `strike`. All monetary fields `Decimal`. Frozen.
- [ ] Model location: `src/models/portfolio.py` extension, OR new `src/models/options.py` if portfolio module gets crowded. Choose and document.
- [ ] Field names are **source-agnostic** — use `delta`, not `greeks_delta` or `greeks.delta`. Translation from Upstox/Dhan response shapes happens in each client's parser, not in the model.
- [ ] `src/portfolio/tracker.py::_fetch_greeks()` implemented (replaces the early-return stub). Module-level private function per Google §2.17 (no `@staticmethod`).
- [ ] Option chain API call fixed to use `NSE_INDEX|Nifty 50` as underlying key (documented quirk in `REFERENCES.md`).
- [ ] Greeks columns in `daily_snapshots` populated on next live snapshot run.
- [ ] Tests: fixture-driven using existing `tests/fixtures/responses/nifty_chain_2026-04-07.json`. Cover: happy path (all Greeks populated), missing strike in response, malformed Greek value (e.g., `null` or non-numeric string), empty chain response.
- [ ] ≥12 new tests, all offline.

## Definition of Done

- [ ] `python -m pytest tests/unit/` full suite green
- [ ] `greeks-analyst` agent invoked on design before implementation; feedback addressed
- [ ] `code-reviewer` agent clean on diff
- [ ] `CONTEXT.md` updated — new model in the tree, Greeks columns no longer flagged as null in "Live Data" section
- [ ] `DECISIONS.md` updated with "Source-agnostic OptionChain model" decision
- [ ] `TODOS.md` item 1 marked done, session log entry added
- [ ] `BACKTEST_PLAN.md` task 0.2 checkbox ticked
- [ ] Commit: `feat(portfolio): capture Greeks from option chain` in conventional format

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
- `_extract_greeks_from_chain(chain, target_leg)` — given a full chain and a leg (instrument key), finds the matching strike and returns a Greeks dict. Pure function.
- Test fixture placement: existing `tests/fixtures/responses/nifty_chain_2026-04-07.json` is the Upstox reference. Do not rename it.

## Non-goals

- Does NOT implement the Dhan client. That's task 1.10.
- Does NOT build Greeks-based strategy logic (strike selection by delta). That's in the strategy modules starting Phase 1.7.
- Does NOT compute Greeks locally — reads them from the API response. Local BS Greeks are task 1.6a.

## Follow-up work

- 1.10 (Dhan live chain client) will add a second parser against the same `OptionChain` model.
- 1.6a (Black-Scholes Greeks) uses the same model for the computed-Greek case.

---

## Session log

_(append-only, dated entries)_
