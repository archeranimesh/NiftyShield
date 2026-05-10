# NiftyShield — TODOs Archive (2026-05-01 to 2026-05-09)

> Archived from `TODOS.md` on 2026-05-10.
> For the active task list see `TODOS.md`.
> Earlier archive (2026-04-01 → 2026-04-30): `TODOS_ARCHIVE_2026-05-01.md`

---

## Completed P1-NEXT Tasks

### ✓ NSE F&O Bhavcopy ingestion pipeline — DONE 2026-05-03

`src/backtest/bhavcopy_ingest.py` shipped. Full scope:

- `download_bhavcopy(date)` → downloads daily CSV ZIP from NSE CDN with ≥1 s politeness delay.
- `parse_bhavcopy(csv_path)` → filters `OPTIDX` / `OPTSTK` + `SYMBOL == 'NIFTY'`; returns list of `BhavRecord` (frozen Pydantic dataclass with `Decimal` invariant on all price fields).
- `parse_option_symbol(symbol)` → handles weekly and monthly NSE symbol formats; `ValueError` on unrecognised pattern.
- Parquet output: `data/offline/options_ohlcv/{year}/{month}/`, idempotent (skip if date already ingested).
- `scripts/bhavcopy_bootstrap.py`: resumable bulk download 2016-01-01 → today; graceful 404 on holidays.
- `src/backtest/bhavcopy_loader.py`: `load_options_ohlcv(underlying, start, end) → pd.DataFrame`.
- Tests: fixture-driven (no network); `parse_option_symbol` round-trips; format detection and routing.
- **UDiFF migration discovered 2026-05-03:** legacy URL breaks from Dec 2024. Fix required — see Task 0 in active `TODOS.md`.

---

## Session Log (2026-05-01 → 2026-05-09)

