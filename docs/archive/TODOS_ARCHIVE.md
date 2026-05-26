# NiftyShield — TODOs Archive

> Completed work and session logs, reverse chronological.
> Active open work: [TODOS.md](../../TODOS.md)

---

## Ongoing Paper Trading — Active as of 2026-05-26

All three tracks confirmed running in production (EOD snapshot log verified 2026-05-25).
Activity items removed from TODOS.md — these are continuous trading discipline, not discrete tasks.

**0.6 — CSP v1 Paper Trading** (`paper_csp_nifty_v1`): active. Monthly CSP entries at 22-delta
per `csp_nifty_v1.md`. Monitored via `daily_snapshot.py`. Minimum 6 full cycles before conclusions.

**0.6a — NiftyShield Integrated v1** (`paper_niftyshield_v1`): active alongside CSP. Leg 2
(put spread, 4 lots) at each CSP entry; Leg 3 (tail puts) quarterly (Jan/Apr/Jul/Oct). Two open
implementation tasks remain in TODOS.md: `paper_csp_roll.py` + `paper_3track_overlay.py:243` migration.

**0.6b — 3-Track Nifty Comparison** (`paper_nifty_spot` / `paper_nifty_futures` / `paper_nifty_proxy`):
active. All base legs entered. Overlays running. Futures standalone CC permanently blocked (council ruling).
Minimum 6 monthly cycles + ≥1 high-VIX event (India VIX >18) before cross-track conclusions.
Source: `docs/strategies/nifty_track_comparison_v1.md`.

---

## Completed Tasks: 2026-05-14 → 2026-05-26

### Task 0 — Fix bhavcopy pipeline for NSE UDiFF format ✅ Done 2026-05-14

NSE migrated F&O bhavcopy to UDiFF format in late 2024. `src/backtest/bhavcopy_ingest.py` updated:
`download_bhavcopy` tries UDiFF URL first, falls back to legacy on 404. `parse_bhavcopy` detects
format via `'TradDt' in reader.fieldnames` and routes to `_parse_legacy()` or `_parse_udiff()`.
`BhavRecord` model unchanged. UDiFF fixture + routing tests added. Commits: `490ec9b`, `590f472`.

### Task 1 — India VIX ingestion + IVR calculation ✅ Done 2026-05-14

`src/backtest/vix_ingest.py` — daily India VIX ingest via Upstox Analytics token; Parquet at
`data/historical/ohlc/india_vix/`; resumable. `src/backtest/ivr.py` — `compute_ivr()` formula with
252-day window, clamped `[0.0, 1.0]`. `PaperTrade.ivr_at_entry: float | None` field added.
`scripts/record_paper_trade.py` R3 gate: warns when IVR < 0.25 or > 0.50. 18 unit tests.
Unblocks Phase 0.8 gate criteria C + D and BACKTEST_PLAN_PHASE1.md task 1.11.

### Task 2 — PortfolioDeltaTracker (`src/risk/`) ✅ Done 2026-05-26

`src/risk/` package: `PortfolioDelta` frozen dataclass (`models.py`); `PortfolioDeltaTracker.aggregate_delta()`
(`delta_tracker.py`) — CE/futures = `net_qty/lot_size`, PE = `-net_qty/lot_size`, NiftyBees =
`qty×avg_cost/(spot×lot_size)`; options thresholds 0.75w/1.0c lots, combined 1.5w/2.0c lots, parameterised.
`check_entry_allowed()` (`entry_gate.py`) — protective bypass, cap blocks, warning passes with message.
21 unit tests. 1472 total suite green. Commit: `e8898d3`.
Source: `docs/council/2026-05-02_multi-strategy-portfolio-risk-allocation.md` §7.3.

---

## Session Log: 2026-05-10 → 2026-05-12

