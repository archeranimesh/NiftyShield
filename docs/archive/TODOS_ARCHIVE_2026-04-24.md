# NiftyShield — Completed Work Archive

> Archived: 2026-04-24. Contains all completed TODO items and session log through 2026-04-23.
> Active open work lives in [TODOS.md](../../TODOS.md).

---

## Completed Feature TODOs

### TODO-0 — Tests for Nuvama options + intraday (DONE 2026-04-21 via AR-3)

Superseded and completed by AR-3. Added 54 new tests across 3 files:
- `tests/unit/nuvama/test_models.py` — `NuvamaOptionPosition` + `NuvamaOptionsSummary` (11 tests)
- `tests/unit/nuvama/test_options_reader.py` (new file) — `parse_options_positions` + `build_options_summary` (26 tests)
- `tests/unit/nuvama/test_store.py` additions — `record_all_options_snapshots`, `record_intraday_positions`, `get_intraday_extremes`, `purge_old_intraday` (13 tests)

### Market Holiday Guard — DONE 2026-04-17

**Phase 1:** `src/market_calendar/` module:
- `holidays.py`: `load_holidays(year)`, `is_trading_day(d)`, `prev_trading_day(d)` — fail-open on missing YAML, module-level cache
- `src/market_calendar/data/nse_2026.yaml`: 17 NSE 2026 holidays (version-controlled, not gitignored)
- 31 tests in `tests/unit/market_calendar/test_holidays.py`

**Phase 2:** Script guards:
- `scripts/daily_snapshot.py`: early exit if `not is_trading_day(today)` (live mode only)
- `scripts/nuvama_intraday_tracker.py`: same guard

**Data gap:** No rows written on holidays — intentional, calendar-agnostic MAX queries handle gaps correctly.

### TODO-2 — Atomic leg roll CLI — DONE 2026-04-15

`PortfolioStore.record_roll()` — single `_connect` block, two INSERTs, one transaction.
`scripts/roll_leg.py`: `--old-*/--new-*` flag pairs, `_build_trades()` pure, `--dry-run`.
14 new tests (4 `test_trade_store.py` + 10 `test_roll_leg.py`).

### TODO-4 (model migration) — DONE 2026-04-16

`src/models/portfolio.py` + `src/models/mf.py` created. All 34 import sites in `src/`, `scripts/`, `tests/` updated. `src/portfolio/models.py` + `src/mf/models.py` deleted.

### TODO-5 — daily_snapshot.py split — DONE 2026-04-16

`src/portfolio/summary.py` (6 pure computation functions) + `src/portfolio/formatting.py` (2 pure formatting functions) extracted. `daily_snapshot.py` slimmed to I/O orchestration only (~350 lines).

### TODO-8 — Indian number format — DONE 2026-04-16

`src/utils/number_formatting.py`: `fmt_inr()` + `_group_indian()`. All `{:,.0f}` formats replaced. 37 tests.

---

## Completed Architecture Review Items (2026-04-21 → 2026-04-23)

Full review conducted 2026-04-21 against `python-architecture-review.prompt.md` v6. 21 action items (AR-1 → AR-21), all P0–P4 complete. P5 (packaging) deferred to TODOS.md.

---

### P0 — Correctness Bugs

#### AR-1 — Fix `if not raw_ltp:` truthiness check — DONE 2026-04-21

`src/portfolio/tracker.py:209`: `prices.get(key, 0.0)` + `if not raw_ltp:` → `prices.get(key)` + `if raw_ltp is None:`. Zero LTP (option expiring worthless) now used as-is. New test: `test_compute_pnl_zero_ltp_used_as_is`.

#### AR-2 — Fix `if underlying_price:` truthiness check — DONE 2026-04-21

`daily_snapshot.py` lines 163 + 408: `if underlying_price:` → `if underlying_price is not None:` at both occurrences.

---

### P1 — Test Coverage Gap