| Date | What Changed |
|---|---|
| 2026-05-09 | **TrueData 1-min data plan.** `BACKTEST_PLAN_PHASE1.md` task 1.3b added: TrueData historical dump ingestion pipeline spec (₹7,999/year for 3 years 2022–2024). CSV format confirmed from sample: headerless 8-column, sparse minutes, two filename formats (weekly YYMMDD / monthly YYMMMM). `DECISIONS.md → TrueData Historical Dump (2026-05-09)` added. No code — start only after TrueData delivers zip files. |
| 2026-05-08 | **Intraday market store review fixes (3 commits).** `4d972c6`: Google-style docstrings on all public `IntradayMarketStore` methods, removed unused `sqlite3` import, renamed orchestrator logger `"intraday"` → `"market"`. `a259115`: UTC timezone-awareness enforced in `record_market_snapshot` — raises `ValueError` on naive `datetime`, converts to ISO string before SQLite insert. `a192727`: test coverage for the naive-timestamp `ValueError` contract. |
| 2026-05-08 | **Intraday Tracker Schema Refactor (Phases 1–3).** Phase 1: `src/intraday/market_store.py` (`IntradayMarketStore` + `intraday_market_snapshots` table) isolates market context (Nifty+VIX). Phase 2: Nuvama v3 schema migration (`_SCHEMA_VERSION = 3`, `DROP COLUMN nifty_spot` from `nuvama_intraday_snapshots`). Phase 3: Orchestrator `scripts/intraday_tracker.py` fetches Nifty+VIX once async and passes to both Dhan and Nuvama trackers. Test coverage maintained. |
| 2026-05-08 | **Doc cleanup.** Archived 12 completed/obsolete docs (SHA 254689e): bhavcopy plans/walkthroughs, antigravity global.md, plan story files for tasks 0.1/0.2/0.5/dhan-intraday, superseded csp_niftybees_v1.md, one-time prompts, resolved council pending prompt. Pruned PLANNER.md stale April sprint section (SHA d03259e). |
| 2026-05-06 | **Dhan intraday options tracking complete (Phases A–E).** Phase A: `DhanOptionPosition`, `DhanOptionsSummary`, `DhanFundLimit` frozen dataclasses in `src/dhan/models.py`. Phase B: `src/dhan/positions.py` — `fetch_positions_raw`, `parse_option_positions`, `filter_intraday_options` (keeps NSE_FNO + productType in INTRADAY/MARGIN; MARGIN=Dhan API name for what UI labels Normal), `build_options_summary`, `fetch_fund_limit_raw`, `parse_fund_limit` (maps `availabelBalance` typo), `format_options_section`. Phase C: `DhanStore` extended with `dhan_options_snapshots` + `dhan_margin_snapshots` tables + 5 methods. Phase D: `scripts/dhan_intraday_tracker.py` + `scripts/intraday_tracker.py` (combined Dhan+Nuvama orchestrator, `*/15 9-15 * * 1-5`). Phase E: `NuvamaOptionsSummary.monthly_realized_pnl` field + `NuvamaStore.get_monthly_realized_pnl` + `build_options_summary(monthly_historical_pnl)` + `formatting.py` split into Today/Month/Realized three lines. Fixture updated to real 2026-05-06 Dhan values (MARGIN productType discovery). 428 targeted tests passing. |
| 2026-05-04 | **Overlay automation complete (Phases A–E).** Phase A: `PaperLegSnapshot` dataclass + `paper_leg_snapshots` table + 4 new `PaperStore` methods. Phase B: `scripts/paper_3track_overlay.py` — live-fetch overlay entry (PP/CC/collar) across all 3 tracks; CC permanently blocked on futures; `_check_existing_overlay` tracks SELL positions; atomic rollback via `delete_trade`. Phase C: `scripts/paper_3track_snapshot.py` — canonical EOD cron; live spot fetch; per-leg delta-from-yesterday display; writes `paper_leg_snapshots`. Phase D: `scripts/paper_3track_overlay_roll.py` — `_parse_expiry_from_key` regex; `_find_expiring_overlay` (DTE gate + force bypass); `_roll_single` 2-trade atomic; `_roll_collar` 4-trade atomic with full rollback chain. Phase E: docs updated. 83 tests across Phases A–D passing. |
| 2026-05-03 | **Task 0.4b complete.** `docs/strategies/nifty_track_comparison_v1.md` written — 3-track Nifty instrument comparison spec (Track A NiftyBees / Track B Futures / Track C Deep ITM Call) per council `2026-05-02_nifty-long-instrument-comparison-protection.md` Stage 3. Passes `validate_strategy_spec.py`. Unblocks task 0.6b. |
| 2026-05-03 | **NSE UDiFF migration discovered.** Legacy bhavcopy URL confirmed working up to 2024-04-25; broken from 2024-12-02. New UDiFF URL and schema (34 columns, ISO dates, `FinInstrmTp` codes) documented in `DECISIONS.md → NSE Bhavcopy Format Migration`. Safe bootstrap range: `--end 2024-11-01`. |
| 2026-05-03 | **Phase 1.3 bhavcopy ingestion shipped.** `src/backtest/__init__.py`, `bhavcopy_ingest.py`, `bhavcopy_loader.py`. See completed section above. |
| 2026-05-03 | **`scripts/find_strike_by_delta.py` added.** CLI: live option chain → filter strikes by |delta| range → fixed-width table (strike/IV/ltp/mid/bid/ask/OI/key) + dry-run `record_paper_trade.py` commands. 30 offline unit tests in `tests/unit/test_find_strike_by_delta.py`. |
| 2026-05-02 | **Council decision ingested — variance gate regime completeness.** `DECISIONS.md` updated (Variance Gate section); `BACKTEST_PLAN.md` Phase 0.8 gate revised (criteria A–D); `docs/plan/variance_gate.md` created. |
| 2026-05-02 | **Council decision ingested — near-expiry gamma buy research.** `DECISIONS.md` updated with Signal Hierarchy Decisions; no code — data collection only until Phase 3 gate. |
| 2026-05-01 | **Root markdown cleanup.** Session log (2026-04-27 → 2026-04-30) archived to `TODOS_ARCHIVE_2026-05-01.md`; `CONTEXT.md` date + test count updated; `README.md` project structure synced. |
