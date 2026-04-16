# NiftyShield — TODOs & Session Log

---

## Open TODOs (priority order)

### ~~0. Nuvama bond portfolio integration~~ — **DONE (2026-04-15)**

New module `src/nuvama/` fetching bond holdings from Nuvama APIConnect and adding them to the daily snapshot Bonds section.

**Schema probe completed 2026-04-15.** Key findings:
- `rmsHdg` records have: `isin`, `cpName`, `ltp`, `totalQty`, `totalVal`, `chgP`, `exc`, `hairCut`, `sym`, `trdSym`, `dpName`, `asTyp`. No `avgPrice`.
- Cost basis seeded manually via `scripts/seed_nuvama_positions.py` into `nuvama_positions` table in `portfolio.sqlite`.
- Day-change delta derived from `chgP` field (percent) — no prior snapshot needed.
- LIQUIDBEES (`INF732E01037`) excluded by ISIN (already tracked in ILTS strategy).
- All holdings classified as BOND (Nuvama account is bonds-only).

**Phase plan:**
1. `src/nuvama/` models + reader (pure functions) + tests → commit
2. `src/nuvama/store.py` + `scripts/seed_nuvama_positions.py` + tests → commit
3. `src/portfolio/models.py` — add `nuvama_*` fields to `PortfolioSummary` + tests → commit
4. `scripts/daily_snapshot.py` wiring (`_async_main`, `_build_portfolio_summary`, `_format_combined_summary`) + tests → commit

**Known positions (for seed script):**

| ISIN | Instrument | Qty | Avg Price |
|---|---|---|---|
| `INE532F07FD3` | EFSL 10% NCD 2034 | 700 | ₹1,000.00 |
| `INE532F07EC8` | EFSL 9.20% NCD 2026 | 500 | ₹1,000.00 |
| `INE532F07DK3` | EFSL 9.67% NCD 2028 | 1,200 | ₹1,001.06 |
| `INE532F07FN2` | EFSL 9.67% NCD 2029 | 700 | ₹1,000.00 |
| `IN0020070069` | G-Sec 8.28% 2027 | 2,000 | ₹109.00 |
| `IN0020230168` | SGB 2031 2.50% | 50 | ₹6,199.00 |

### 1. Greeks capture
Fix option chain call (`NSE_INDEX|Nifty 50`), define `OptionChain` Pydantic model, implement `_extract_greeks_from_chain()`.
Fixture `nifty_chain_2026-04-07.json` already recorded in `tests/fixtures/responses/` — use it to drive model definition.
Blocked by: nothing. Next after Nuvama integration.

### ~~2. `scripts/roll_leg.py`~~ — **DONE (2026-04-15)**
`PortfolioStore.record_roll(close_trade, open_trade)` added — single `_connect` block, both INSERTs atomic. `scripts/roll_leg.py` CLI: `--old-*/--new-*` flag pairs, `_build_trades()` pure function, `--dry-run`. 14 new tests (4 store + 10 script). 599 total, all pre-existing failures unchanged.

### 3. P&L visualization
Matplotlib script or React dashboard from `daily_snapshots` time series.
Deferred until several weeks of snapshot history exist.
`PortfolioSummary` dataclass already extracted — ready to query.

### 5. Split `scripts/daily_snapshot.py` into focused modules

The script has grown to ~600 lines with three distinct responsibilities mixed together. Split into:

- **`src/portfolio/summary.py`** — pure computation: `_etf_current_value`, `_etf_cost_basis`, `_build_prev_prices`, `_compute_prev_mf_pnl`, `_build_portfolio_summary`, `_compute_strategy_pnl_from_prices`. No I/O, no imports beyond models. Fully unit-testable in isolation.
- **`src/portfolio/formatting.py`** — pure formatting: `_format_combined_summary`, `_format_protection_stats`. Depends only on `PortfolioSummary` — zero I/O. Test by asserting substring/line presence.
- **`scripts/daily_snapshot.py`** — thin I/O orchestration only: `_async_main`, `_historical_main`, `main()`, `parse_args()`. Imports summary + formatting from `src/portfolio/`. No arithmetic here.

**Phase boundaries and commits:**
1. Extract `summary.py` + tests → commit (`refactor(portfolio): extract summary computation`)
2. Extract `formatting.py` + tests → commit (`refactor(portfolio): extract summary formatting`)
3. Slim down `daily_snapshot.py` (orchestration only) → update CONTEXT.md → commit (`refactor(scripts): daily_snapshot orchestration only`)

**Why:** Current file mixes pure functions (fully testable) with async I/O, making unit tests brittle. Moves reusable computation into `src/` where the backtesting and visualization layers (TODO 3) can import it directly without going through the script.

**Pre-condition:** No new features during this refactor. Test count must not change.