| Date | What Changed |
|---|---|
| 2026-05-12 | **CLI/UX audit cross-check.** Verified against commits `264adf0` + `8cd9307`: CLI-1–5, CLI-10–11, UX-6–9 all implemented. CLI-12 (--notes surface in paper_snapshot.py) confirmed absent — remains open in TODOS.md. |
| 2026-05-11 | **Paper Trading CLI & UX audit.** Full audit of 6 paper trading scripts. 12 CLI/UX issues catalogued with Antigravity handoff prompts: CLI-1 (dry-run flag unification), CLI-2 (--spot rename), CLI-3 (--index for roll), CLI-4 (--date type), CLI-5 (--track shortcuts), UX-6 (compact P&L table), UX-7 (summary-first ordering), UX-8 (--verbose flag), UX-9 (shared formatting.py), CLI-10 (--overlay filter for roll), CLI-11 (--yes semantics), CLI-12 (--notes surface). |
| 2026-05-10 | **Auto-expiry for CSP entry scripts (SHA 21cd505).** `src/instruments/lookup.py`: `get_expiry_candidates(underlying, today, preference)` added — enumerates NIFTY expiries into monthly/quarterly/yearly buckets. `scripts/find_strike_by_delta.py` + `scripts/record_paper_trade.py`: `--expiry` now optional; auto-selects via cross-ranked pool. 6 unit tests in `tests/unit/instruments/test_expiry_candidates.py`. |
| 2026-05-10 | **Markdown sweep.** Archived 2026-05-01 to 2026-05-09 session log. Restructured TODOS.md (Task 0–3 sequential queue). Updated BACKTEST_PLAN.md completion log, PLANNER.md completed section, CONTEXT.md date + test count. |

---

## Session Log: 2026-05-01 → 2026-05-09

| Date | What Changed |
|---|---|
| 2026-05-09 | **TrueData 1-min data plan.** `BACKTEST_PLAN_PHASE1.md` task 1.3b added: TrueData historical dump ingestion pipeline spec (₹7,999/year, 2022–2024). CSV format confirmed from sample. `DECISIONS.md → TrueData Historical Dump (2026-05-09)` added. No code — start only after TrueData delivers zip files. |
| 2026-05-08 | **Intraday market store review fixes (3 commits).** UTC timezone-awareness enforced in `record_market_snapshot`; Google-style docstrings; renamed orchestrator logger. |
| 2026-05-08 | **Intraday Tracker Schema Refactor.** `src/intraday/market_store.py` (`IntradayMarketStore`) isolates market context (Nifty+VIX). Nuvama v3 schema: `nifty_spot` dropped from `nuvama_intraday_snapshots`. Orchestrator `scripts/intraday_tracker.py` fetches Nifty+VIX once async. |
| 2026-05-08 | **Workflow tooling session.** Commit skill converted to 5-step executor; agent model strings updated; AutoTrigger table + Step 3b routing gate added to CLAUDE.md; 4 new hooks/skills added. |
| 2026-05-06 | **Dhan intraday options tracking complete (Phases A–E).** `DhanOptionPosition`, `DhanOptionsSummary`, `DhanFundLimit` models. `src/dhan/positions.py` — positions parser/filter/formatter. `DhanStore` extended with `dhan_options_snapshots` + `dhan_margin_snapshots`. `scripts/dhan_intraday_tracker.py` + `scripts/intraday_tracker.py` (combined Dhan+Nuvama, `*/15 9-15 * * 1-5`). `NuvamaOptionsSummary.monthly_realized_pnl` + Today/Month/Realized split. 428 tests passing. |
| 2026-05-04 | **Overlay automation complete (Phases A–E).** `PaperLegSnapshot` + `paper_leg_snapshots` table. `paper_3track_overlay.py` (live overlay entry, CC blocked on futures). `paper_3track_snapshot.py` (EOD cron, delta-from-yesterday). `paper_3track_overlay_roll.py` (DTE gate, atomic collar rollback). 83 paper tests passing. |
| 2026-05-03 | **Task 0.4b complete.** `docs/strategies/nifty_track_comparison_v1.md` written; passes `validate_strategy_spec.py`. Unblocks 0.6b. |
| 2026-05-03 | **NSE UDiFF migration discovered.** Legacy URL confirmed working to 2024-04-25; broken from 2024-12-02. Fix spec documented in `DECISIONS.md → NSE Bhavcopy Format Migration`. Safe bootstrap range: `--end 2024-11-01`. |
| 2026-05-03 | **Phase 1.3 bhavcopy ingestion shipped.** `src/backtest/bhavcopy_ingest.py` + `bhavcopy_loader.py`. `download_bhavcopy`, `parse_bhavcopy`, Parquet output at `data/offline/options_ohlcv/`. `scripts/bhavcopy_bootstrap.py` resumable bulk download. |
| 2026-05-02 | **Council decisions ingested** — variance gate, near-expiry gamma buy research. `DECISIONS.md` + `BACKTEST_PLAN.md` updated; `docs/plan/variance_gate.md` created. |
| 2026-05-01 | **Root markdown cleanup.** Session log archived; CONTEXT.md date + test count updated; README.md synced. |

