# 0.5 — Paper trading module (`src/paper/`)

**Status:** NOT STARTED
**Owner:** Cowork
**Phase:** 0
**Blocks:** 0.6 (cannot start paper trading without this), 0.8 (Phase 0 gate)
**Blocked by:** 0.1 (protocol debt), 0.2 (OptionChain model needed for chain snapshots)
**Estimated effort:** L (3-7 days)
**Literature:** none

## Problem statement

Paper trading is the core learning mechanism of Phase 0 and the calibration target for the Phase 1 backtest. Without a paper trading substrate, there is nothing to paper-trade into — strategy rules become a disconnected spec document instead of a measured discipline.

The implementation reuses existing `Trade` / `PortfolioStore` patterns rather than building parallel infrastructure. This keeps the codebase coherent: paper trades and live trades share the analytics layer, share the snapshot pipeline, share Telegram notifications — differing only in that paper trades are namespaced by `strategy_name` prefix `paper_` and live in a separate table.

Design decision: separate table, not a boolean flag on `trades`. Rationale: prevents accidental cross-contamination at query time, allows schema divergence later (paper trades may want different fields — e.g., "override logged" — that don't belong on live trades), and mirrors the MF ledger pattern (`mf_transactions` is a separate table even though it could be a flagged row in `trades`).

## Acceptance criteria

- [ ] `src/paper/` package with `__init__.py` and `CLAUDE.md` (module invariants: paper trades never touch live `trades` table; `strategy_name` must start with `paper_`; no broker API calls; reuses `BrokerClient` protocol for LTP).
- [ ] `src/paper/models.py` — `PaperTrade` frozen Pydantic model mirroring `Trade`'s fields plus `is_paper: Literal[True] = True` (discriminator) and `intended_risk: Decimal | None` (for R-multiple computation later per LIT-09). Validator rejects `strategy_name` that does not start with `paper_`.
- [ ] `src/paper/store.py` — `PaperStore` class. Tables in shared `portfolio.sqlite`:
  - `paper_trades` — same columns as `trades` plus `intended_risk TEXT`. UNIQUE `(strategy_name, leg_role, trade_date, action)`. Idempotent upsert.
  - `paper_nav_snapshots` — daily mark-to-market per paper strategy.
  - Decimal-as-TEXT invariant preserved for all monetary fields.
- [ ] `PaperStore` methods: `record_trade`, `get_trades`, `get_position`, `get_all_positions_for_strategy`, `record_nav_snapshot`, `get_prev_nav_snapshot`. Mirror `PortfolioStore` shapes exactly — agents reading graph should find identical-name identical-signature methods.
- [ ] `src/paper/tracker.py` — `PaperTracker` class. `compute_pnl(strategy_name)` returns `StrategyPnL`. `record_daily_snapshot(strategy_name)` records current mark-to-market. Consumes `MarketDataProvider` protocol for LTP (not a new market client).
- [ ] `scripts/record_paper_trade.py` — CLI mirroring `record_trade.py`. Enforces `strategy_name` prefix at CLI layer (rejects with a clear error message before touching the store).
- [ ] Extend `scripts/daily_snapshot.py` `_async_main` to include a paper-trades section in the combined summary. Wrapped in `try/except Exception` with intent comment — non-fatal per existing Dhan/Nuvama pattern.
- [ ] Extend `_format_combined_summary()` with a Paper section (only rendered if there are active paper strategies, i.e., at least one with non-zero net position).
- [ ] Tests: ≥40 new tests. Models (validator rejections, frozen, Decimal precision): ~10. Store (CRUD, idempotency, strategy prefix enforcement at store layer as second defense, schema coexistence with existing tables): ~18. Tracker (pure P&L math, mocked store/market): ~8. CLI (prefix rejection, dry-run, successful path with mocked DB): ~6.

## Definition of Done

- [ ] `python -m pytest tests/unit/` full suite green
- [ ] `code-reviewer` agent clean on diff (heavy Decimal focus)
- [ ] `src/paper/CLAUDE.md` exists and documents invariants
- [ ] `CONTEXT.md` "What Exists" tree updated with new module
- [ ] `DECISIONS.md` updated with two new entries: (a) "Paper trades in separate table with `paper_` prefix" rationale, (b) "PaperTrade mirrors Trade deliberately" rationale
- [ ] `TODOS.md` session log entry added
- [ ] `BACKTEST_PLAN.md` task 0.5 checkbox ticked
- [ ] Commit sequence (per `CLAUDE.md` Step 6): one commit per phase boundary — models → store → tracker → CLI → snapshot wiring. 5 commits.

## Technical notes

- **Do not copy-paste `PortfolioStore` into `PaperStore`.** Even though they're similar, copy-paste will drift — one will get a bug fix and the other won't. If repetition becomes egregious, factor into a shared base class or mixin, but only after the second store exists and the duplication is visible.
- **The `strategy_name` prefix enforcement belongs in both the model validator AND the CLI.** Two layers of defense — one catches programmatic mistakes, the other catches human CLI typos. Not redundant; belt-and-braces.
- **Paper trades share the `portfolio.sqlite` DB, not a separate file.** Single WAL, single backup target. The two-table separation is logical, not physical.
- **`PaperTracker` uses the `MarketDataProvider` protocol**, not a specific client. This means when Phase 1.10 switches the default from Upstox to Dhan, paper trading migrates automatically — no code changes in `src/paper/`.
- Snapshot section format in the combined summary should follow the existing Bonds/Derivatives section style. Example output:
  ```
  Paper (CSP v1)
    CSP NIFTYBEES 2025-05-29 PE @ 270  qty=35  entry=3.20  ltp=2.10  pnl=+₹3,850
    Strategy total: +₹3,850
  ```
- **Field `intended_risk`:** set to estimated max loss at trade entry. For a CSP, this is `(strike - premium_received) * lot_size` (the amount at risk if assigned and stock goes to zero, though practically less because the CSP owner wants the assignment). For test data, use placeholder values; document the convention in `CLAUDE.md` for the module.

## Non-goals

- Does NOT implement any specific strategy. The CSP spec and paper-trading mechanics are task 0.4 (spec) and 0.6 (execution). This task provides the substrate only.
- Does NOT build analytics. Analytics module is 1.5b.
- Does NOT connect to a live broker — all "trades" are manual log entries via the CLI.
- Does NOT simulate fills or slippage. The human decides entry/exit prices based on observed market; CLI records them.

## Follow-up work

- 0.6 (paper trading execution) uses this module.
- 1.5b (analytics module) consumes `paper_trades` alongside live `trades` via a shared interface.
- 1.11 (variance check) reads paper trade history to compare against backtest distribution.

---

## Session log

_(append-only, dated entries)_