### 6. Fuzzy instrument search (`rapidfuzz`) — **DONE (2026-04-15)**
`InstrumentLookup.search()` upgraded: `exact(1.0) > prefix(0.92) > fuzzy` ranking via `_score_query()` + `_best_score()`. `min_score` param added. 27 tests in `tests/unit/instruments/test_lookup.py`.

**Remaining deployment step:** add `rapidfuzz` to `requirements.txt`.
The implementation falls back silently to `difflib` when rapidfuzz is absent, but rapidfuzz is ~10–50× faster on the full NSE BOD file (~100k instruments).

To verify rapidfuzz is active in the venv:
```bash
python -c "from rapidfuzz import fuzz; print('rapidfuzz OK:', fuzz.token_set_ratio('NIFTY', 'nifty'))"
# Expected: rapidfuzz OK: 100.0
```

To install:
```bash
pip install rapidfuzz          # inside venv
# or pin it:
echo "rapidfuzz>=3.0" >> requirements.txt
pip install -r requirements.txt
```

### 4. `src/models/` migration
Move `portfolio/models.py` Pydantic models and `mf/models.py` models to `src/models/`.
Do in one commit with `src/strategy/` start — they migrate together.

---

## Tech Debt — Google Python Style Guide Violations

Identified 2026-04-16 via full audit against the PDF style guide. Existing code is NOT being changed in place — these are tracked for systematic cleanup when refactoring adjacent code.

### TD-1: `@staticmethod` overuse (§2.17 — "Never use `staticmethod`")

The guide says to use module-level `_private_function()` instead. Each `@staticmethod` below should become a standalone `_function(...)` at module scope. Change is mechanical — no logic changes.

| File | Method |
|---|---|
| `src/mf/store.py` | `_row_to_transaction()`, `_row_to_nav_snapshot()` |
| `src/portfolio/store.py` | `_row_to_leg()`, `_row_to_snapshot()` |
| `src/portfolio/tracker.py` | `_extract_greeks_from_chain()` |
| `src/dhan/store.py` | `_row_to_holding()` |
| `src/instruments/lookup.py` | `_score_query()` or similar |
| `src/client/upstox_market.py` | row-mapping helper |

**Approach:** Do one module at a time as part of adjacent refactoring work. Never worth a standalone commit.

### TD-2: Line length violations (§3.2 — 80 char limit)

~44 lines exceed 80 chars; 7 lines exceed 100 chars. The 7 >100 lines are the priority — they are unwrapped f-strings or SQL concatenations and are clearly fixable.

| File | Lines |
|---|---|
| `src/portfolio/store.py` | L129 (116c), L292 (102c), L621 (111c) |
| `src/nuvama/store.py` | L229 (104c) |
| `src/dhan/reader.py` | L167 (101c) |
| `src/portfolio/models.py` | L95 (102c) |
| `src/portfolio/tracker.py` | L126 (102c) |

### TD-3: Vertical token alignment (§3.6 — "Don't use spaces to vertically align")

`src/client/protocol.py` lines 43–53: the `= Any      # TODO:` stub assignments use extra spaces to align the comment column. Strip the padding — 11 lines, 5-minute fix.

### TD-4: Missing license boilerplate (§3.8.2)

Every file should contain a license header. Zero files have one. Decision needed on which license to use before this can be automated.

### TD-5: `except Exception` without intent comment (§2.4)

The guide allows broad catches only at documented isolation points. These two need a one-line comment explaining they are intentional:

- `src/auth/dhan_verify.py` lines 165, 184
- `src/auth/nuvama_verify.py` lines 154, 177

### TD-6: Stale `assert` in production module (§2.4)

`src/client/upstox_live.py:46` has `assert issubclass(type, type)` — reads like a placeholder that was never removed. Investigate and delete or replace with a real check.

### TD-7: TODO format missing bug reference (§3.12)

Current format: `# TODO: description`
Required format: `# TODO: <issue-url-or-ref> — description`

All existing `# TODO:` comments need a GitHub issue or reference link added. Low priority — only matters for searchability.

---

## Session Log