---

## Session Log: 2026-04-27 → 2026-04-30

| Date | What Changed |
|---|---|
| 2026-04-30 | **IV Reconstruction + Slippage council decisions documented.** Black '76 + Nifty Futures forward, stepped RBI Repo Rate, quadratic smile fit. Slippage: absolute INR, VIX-regime-aware. `DECISIONS.md` + `BACKTEST_PLAN.md` updated. |
| 2026-04-30 | **llm-council integrated.** `scripts/ask_council.py` — dual-mode CLI (submit or save to pending/). 3 domain templates. `docs/council/README.md` with workflow. 33 offline unit tests. |
| 2026-04-27 | **Data source decision.** TrueData API + DhanHQ rejected. Stockmock (calibration) + NSE Bhavcopy (programmatic) adopted. TimescaleDB deferred indefinitely. `DECISIONS.md` + multiple plan docs updated. |
| 2026-04-27 | **BACKTEST_PLAN + PLANNER restructure.** Task 1.3a added (Upstox OHLC ingest); Phase 2 Track A (swing) + Track B (investment) research pipelines added. |
| 2026-04-27 | **Story 0.1 closed (nuvama test debt).** All 154 nuvama tests passing; plan story status updated to DONE. |

---

## Session Log: 2026-04-24 → 2026-04-26

| Date | What Changed |
|---|---|
| 2026-04-26 | **NiftyShield integrated strategy design.** CSP income + put spread (4 lots) + tail puts (2 lots). `docs/strategies/niftyshield_integrated_v1.md` created; passes validator. `DECISIONS.md` + `BACKTEST_PLAN.md` updated (tasks 0.4a, 0.6a, 1.9, 1.9a). |
| 2026-04-25 | **CSP v1 strategy review.** Underlying switched from NiftyBees → Nifty 50. `docs/strategies/csp_nifty_v1.md` created. Rules R1–R7 revised. `DECISIONS.md` + `BACKTEST_PLAN.md` updated. |
| 2026-04-25 | **Greeks capture (task 0.2).** `src/models/options.py` (OptionLeg, OptionChainStrike, OptionChain). `parse_upstox_option_chain` in `upstox_market.py`. Real `_fetch_greeks` in tracker. 16 tests. 883 total passing. |
| 2026-04-25 | **Paper trading module (sprint 0.5).** `src/paper/` package: `PaperTrade`, `PaperPosition`, `PaperNavSnapshot`, `PaperStore`, `PaperTracker`. `record_paper_trade.py` + `paper_snapshot.py`. 65 tests. 948 total passing. |
| 2026-04-25 | **NiftyBees collateral leg decision.** `long_niftybees` leg modelled in paper P&L; annual reset January. `DECISIONS.md` + `csp_nifty_v1.md` updated. |
| 2026-04-24 | **DEBT-1 (`@staticmethod` overuse).** 8 static methods promoted to module-level private functions. 868 tests green. |

---

## Completed Feature TODOs (2026-04-01 → 2026-04-23)

### ✅ Architecture Review (AR-1 → AR-21) — DONE 2026-04-21 → 2026-04-23