#### AR-3 — Nuvama options + intraday tests — DONE 2026-04-21

See TODO-0 above. 54 new tests. 847 passing.

---

### P2 — Architecture

#### AR-4 — Refactor `PortfolioSummary` to per-source composition — DONE 2026-04-22

`src/models/portfolio.py`: Replaced 26-field flat accumulator with 16-field composed model. Four typed Optional source references: `mf_pnl`, `dhan`, `nuvama_bonds`, `nuvama_options`. Availability via computed `@property`. `TYPE_CHECKING` guards on all source type annotations.

`src/portfolio/summary.py`: `_build_portfolio_summary` computes only cross-source aggregates; dead intermediate extraction variables removed.

`src/portfolio/formatting.py`: All double-guards inside available-checks eliminated. `test_portfolio_summary_nuvama.py` deleted (superseded). `test_telegram_formatting.py` added. Commit: `4de0ec4`.

#### AR-5 — Type `object | None` params in `_build_portfolio_summary` — DONE 2026-04-22

Added `TYPE_CHECKING` imports in `summary.py` + `formatting.py`. All 14 `# type: ignore[union-attr]` suppressions removed.

#### AR-6 — Fix `NuvamaBondHolding` historical reconstruction hack — DONE 2026-04-22

`src/nuvama/store.py`: `get_snapshot_for_date` returns `dict[str, dict]` with `qty/ltp/current_value` keys. `_historical_main` reconstructs true `NuvamaBondHolding` objects from stored `qty` + `ltp` — the `qty=1` stub is gone.

#### AR-7 — Make `record_all_snapshots` + `record_all_options_snapshots` atomic — DONE 2026-04-22

Both methods rewritten to use `executemany` inside a single `with connect() as conn:` block. Matches `PortfolioStore.record_snapshots_bulk()` pattern. Rollback tests added.

#### AR-9 — Wrap Nuvama APIConnect SDK behind a 2-method protocol — DONE 2026-04-23

`src/nuvama/protocol.py` (new): `NuvamaClient` protocol (`Holdings()` + `NetPosition()`). `MockNuvamaClient` added. `fetch_nuvama_portfolio()` and `nuvama_intraday_tracker.py` accept `NuvamaClient`. Type annotation wired into `daily_snapshot.py`. Uninitialized locals fallback fixed.

---

### P3 — Performance & Structural Correctness

#### AR-8 — SQL `GROUP BY` in `get_cumulative_realized_pnl` — DONE 2026-04-23

`src/nuvama/store.py`: Replaced Python loop aggregation with a single SQL `GROUP BY trade_symbol` query. Result set bounded regardless of history depth. Returns `{trade_symbol: Decimal(row["cumulative"])}` — boundary cast preserves Decimal invariant.

#### AR-10 — Batch `get_all_positions_for_strategy` to eliminate N+1 — DONE 2026-04-23

`src/portfolio/store.py`: Replaced loop over `get_position()` (8 connections, 7 full scans per call) with a single SQL aggregate query. `avg_price` computed from `buy_value / buy_qty` in Python with Decimal.

#### AR-11 — Eliminate double LTP fetch in `_async_main` — DONE 2026-04-23

`PortfolioTracker._build_strategy_pnl` extracted. `record_daily_snapshot` and `record_all_strategies` now accept master `prices` dict and return computed `StrategyPnL` — eliminating the redundant `compute_pnl()` re-fetch. Any caller unpacking the old single-value return must unpack as `count, pnl = ...`.

#### AR-12 — Defer module-level I/O imports in `nuvama_intraday_tracker.py` — DONE 2026-04-23

`load_api_connect`, `NuvamaStore`, `parse_options_positions`, `create_client`, `LTPFetchError` imports moved inside `async def main()`. Matches `daily_snapshot.py` pattern.

---

### P4 — Observability & Hygiene

All 7 items completed 2026-04-21. 859 tests passing.