| Date | What Changed |
|---|---|
| 2026-04-01 — 2026-04-04 | **Foundation sprint.** Auth, portfolio module, full MF stack (models/store/nav_fetcher/tracker), daily snapshot cron, seed scripts. All 11 AMFI codes corrected against live AMFI flat file. 8-point code review applied (Decimal migration, shared db.py, enum compat, exception hierarchy, deferred I/O imports). 176 offline tests green. DB wiped and re-seeded; clean baseline from 2026-04-06. |
| 2026-04-07 | `--date` historical query mode, day-change delta, `_compute_prev_mf_pnl`. 211 tests all green. |
| 2026-04-08 | **Telegram notifications.** `src/notifications/telegram.py`: `TelegramNotifier` + `build_notifier()`. Raw requests, HTML parse_mode, `<pre>` block. Non-fatal. `_format_combined_summary()` extracted. 25 new tests, 236 total. |
| 2026-04-08 | **Exception hierarchy.** `src/client/exceptions.py` expanded: `AuthenticationError`, `RateLimitError`, `OrderRejectedError`, `InsufficientMarginError`, `InstrumentNotFoundError`. 9 new tests in `test_exceptions.py`. 254 total. |
| 2026-04-08 | **BrokerClient protocol layer.** `src/client/protocol.py`: `BrokerClient` + `MarketStream` full protocols; sub-protocols; 11 stub type aliases. `MarketDataProvider` migrated from `tracker.py`. 11 new tests. 265 total. |
| 2026-04-08 | **`PortfolioSummary` extraction.** Frozen dataclass in `src/portfolio/models.py`. `_build_portfolio_summary()` owns all arithmetic. 10 new tests, 246 total. |
| 2026-04-08 | **`UpstoxLiveClient` (5.c).** `src/client/upstox_live.py`. `get_ltp` + `get_option_chain` delegate to `UpstoxMarketClient`. Blocked methods raise `NotImplementedError`. 14 tests. 279 total. |
| 2026-04-08 | **`MockBrokerClient` (5.d).** `src/client/mock_client.py`. Stateful offline broker. `simulate_error` (one-shot). `reset()`. 38 tests. |
| 2026-04-08 | **`factory.py` (5.e).** `create_client(env)` composition root. Sole importer of concrete clients. 10 tests. |
| 2026-04-08 | **Consumer migration (5.f).** `daily_snapshot.py` uses `create_client(UPSTOX_ENV)`. `UpstoxMarketClient` no longer imported outside `src/client/`. 327 tests. |
| 2026-04-08 | **Trade ledger.** `TradeAction` + `Trade` models. `trades` table. `seed_trades.py` + `record_trade.py`. LIQUIDBEES key verified. 58 new tests. 385 total. |
| 2026-04-08 | **Trade overlay.** `get_all_positions_for_strategy()`. `apply_trade_positions()` pure function. Wired into `_async_main` and `_historical_main`. 17 new tests. 400 total. |
| 2026-04-08 | **Trade overlay internalized + strategy name fix.** `_get_overlaid_strategy()` / `_get_all_overlaid_strategies()` added to `PortfolioTracker`. `ensure_leg()` added to `PortfolioStore`. `trades.strategy_name` migrated from `ILTS`/`FinRakshak` to `finideas_ilts`/`finrakshak`. |
| 2026-04-10 | **Nuvama auth layer.** `src/auth/nuvama_login.py` + `nuvama_verify.py`. `APIConnect` session persists in `NUVAMA_SETTINGS_FILE`. 33 offline tests. Read-only scope. |
| 2026-04-10 | **Nuvama verify confirmed live.** 6 holdings: 5 EFSL NCDs + 1 GOI loan bond + 1 Sovereign Gold Bond. LTPs populated. |
| 2026-04-12 | **Context reorganisation (completed).** CONTEXT.md split into CONTEXT.md + DECISIONS.md + REFERENCES.md + TODOS.md. PLANNER.md added. CLAUDE.md tightened. Module CLAUDE.md files created: `src/portfolio/`, `src/mf/`, `src/client/`, `src/notifications/`. `.claude/skills/commit/SKILL.md` (commit format, disable-model-invocation). `.claude/agents/code-reviewer.md` (opus) + `test-runner.md` (haiku). `CODE_REVIEW.md` → `docs/archive/CODE_REVIEW_2026-04-04.md`. `scripts/daily_snapshot_old.py` → `docs/archive/daily_snapshot_old_2026-04-12.py`. `PROJECT_INSTRUCTIONS_DRAFT.md` added for Claude Desktop project settings. |
| 2026-04-13 | **Dhan auth layer.** `src/auth/dhan_login.py` + `dhan_verify.py`. Manual 24h token flow via web.dhan.co. Raw `requests` client (no dhanhq SDK). Pure functions: `build_login_url()`, `validate_token()`, `save_token()`, `load_dhan_credentials()`, `fetch_profile()`, `fetch_holdings()`, `parse_holdings()`. 31 offline tests (13 login + 18 verify). Read-only scope — free Trading APIs only. Data APIs (₹499/month — option chain, historical, expired options) deferred for backtesting sprint. 431 total tests, all green (excluding pre-existing upstox_live failures). |
| 2026-04-14 | **Dhan LTP fix — switch to Upstox batch fetch.** Dhan `POST /v2/marketfeed/ltp` returns 401 on free tier (requires ₹499/month Data API). Added `enrich_with_upstox_prices()` + `upstox_keys_for_holdings()` + `fetch_dhan_holdings()` to `reader.py`. Restructured `_async_main`: Dhan holdings pre-fetched before Upstox LTP batch → keys added to `all_keys` → enriched after single batch call. `fetch_dhan_portfolio()` accepts optional `upstox_prices` param. 9 new tests. 558 total. |
| 2026-04-14 | **Dhan portfolio integration.** `src/dhan/` module: `models.py` (DhanHolding, DhanPortfolioSummary frozen dataclasses), `reader.py` (fetch_holdings_raw, fetch_ltp_raw, classify_holding, build_dhan_holdings, build_security_id_map, enrich_with_ltp, build_dhan_summary, fetch_dhan_portfolio), `store.py` (DhanStore — dhan_holdings_snapshots table, upsert, get_prev_snapshot). `src/portfolio/models.py` extended with 9 Dhan fields on PortfolioSummary (all default-zero — existing tests unaffected). `daily_snapshot.py`: `_async_main` wires Dhan (non-fatal, excludes strategy ISINs), `_historical_main` reads stored Dhan snapshots, `_build_portfolio_summary` includes Dhan in totals, `_format_combined_summary` restructured to Equity/Bonds/Derivatives/Total sections. `test_daily_snapshot_historical.py` updated for new sectioned format. 81 new Dhan tests (57 module + 24 snapshot integration). 549 total, all green (pre-existing upstox_live/nuvama failures unchanged). |
| 2026-04-15 | **Fuzzy instrument search.** `src/instruments/lookup.py`: `_score_query()` + `_best_score()` private helpers implement `exact(1.0) > prefix(0.92) > fuzzy` ranking via rapidfuzz (difflib fallback, no hard dep). `InstrumentLookup.search()` now scores + sorts all candidates; `min_score` param added. Signature of all other methods unchanged. 27 new tests in `tests/unit/instruments/test_lookup.py`. 585 total. |
| 2026-04-15 | **quant-4pc-local analysed.** Prior Dhan-focused research repo reviewed. Reusable components identified: `BacktestEngine` + `Strategy` protocol (port into `src/backtest/`), `IronCondorStrategy` + `IronCondorConfig` (port into `src/strategy/`), `_normalize_df()` data normalisation improvements for `src/dhan/reader.py`, retry/backoff pattern for future rate-limiter. Full porting notes in `PLANNER.md` → "quant-4pc-local Reference" section. Folder gitignored (`quant-4pc-local/`). |
| 2026-04-15 | **Atomic leg roll CLI (TODO 2).** `PortfolioStore.record_roll()` — single `_connect` block, two INSERTs, one transaction. `scripts/roll_leg.py`: `--old-*/--new-*` flag pairs, `_build_trades()` pure function, `--dry-run`. README.md updated with full CLI signature + dry-run example. 14 new tests (4 `test_trade_store.py` + 10 `test_roll_leg.py`). 599 total. |
| 2026-04-15 | **Nuvama bond schema probe.** `scripts/probe_nuvama_schema.py` added. Full `rmsHdg` field set confirmed: `isin`, `ltp`, `totalQty`, `totalVal`, `chgP`, `exc`, `hairCut` — no `avgPrice`. 6 holdings: 4 EFSL NCDs, 1 GOI G-Sec, 1 SGB. Cost basis sourced from Nuvama UI screenshot and will be seeded. LIQUIDBEES excluded by ISIN. Plan finalized — 4-phase implementation begins. |
| 2026-04-15 | **fix(scripts): os._exit() for daily_snapshot.py.** APIConnect `__init__` spawns a non-daemon Feed thread. `sys.exit()` waits for non-daemon threads so the process hung after completing. Replaced with `os._exit(main())` — identical fix to `nuvama_verify.py` and `nuvama_login.py`. Committed separately by Animesh (7a49720). |
| 2026-04-15 | **Nuvama bond portfolio integration (TODO 0) — all 4 phases complete.** `src/nuvama/` module: `models.py` (NuvamaBondHolding + NuvamaBondSummary frozen dataclasses), `reader.py` (parse_bond_holdings, build_nuvama_summary, fetch_nuvama_portfolio), `store.py` (NuvamaStore — nuvama_positions + nuvama_holdings_snapshots tables). `scripts/seed_nuvama_positions.py` (6 instruments, idempotent, dry-run by default). `PortfolioSummary` extended with 6 nuvama_* fields (all default-zero). `daily_snapshot.py`: Nuvama fetch block in `_async_main` (non-fatal), historical reconstruction in `_historical_main`, Nuvama Bonds line in `_format_combined_summary`, nuvama fields in `_build_portfolio_summary`. 97 new tests (54 pydantic-dependent — all pass in Mac venv). |