Full review against `python-architecture-review.prompt.md` v6. All P0–P4 items completed:
- AR-1: Fix `if not raw_ltp:` truthiness bug; AR-2: Fix `if underlying_price:` at 2 sites
- AR-3: Nuvama options + intraday tests (54 new tests, 847 total)
- AR-4: `PortfolioSummary` refactored to per-source composition (26-field flat → 16-field composed)
- AR-5 → AR-21: BrokerClient protocol, composition root, notification non-fatal, Decimal invariants, SQL GROUP BY optimization, logger hygiene, async correctness, etc.

### ✅ Nuvama Options + Intraday — DONE 2026-04-21

`NuvamaOptionPosition`, `NuvamaOptionsSummary` models; `parse_options_positions`, `build_options_summary`; `record_all_options_snapshots` (atomic); `get_monthly_realized_pnl`. 54 new tests.

### ✅ Market Holiday Guard — DONE 2026-04-17

`src/market_calendar/`: `holidays.py` (`load_holidays`, `is_trading_day`, `prev_trading_day`); `nse_2026.yaml`. `daily_snapshot.py` + `nuvama_intraday_tracker.py` guard wired. 31 tests.

### ✅ Atomic Leg Roll CLI — DONE 2026-04-15

`PortfolioStore.record_roll()` — one transaction, two INSERTs. `scripts/roll_leg.py` with `--dry-run`. 14 tests.

### ✅ Model Migration (`src/models/`) — DONE 2026-04-16

`src/models/portfolio.py` + `src/models/mf.py` created; 34 import sites updated; old files deleted.

### ✅ `daily_snapshot.py` split — DONE 2026-04-16

`src/portfolio/summary.py` (6 computation functions) + `src/portfolio/formatting.py` (2 formatting functions) extracted.

### ✅ Indian Number Format — DONE 2026-04-16

`src/utils/number_formatting.py`: `fmt_inr()` + `_group_indian()`. 37 tests.

### ✅ Dhan Portfolio Integration — DONE 2026-04-16

`src/dhan/` package: `DhanHolding`, `DhanPortfolioSummary`, `reader.py`, `store.py`. `dhan_holdings_snapshots` table. Double-count prevention via `exclude_isins`. Upstox batch LTP (not Dhan Data API). `PortfolioSummary` extended with 9 Dhan fields. 152 tests.

### ✅ P3 Performance Sprint — DONE 2026-04-23

AR-8: SQL GROUP BY in `get_cumulative_realized_pnl` (eliminates N+1). AR-9a: `NuvamaClient` protocol + `MockNuvamaClient`. AR-10: N+1 elimination in `get_all_positions_for_strategy`. P3 logging: `print` → structured `logging` across scripts. `p3-script-hygiene-agent.md`, `p3-sql-agent.md`, `p3-protocol-agent.md` prompts executed and committed.

### ✅ P2 Architecture Sprint — DONE 2026-04-22

`PortfolioSummary` composition refactor. Day-change P&L. `PortfolioTracker.record_daily_snapshot` returns `(count, StrategyPnL)` tuple. `record_all_strategies` returns `(dict[str,int], dict[str,StrategyPnL])`.

### ✅ Strategy Spec Validator — DONE 2026-04-25

`scripts/validate_strategy_spec.py` — validates 8 required `##` section headers in `docs/strategies/*.md`. 28 tests.

### ✅ NSE Bhavcopy Pipeline — DONE 2026-05-03

`src/backtest/bhavcopy_ingest.py` + `bhavcopy_loader.py`. `scripts/bhavcopy_bootstrap.py` resumable bulk download. Parquet output `data/offline/options_ohlcv/`. UDiFF migration fix pending (Task 0 in TODOS.md).

### ✅ find_strike_by_delta.py — DONE 2026-05-03

CLI: live option chain → filter by delta range → fixed-width table + dry-run `record_paper_trade.py` commands. 30 offline tests.

### ✅ P&L Visualization decision — RESOLVED 2026-05-03

Decision: keep cumulative inception P&L (vs Nuvama session view). No code changes required.