#### AR-13 — `logger.exception()` in `nuvama_intraday_tracker.py` — DONE

Replaced `logger.error("...: %s", e)` + `traceback.print_exc()` with `logger.exception("run_id=%s ...", run_id)`.

#### AR-14 — Run/correlation ID — DONE

`run_id = uuid.uuid4().hex[:8]` added to `_async_main` and `nuvama_intraday_tracker.main()`. All non-fatal WARNING blocks include `[{run_id}]`.

#### AR-15 — Delete TD-6 dead assert — DONE (pre-existing)

`src/client/upstox_live.py:46` — assert was already absent; verified via grep.

#### AR-16 — Fix `__import__("datetime").date.today()` — DONE

`src/portfolio/tracker.py:126`: replaced with `date.today()` — `date` already imported at line 12.

#### AR-17 — Fix `classify_holding()` return type — DONE

Added `AssetType.BOND = "BOND"` enum variant. `DhanHolding.classification: str` → `AssetType`. Updated `classify_holding()`, all string comparisons in `build_dhan_summary()`, and 4 test files.

#### AR-18 — Remove unnecessary `Decimal` round-trip in `_etf_cost_basis` — DONE

`src/portfolio/summary.py:60`: `Decimal(str(leg.entry_price)) * Decimal(str(leg.quantity))` → `leg.entry_price * leg.quantity`. Test stubs updated to convert `float → Decimal` at helper boundary.

#### AR-19 — Fix `nifty_spot DECIMAL` → `REAL` in intraday schema — DONE

`src/nuvama/store.py` DDL changed to `REAL`. `_INTRADAY_SCHEMA_VERSION = 1` guard via `PRAGMA user_version` — drops and recreates 30-day-retention table on first deploy. `float(str(nifty))` → `float(nifty)`.

---

## Completed Technical Debt Items

### TD-3 — Vertical token alignment — DONE 2026-04-16

Stripped vertical alignment padding from stub type alias block in `src/client/protocol.py` lines 43–53. Normalised to 2-space inline comment per §3.6.

### TD-5 — `except Exception` without intent comment — DONE 2026-04-16

Intent comments added to all four broad catches (`dhan_verify.py:165,184` + `nuvama_verify.py:154,177`).

### TD-6 — Stale `assert` in production module — RESOLVED (pre-existing)

`src/client/upstox_live.py:46`: verified via grep — assert was already absent. No action needed.

### TD-7 — TODO format missing bug reference — DONE 2026-04-17

All `# TODO:` comments updated to `# TODO: TD-7 — description` format per §3.12. 2 in `tracker.py`, 11 in `protocol.py`.

---

## Session Log (2026-04-01 → 2026-04-21)

