# NiftyShield — TODOs

> Open work only. Completed items and full session history:
> [docs/archive/TODOS_ARCHIVE_2026-04-24.md](docs/archive/TODOS_ARCHIVE_2026-04-24.md)

---

## Priority Key

| Label | Meaning |
|---|---|
| `P1-NEXT` | Do this sprint — unblocked, highest impact |
| `P2-EVAL` | Decision or evaluation required before any code |
| `P3-DEFER` | Explicitly deferred — reason and ETA documented |
| `P4-PKG` | Packaging / infra hygiene — no production logic changes |
| `P5-DEBT` | Technical debt — fix alongside adjacent refactoring only, never standalone |

---

## P1-NEXT — Greeks Capture

Story file: `docs/plan/0_2_greeks_capture.md`

Fix the option chain call, define the `OptionChain` Pydantic model, implement `_extract_greeks_from_chain()`, and wire the null Greeks columns in `daily_snapshots`.

Steps:
- Fix API call: instrument key must be `NSE_INDEX|Nifty 50`
- Define `OptionChain` Pydantic model — drive from `tests/fixtures/responses/nifty_chain_2026-04-07.json`
- Implement `_extract_greeks_from_chain()` in `src/portfolio/tracker.py` (currently returns `{}`)
- Wire Greeks columns into `daily_snapshots` (columns already exist, currently null)
- Tests: fixture-driven, fully offline

Blocked by: nothing.

---

## P2-EVAL — Nuvama Session P&L Alignment

Decision needed before any code changes.

