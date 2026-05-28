# Council Decision: council-ping-test

Date: 2026-05-28  
Chairman: anthropic/claude-4.6-opus-20260205  
Council members: openai/gpt-5.5-20260423, google/gemini-3.1-pro-preview-20260219, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

## Council Chairman's Final Answer

**Recommendation:** Exit the short put at **50% premium decay (R1) or 21 DTE remaining (R5) — whichever comes first.**

The 50% profit target captures the most capital-efficient portion of theta decay, while the 21 DTE *remaining* time stop (not 21 calendar days from entry) mitigates the accelerating gamma and tail risk that builds as expiration approaches. This distinction matters because your entries range from 30–45 DTE, so a fixed calendar-day count from entry would trigger inconsistently, whereas anchoring to DTE remaining enforces a uniform risk cutoff aligned with your existing R5 rule.

---

**Chairman's note on the deliberation:** All three models converged on the same core recommendation (50% target + time stop, whichever first). The key differentiator was precision on the time stop definition: two of three models correctly flagged that the prompt's "21 calendar days from entry" framing is a trap — your documented R5 rule is **21 DTE remaining**, which is the correct anchor. This is the single most important nuance for implementation.

---

## Stage 1 — Individual Responses

### openai/gpt-5.5-20260423

Recommendation: Use **50% premium decay first, with a time stop at 21 DTE remaining — not 21 calendar days from entry**.  

Reason: the 50% target captures efficient theta decay, while exiting around 21 DTE reduces accelerating gamma/tail risk near expiry; using “21 days from entry” is less consistent because entries can vary from 30–45 DTE.

### google/gemini-3.1-pro-preview-20260219

I recommend exiting the short put at either a 50% profit target or when **21 Days to Expiry (DTE)** remain, whichever comes first, rather than counting 21 days from entry. Taking profits at 50% captures the most capital-efficient portion of theta decay, while stopping out specifically at 21 DTE protects your portfolio from the accelerating gamma risk and outsized directional moves that occur right before expiration. This structure directly enforces your established R1 (50% profit target) and R5 (21 DTE time stop) strategy rules.

### deepseek/deepseek-r1-0528

## Recommendation

Use the **50% profit target as the primary exit condition**, closing the position when premium decays to 50% of the original credit received. The 21-day time stop should only trigger if the profit target isn't met.  

**Key Reason:** Historical analysis of Nifty options selling indicates that most profitable trades reach 50% decay within 10-15 days due to theta acceleration. Enforcing the profit target first captures this edge, while the 21-day fallback mitigates gamma risk from holding positions too close to expiry.

## Aggregate Rankings (Stage 2 Peer Review)

- google/gemini-3.1-pro-preview-20260219: avg rank 1.67 (3 votes)
- openai/gpt-5.5-20260423: avg rank 2.0 (3 votes)
- deepseek/deepseek-r1-0528: avg rank 2.33 (3 votes)

---

## Prompt Sent (first 3000 chars)

```
=== NIFTYSHIELD PROJECT STATE ===

# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

**Related files:** [MISSION.md](MISSION.md) — immutable mission + grounding principles | [DECISIONS.md](DECISIONS.md) | [REFERENCES.md](REFERENCES.md) | [TODOS.md](TODOS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) — Phase 0 active tasks only (~300 lines) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) — Phase 1+ tasks (load only after Phase 0.8 gate) | [LITERATURE.md](LITERATURE.md) — concept reference (Kelly, Sharpe, meta-labeling) | [docs/plan/](docs/plan/) — one story file per task | [INSTRUCTION.md](INSTRUCTION.md)
---

## Current State (as of 2026-05-25)

### What Exists (committed and working)

Full file-level module tree: **[CONTEXT_TREE.md](CONTEXT_TREE.md)**
Load that file when adding new modules or doing a full structural survey.
Key top-level packages: `src/auth`, `src/client`, `src/models`, `src/portfolio`, `src/paper`, `src/mf`, `src/dhan`, `src/nuvama`, `src/intraday`, `src/instruments`, `src/market_calendar`, `src/notifications`, `src/utils`, `src/backtest`, `src/risk`, `src/gamma`, `src/db.py`
`src/risk/` — portfolio-level delta risk controls. `PortfolioDelta` frozen dataclass (`src/risk/models.py`): `options_delta_lots`, `niftybees_delta_lots`, `total_delta_lots`, `warning_breached`, `cap_breached`, `as_of`. `PortfolioDeltaTracker` (`src/risk/delta_tracker.py`): `aggregate_delta(paper_positions, nifty_spot, lot_size) → PortfolioDelta`; options-only thresholds warning=0.75/cap=1.0 lots, combined thresholds warning=1.5/cap=2.0 lots; parameterised via constructor. CE/futures = `net_qty/lot_size`; PE = `-net_qty/lot_size`; NiftyBees = `qty×avg_cost/(spot×lot_size)`. `check_entry_allowed` (`src/risk/entry_gate.py`): protective entries always allowed; cap → block; warning → allow with message. 20 unit tests in `tests/unit/risk/test_delta_tracker.py`.
`src/gamma/` — scaffolding, data models (`GammaChainSnapshot` and `GammaWatchlistEntry` frozen dataclasses), and persistence (`GammaStore` SQLite operations) for Near-Expiry Gamma Buy strategy.
`src/backtest/ivr.py` — `compute_ivr(vix_today, vix_series)`: IVR formula over trailing 252-day VIX window; returns `float | None`; clamps to `[0.0, 1.0]`; flat-window safe (returns 0.5). 11 unit tests in `tests/unit/backtest/test_ivr.py`.
`src/backtest/vix_ingest.py` — India VIX ingestion pipeline. Supports NSE CSV (legacy) and Upstox API.canonical Parquet storage: `data/historical/ohlc/india_vix/`. Resumable — identifies gaps and fetches missing days. 7 unit tests in `tests/unit/backtest/test_vix_ingest.py`.

`src/models/options.py` — `OptionLeg`, `OptionChainStrike`, `OptionChain` (all `frozen=True` Pydantic). Source-agnostic field names; Upstox parser in `src/client/upstox_market.py...
```