| Date | What Changed |
|---|---|
| 2026-04-01 — 2026-04-04 | **Foundation sprint.** Auth, portfolio module, full MF stack (models/store/nav_fetcher/tracker), daily snapshot cron, seed scripts. All 11 AMFI codes corrected against live AMFI flat file. 8-point code review applied (Decimal migration, shared db.py, enum compat, exception hierarchy, deferred I/O imports). 176 offline tests green. DB wiped and re-seeded; clean baseline from 2026-04-06. |
| 2026-04-07 | `--date` historical query mode, day-change delta, `_compute_prev_mf_pnl`. 211 tests all green. |
| 2026-04-08 | **Telegram notifications.** `src/notifications/telegram.py`: `TelegramNotifier` + `build_notifier()`. Raw requests, HTML parse_mode, `<pre>` block. Non-fatal. `_format_combined_summary()` extracted. 25 new tests, 236 total. |
| 2026-04-08 | **Exception hierarchy.** `src/client/exceptions.py` expanded: `AuthenticationError`, `RateLimitError`, `OrderRejectedError`, `InsufficientMarginError`, `InstrumentNotFoundError`. 9 new tests in `test_exceptions.py`. 254 total. |
| 2026-04-08 | **BrokerClient protocol layer.** `src/client/protocol.py`: `BrokerClient` + `MarketStream` full protocols; sub-protocols; 11 stub type aliases. `MarketDataProvider` migrated from `tracker.py`. 11 new tests. 265 total. |
| 2026-04-08 | **`PortfolioSummary` extraction.** Frozen dataclass in `src/models/portfolio.py`. `_build_portfolio_summary()` owns all arithmetic. 10 new tests, 246 total. |
| 2026-04-08 | **`UpstoxLiveClient` (5.c).** `src/client/upstox_live.py`. `get_ltp` + `get_option_chain` delegate to `UpstoxMarketClient`. Blocked methods raise `NotImplementedError`. 14 tests. 279 total. |
| 2026-04-08 | **`MockBrokerClient` (5.d).** `src/client/mock_client.py`. Stateful offline broker. `simulate_error` (one-shot). `reset()`. 38 tests. |
| 2026-04-08 | **`factory.py` (5.e).** `create_client(env)` composition root. Sole importer of concrete clients. 10 tests. |
| 2026-04-08 | **Consumer migration (5.f).** `daily_snapshot.py` uses `create_client(UPSTOX_ENV)`. `UpstoxMarketClient` no longer imported outside `src/client/`. 327 tests. |
| 2026-04-08 | **Trade ledger.** `TradeAction` + `Trade` models. `trades` table. `seed_trades.py` + `record_trade.py`. LIQUIDBEES key verified. 58 new tests. 385 total. |
| 2026-04-08 | **Trade overlay.** `get_all_positions_for_strategy()`. `apply_trade_positions()` pure function. Wired into `_async_main` and `_historical_main`. 17 new tests. 400 total. |
| 2026-04-08 | **Trade overlay internalized + strategy name fix.** `_get_overlaid_strategy()` / `_get_all_overlaid_strategies()` added to `PortfolioTracker`. `ensure_leg()` added to `PortfolioStore`. `trades.strategy_name` migrated from `ILTS`/`FinRakshak` to `finideas_ilts`/`finrakshak`. |
| 2026-04-10 | **Nuvama auth layer.** `src/auth/nuvama_login.py` + `nuvama_verify.py`. `APIConnect` session persists in `NUVAMA_SETTINGS_FILE`. 33 offline tests. Read-only scope. |
| 2026-04-10 | **Nuvama verify confirmed live.** 6 holdings: 5 EFSL NCDs + 1 GOI loan bond + 1 Sovereign Gold Bond. LTPs populated. |
| 2026-04-12 | **Context reorganisation.** CONTEXT.md split into CONTEXT.md + DECISIONS.md + REFERENCES.md + TODOS.md. PLANNER.md added. CLAUDE.md tightened. Module CLAUDE.md files created: `src/portfolio/`, `src/mf/`, `src/client/`, `src/notifications/`. `.claude/skills/commit/SKILL.md`. `.claude/agents/code-reviewer.md` + `test-runner.md`. Stale docs moved to `docs/archive/`. |
| 2026-04-13 | **Dhan auth layer.** `src/auth/dhan_login.py` + `dhan_verify.py`. Manual 24h token flow. Raw `requests` (no SDK). Pure functions: `build_login_url()`, `validate_token()`, `save_token()`, `load_dhan_credentials()`, `fetch_profile()`, `fetch_holdings()`, `parse_holdings()`. 31 offline tests. 431 total. |
| 2026-04-14 | **Dhan LTP fix — switch to Upstox batch fetch.** Dhan `POST /v2/marketfeed/ltp` returns 401 on free tier. `enrich_with_upstox_prices()` + `upstox_keys_for_holdings()` added. Dhan holdings pre-fetched, keys added to Upstox batch. 9 new tests. 558 total. |
| 2026-04-14 | **Dhan portfolio integration.** `src/dhan/` module: `models.py`, `reader.py`, `store.py`. `daily_snapshot.py` wired (non-fatal, strategy ISINs excluded). 81 new tests. 549 total. |
| 2026-04-15 | **Fuzzy instrument search.** `src/instruments/lookup.py`: `_score_query()` + `_best_score()` via rapidfuzz (difflib fallback). `min_score` param. 27 tests. 585 total. |
| 2026-04-15 | **quant-4pc-local analysed.** Prior research repo reviewed. Reusable: `BacktestEngine`, `Strategy` protocol, `IronCondorStrategy`, data normalisation patterns, retry/backoff. Porting notes in `PLANNER.md`. |
| 2026-04-15 | **Atomic leg roll CLI (TODO-2).** `PortfolioStore.record_roll()`. `scripts/roll_leg.py`. 14 tests. 599 total. |
| 2026-04-15 | **Nuvama bond portfolio integration — all 4 phases.** `src/nuvama/` module: `models.py`, `reader.py`, `store.py`. `scripts/seed_nuvama_positions.py`. `PortfolioSummary` extended. 97 new tests. |
| 2026-04-15 | **fix(scripts): `os._exit()` for daily_snapshot.py.** APIConnect non-daemon Feed thread caused `sys.exit()` to hang. Commit: `7a49720`. |
| 2026-04-16 | **Nuvama option PnL reporting.** Extended `src/nuvama/` to parse `NetPosition()`, fetch cumulative PnL from DB, output realized/unrealized metrics. Wired into `daily_snapshot.py` formatting. |
| 2026-04-16 | **TD-3 resolved.** Stripped alignment padding from `src/client/protocol.py`. |
| 2026-04-16 | **`src/models/` migration (TODO-4) complete.** All 34 import sites updated. Old `portfolio/models.py` + `mf/models.py` deleted. |
| 2026-04-16 | **Indian number format (TODO-8) complete.** `src/utils/number_formatting.py`. 37 tests. 774 passing. |
| 2026-04-16 | **daily_snapshot.py split (TODO-5) complete.** `src/portfolio/summary.py` + `src/portfolio/formatting.py` extracted. 717 tests passing. |
| 2026-04-17 | **Intraday tracking for options.** `nuvama_intraday_snapshots` table, 30-day retention. `scripts/nuvama_intraday_tracker.py`. 5-minute sampling of options PnL + Nifty spot bounds. Telegram wired. |
| 2026-04-17 | **Market holiday guard — complete.** `src/market_calendar/` module. `nse_2026.yaml`. Guards in `daily_snapshot.py` + `nuvama_intraday_tracker.py`. 31 tests. `.gitignore` anchored to `/data/`. |
| 2026-04-17 | **Doc sync.** CONTEXT.md, DECISIONS.md updated for all 2026-04-16/17 additions. |
| 2026-04-21 | **Architecture review.** Full top-down review using `python-architecture-review.prompt.md` v6. 21 action items (AR-1 → AR-21). |
| 2026-04-21 | **P0 correctness fixes (AR-1, AR-2).** Zero-LTP bug + underlying_price truthiness bugs fixed. 785 tests passing. |
| 2026-04-21 | **P4 hygiene (AR-13 → AR-19).** exc_info, run_id, dead assert, date.today(), AssetType.BOND, Decimal round-trip, intraday schema REAL + version guard. 859 tests. |
| 2026-04-21 | **P1 test coverage (AR-3).** 54 new Nuvama options + intraday tests. 847 passing. |
| 2026-04-22 | **Morning NAV backfill.** `scripts/morning_nav.py`: fetches AMFI NAVs for `prev_trading_day(today)`. Fixes stale T-2 NAV written by 15:45 cron. `--date` override for manual recovery. 6 tests. Cron: `15 9 * * 1-5`. |
| 2026-04-22 | **P2 architecture refactor (AR-4, AR-5, AR-6, AR-7).** `PortfolioSummary` refactored from 26-field flat to 16-field composed model with typed Optional source refs. `record_all_snapshots` + `record_all_options_snapshots` atomic via `executemany`. Historical bond reconstruction uses real `qty`+`ltp` (no `qty=1` stub). All 14 `# type: ignore[union-attr]` suppressions removed. 846 passing. Commit: `4de0ec4`. |
| 2026-04-23 | **P3 architecture refactor (AR-8, AR-9, AR-10, AR-11, AR-12).** `get_cumulative_realized_pnl` uses SQL `GROUP BY` (bounded result set). `get_all_positions_for_strategy` uses single aggregate query (N+1 eliminated). `NuvamaClient` protocol + `MockNuvamaClient` created. Deferred I/O imports in `nuvama_intraday_tracker.py`. `record_all_strategies` returns `dict[str, StrategyPnL]` — double LTP fetch eliminated. 854 passing. |
| 2026-04-24 | **P4 packaging hygiene (AR-20, AR-21).** Removed `uuid==1.30` stdlib shim. Created `requirements-dev.txt` (pytest, pytest-asyncio, RapidFuzz). |
| 2026-04-24 | **Claude token optimisation (AR-22, AR-23).** Graph project ID added to CLAUDE.md Quick Reference. git-log promoted to step 0 in Rule 0. `Rule 1 — Bash Output Discipline` added with four-pattern contract table. |
| 2026-04-24 | **DEBT-2 line length (TD-2).** 11 lines >100 chars wrapped across `src/portfolio/store.py`, `src/nuvama/store.py`, `src/dhan/reader.py`, `src/models/portfolio.py`. 868 tests pass. |
| 2026-04-24 | **DEBT-4 SELECT * (TD-5).** Named column lists in all store `get_*` methods. `get_options_snapshot_for_date` → `list[NuvamaOptionPosition]` (typed). `get_snapshots_for_date` + `get_nav_snapshots_for_date` also fixed. 868 tests pass. |
| 2026-04-24 | **Root markdown cleanup.** Archived all ✅ DONE items (PKG-1–4, DEBT-2,4,5) here. Moved `python-architecture-review.prompt.md` to `docs/`. Updated README.md actual src/ layout. Wrote `.claude/skills/md-cleanup/SKILL.md`. |