Current `nuvama_intraday_tracker.py` shows "All-time Total P&L" — cumulative sum of all historical `realized_pnl_today` rows via `get_cumulative_realized_pnl()`. This diverges from the Nuvama mobile/web UI which shows "Session P&L" (Unrealized + Today's Realized only), causing a visible mismatch (e.g. system shows +17k, Nuvama shows -17k).

Options:
1. Keep cumulative — true inception P&L; diverges from Nuvama UI intentionally
2. Switch to session-only — matches Nuvama UI; cumulative history still in DB but not displayed

No implementation until Animesh chooses an option.

---

## P3-DEFER — P&L Visualization

Deferred until late May 2026 (need 4+ weeks of snapshot data).

Matplotlib chart or React dashboard from `daily_snapshots` time series (component breakdown over time). `PortfolioSummary` dataclass is already extracted and ready to query. Plan notes in `PLANNER.md`.

---

## P4-PKG — Packaging / Infra Hygiene

### PKG-1: Remove `uuid==1.30` from `requirements.txt` (AR-20) ✅ DONE (2026-04-24)

Confirmed: all `import uuid` / `from uuid import uuid4` usages in `src/` and `scripts/` hit the Python 3 stdlib — the PyPI shim was a transitive leak. Removed.

### PKG-2: Split `requirements-dev.txt` (AR-21) ✅ DONE (2026-04-24)

Created `requirements-dev.txt` (`-r requirements.txt` + `pytest`, `pytest-asyncio`, `RapidFuzz`). All three removed from `requirements.txt`.

### PKG-3: Document graph project ID in `CLAUDE.md` Quick Reference (AR-22) ✅ DONE (2026-04-24)

Added `| Graph project ID | \`Users-abhadra-myWork-myCode-python-NiftyShield\` |` as first row of Quick Reference table.

### PKG-4: Add bash output discipline and git-log-first rule to `CLAUDE.md` (AR-23) ✅ DONE (2026-04-24)

- Promoted git-log to step 0 in Rule 0 decision tree (removed buried separate block, integrated inline with token cost call-out).
- Added `Rule 1 — Bash Output Discipline` section with explicit contract table: aggregate queries, diagnostic queries, test runs, log reads. Token math included.

---

## P5-DEBT — Technical Debt

Fix alongside adjacent refactoring. Never worth a standalone commit.

### DEBT-1: `@staticmethod` overuse (TD-1)

Per §2.17: replace with module-level `_private_function()`. Mechanical — no logic changes.

| File | Method(s) |
|---|---|
| `src/mf/store.py` | `_row_to_transaction()`, `_row_to_nav_snapshot()` |
| `src/portfolio/store.py` | `_row_to_leg()`, `_row_to_snapshot()` |
| `src/portfolio/tracker.py` | `_extract_greeks_from_chain()` |
| `src/dhan/store.py` | `_row_to_holding()` |
| `src/instruments/lookup.py` | `_score_query()` |
| `src/client/upstox_market.py` | row-mapping helper |

### DEBT-2: Line length violations (TD-2) ✅ DONE (2026-04-24)

11 lines >100 chars wrapped across 5 files: `src/portfolio/store.py` (docstring, 2× ternary),
`src/nuvama/store.py` (2× SQL strings, 2× SQL column list, docstring, method signature),
`src/dhan/reader.py` (logger.debug), `src/models/portfolio.py` (Field definition). 868 tests pass.

### DEBT-4: `SELECT *` column over-fetch in store layer (TD-5)

Multiple store `get_*` methods use `SELECT *` + `dict(r)` / `_row_to_*()`, pulling entire rows when callers consume only 3-4 fields. Code quality issue — return type is opaque, callers can't tell what fields exist without tracing to the schema.

Files and methods to target:

| File | Method | Action |
|---|---|---|
| `src/nuvama/store.py` | `get_options_snapshot_for_date` | `SELECT *` → named columns; return typed `dataclass` not `list[dict]` |
| `src/portfolio/store.py` | `get_prev_snapshots` | `SELECT *` → named columns matching `DailySnapshot` fields only |
| `src/mf/store.py` | `get_nav_snapshots`, `get_prev_nav_snapshots` | `SELECT *` → named columns matching `NavSnapshot` fields only |

Fix alongside adjacent refactoring (same file edit). Never a standalone commit.

### DEBT-5: Pre-aggregate bash tool output before it enters Claude context (TD-6) ✅ DONE (2026-04-24)

Completed as part of PKG-4 (AR-23). `Rule 1 — Bash Output Discipline` added to `CLAUDE.md` with the explicit four-pattern contract table (aggregate → `SUM`/`MAX`/`COUNT`, diagnostic → named columns + `LIMIT 10`, test runs → `--tb=no -q`, log reads → `tail`/`grep`). Token math and `get_cumulative_realized_pnl` reference callout included.

### DEBT-3: Missing license boilerplate (TD-4)

License decision needed before this can be automated. Every file should carry a header once the license is chosen.

---

## Session Log

| Date | What Changed |
|---|---|
| 2026-04-24 | **DEBT-5 (TD-6) closed.** `Rule 1 — Bash Output Discipline` (added as PKG-4/AR-23) satisfies the full DEBT-5 DoD. TODOS.md updated to reflect completion — no code changes. |
| 2026-04-24 | **PKG-3 + PKG-4 (AR-22, AR-23).** Graph project ID added to CLAUDE.md Quick Reference. git-log promoted to step 0 in Rule 0 decision tree. `Rule 1 — Bash Output Discipline` section added with explicit aggregate/diagnostic/test/log contract table. |
| 2026-04-24 | **Claude token optimization audit.** Added PKG-3 (graph project ID in CLAUDE.md), PKG-4 (bash output discipline + git-log-first rule in CLAUDE.md). Reframed DEBT-4 (SELECT * is code quality, not token issue). Reframed DEBT-5 (pre-aggregate bash output before Claude context, not store methods). No code changes — planning only. |
| 2026-04-24 | **DEBT-2 line length (TD-2).** Wrapped 11 lines >100 chars across `src/portfolio/store.py`, `src/nuvama/store.py`, `src/dhan/reader.py`, `src/models/portfolio.py`. 868 tests pass. |
| 2026-04-24 | **P4-PKG packaging hygiene.** Removed `uuid==1.30` (stdlib shim, AR-20). Created `requirements-dev.txt` with `pytest`, `pytest-asyncio`, `RapidFuzz` (AR-21). |
| 2026-04-22 | **Morning NAV backfill.** `scripts/morning_nav.py`: fetches AMFI NAVs for `prev_trading_day(today)`. Fixes stale T-2 NAV written by 15:45 cron. `--date` override for manual recovery. 6 tests. Cron: `15 9 * * 1-5`. |
| 2026-04-22 | **P2 architecture refactor (AR-4, AR-5, AR-6, AR-7).** `PortfolioSummary` refactored from 26-field flat to 16-field composed model with typed Optional source refs. `record_all_snapshots` + `record_all_options_snapshots` atomic via `executemany`. Historical bond reconstruction uses real `qty`+`ltp` (no `qty=1` stub). All 14 `# type: ignore[union-attr]` suppressions removed. 846 passing. Commit: `4de0ec4`. |
| 2026-04-23 | **P3 architecture refactor (AR-8, AR-9, AR-10, AR-11, AR-12).** `get_cumulative_realized_pnl` uses SQL `GROUP BY` (bounded result set). `get_all_positions_for_strategy` uses single aggregate query (N+1 eliminated). `NuvamaClient` protocol + `MockNuvamaClient` created. Deferred I/O imports in `nuvama_intraday_tracker.py`. `record_all_strategies` returns `dict[str, StrategyPnL]` — double LTP fetch eliminated. 854 passing. |

Full log (2026-04-01 → 2026-04-21): [docs/archive/TODOS_ARCHIVE_2026-04-24.md](docs/archive/TODOS_ARCHIVE_2026-04-24.md)