---

## Completed P4-PKG Items (2026-04-24)

### PKG-1: Remove `uuid==1.30` from `requirements.txt` (AR-20)
All `import uuid` usages hit stdlib — PyPI shim was a transitive leak. Removed from `requirements.txt`.

### PKG-2: Split `requirements-dev.txt` (AR-21)
Created `requirements-dev.txt` (`-r requirements.txt` + pytest, pytest-asyncio, RapidFuzz). All three removed from `requirements.txt`.

### PKG-3: Document graph project ID in `CLAUDE.md` (AR-22)
Added `| Graph project ID | \`Users-abhadra-myWork-myCode-python-NiftyShield\` |` to Quick Reference table.

### PKG-4: Bash output discipline in `CLAUDE.md` (AR-23)
`Rule 1 — Bash Output Discipline` added with four-pattern contract (aggregate → SUM/COUNT, diagnostic → named cols + LIMIT 10, test runs → --tb=no -q, log reads → tail/grep). Token math included.

---

## Completed P5-DEBT Items (2026-04-24)

### DEBT-2: Line length violations (TD-2)
11 lines >100 chars wrapped across 5 files. 868 tests pass.

### DEBT-4: `SELECT *` over-fetch in store layer (TD-5)
Named column lists in all store `get_*` methods. `get_options_snapshot_for_date` → `list[NuvamaOptionPosition]`. 868 tests pass.

### DEBT-5: Pre-aggregate bash output (TD-6)
Completed as part of PKG-4. `Rule 1 — Bash Output Discipline` in `CLAUDE.md` satisfies full DoD.
