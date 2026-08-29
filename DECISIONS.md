# NiftyShield — Architecture Decisions

> Read this when: adding a new module, changing inter-module dependencies, or making a
> structural choice that affects more than one file. Not needed for routine feature work.
>
> **Scope (RDO-9, 2026-08-28):** this file holds *still-enforced rules* only — a
> constraint that code or a process obeys today. Records of changes that already
> landed ("fixed X, why") live in
> [`docs/archive/DECISIONS_worklog_2026.md`](docs/archive/DECISIONS_worklog_2026.md).

---

## Developer Tooling

**pydantic-settings singleton for all env vars (2026-05-30, CH-7a):** `Settings(BaseSettings)` in `src/config.py` is the sole place where environment variables are read.
Import the `settings` singleton everywhere else — never call `os.getenv()` directly. Rationale:
single validation point at startup catches missing credentials immediately rather than failing silently mid-run; pydantic-settings handles `.env` loading, type coercion,
and pattern validation in one place. All fields are optional (None by default) so the codebase starts in test mode without credentials;
callers that require a specific token guard against None themselves.

**structlog over stdlib logging (2026-05-30, CH-6):** `src/utils/logging.py` exposes a single `setup_logging()` entry point using structlog. JSON renderer in prod (`UPSTOX_ENV=prod`),
coloured `ConsoleRenderer` in dev. `setup_logging()` is called once at the top of each script — no per-module `logging.getLogger()` boilerplate.
`structlog.processors.format_exc_info` sits in `shared_processors`, unconditionally, before the JSON/console split — so `exc_info=True` renders a real traceback in **both** modes
(was JSON-only until 2026-08-10; the plain/console branch every cron log uses was silently dropping tracebacks). Rationale: structured JSON log lines are machine-parseable
(grep + jq + CloudWatch Insights); the structlog `contextvars` processor allows request-scoped fields (e.g., `order_id`)
to be injected once and appear on all subsequent log lines without threading `logger` objects through every call.

**hypothesis property-based tests for financial math (2026-05-31, CH-9):** `@given` tests cover `compute_ivr`, `aggregate_delta`, and `PaperTracker.compute_pnl`.
These functions are the highest-risk for silent edge-case failures (boundary clamping, sign conventions, Decimal invariants). Hypothesis generates adversarial inputs
(random VIX series, empty position lists, large-magnitude deltas) that hand-written parametrised tests do not cover. Tests live in `tests/unit/backtest/test_ivr_hypothesis.py`,
`tests/unit/risk/test_delta_hypothesis.py`, `tests/unit/paper/test_pnl_hypothesis.py`. Key invariants enforced: `compute_ivr` always returns `[0.0, 1.0]` or None;
CE always adds positive delta, PE negative; `total_pnl == unrealized + realized` always holds; monetary results are always `Decimal`, never `float`.

**No CD pipeline (2026-05-30, CI-5):** GitHub Actions CI handles lint, test, coverage, and security on every push/PR. Continuous deployment is deliberately omitted.
NiftyShield is a live trading system — automated deploys without a manual review gate risk pushing broken logic to production during market hours. Deploy is a conscious,
human-executed step: `git pull` on the host + cron restart. This decision is revisited only after a paper-trading phase validates strategy stability.

**`pytest-xdist` parallel by default (2026-05-30, CI-2):** `addopts = "-n auto"` in `pyproject.toml` runs all tests in parallel. Serial fallback: `make test-serial`.
Tests that write to `data/` use `tmp_path` and are isolation-safe. If a test fails only with `-n auto`, it is order/state-dependent — fix isolation before marking slow.

**`pytest-randomly` seed logged in CI (2026-05-30, CI-3):** `make ci` passes `--randomly-seed=last` so the seed used in any failing CI run is visible in the Actions log and reproducible locally.

**Coverage gate at 80% (2026-05-30, CI-4):** `fail_under = 80` in `[tool.coverage.report]`.
Threshold chosen as the floor that forces meaningful test coverage without blocking incremental feature work.
`irongut/CodeCoverageSummary` posts the coverage table to the GitHub Actions summary on every CI run.

**mypy phased strict rollout (2026-05-29, DX-3):** `src/client.*` and `src/paper.*` run under strict mypy (`disallow_untyped_defs`, `disallow_any_generics`, `strict_equality`).
All other modules use permissive defaults (`warn_return_any`, `warn_unused_ignores`, `no_implicit_optional` only). Rationale:
`src/client/` owns the `BrokerClient` protocol boundary and all order/auth logic; `src/paper/` owns `Decimal` monetary fields and `PaperTrade` invariants —
both are highest-risk for silent type drift. A wall of errors on day one would kill adoption; phased rollout lets the team fix errors module-by-module.
Baseline error counts in `docs/plan/dev-foundation/dx-foundation/mypy_baseline.md`. Expanding strict coverage to other modules is a post-baseline task.

**ruff over flake8/black (2026-05-29, DX-2):** Single tool replaces flake8, isort, and black. Line length 100 (wider than black's 88 — matches existing codebase style). `E501` ignored
(ruff format handles line length). `B008` ignored (Pydantic validators call functions in default args by design).

**pre-commit scoped to client/paper only for mypy (2026-05-29, DX-4):** mypy hook in `.pre-commit-config.yaml` uses `files: ^src/(client|paper)/` to match DX-3 strictness boundaries.
Expanding the hook to other modules is gated on fixing their baseline errors first.

**`paper_track_snapshot.py` status (2026-05-31, SR5):** `paper_track_snapshot.py` is confirmed superseded by `paper_3track_snapshot.py` as the canonical EOD cron snapshot script.
It has been moved to `scripts/dev/paper_track_snapshot.py` to be preserved purely for backward-compatible operator use (ad-hoc runs) and is excluded from `crontab`.

**paper-backbone architecture shipped (2026-06-02, PB):** `PaperStrategy` protocol (`src/strategy/protocol.py`) is the sole interface between strategies and the monitor daemon —
`check_signals` returns `list[SignalEvent]`, `apply_action` executes an `ApprovedAction`. `StrategyMonitor` (`src/strategy/monitor.py`) owns the tick loop, strategy registry,
and heartbeat writes to `daemon_heartbeat` table. `PaperExecutor` (`src/strategy/executor.py`) dispatches approved actions and simulates fills via `PaperFillSimulator`
(VIX-regime slippage: high VIX → wider spread). `RapidCouncil` (`src/council/rapid.py`) provides parallel Stage-1 fan-out (5 heterogeneous LLM personas)
with chairman synthesis and per-call timeout — **not wired into the paper trading approval path** (see CR decision below). `TelegramGateway` (`src/notifications/telegram_gateway.py`)
handles human-approval flow: sends approval request with inline keyboard, polls inbound callbacks, enforces chat-ID allowlist, and scans for stale pending approvals.
DB migrations add `pending_approvals`, `council_outputs`, `daemon_heartbeat` tables to shared SQLite. Integrated strategies: `CSPNiftyV1` (PT-S0), `IronCondorV1` (PT-S1),
`NiftyTrackComparisonV1` (PT-S3, WARN-only). PT-S2 Signal Pipeline blocked on signals story + OpenRouter API key.

**`paper_csp_roll.py` retired (2026-06-22, PA2):** Roll signal + strike selection moved into `CSPNiftyV1._select_roll_target` (PA1.1). `PaperExecutor` handles `legs_to_open`;
the standalone script is no longer the execution path for CSP rolls.

**`paper_3track_overlay_roll.py` retired (2026-06-22, PA2):** Overlay roll signals moved into `NiftyTrackComparisonV1._select_overlay_roll_target` (PA1.3).
`PaperExecutor` handles `legs_to_open`; the standalone script is no longer the execution path for 3-track overlay rolls.

**RapidCouncil removed from paper trading approval path (2026-06-04, CR):** `RapidCouncil` is not called in any Phase 0 paper trading flow. Three reasons:
(1) Paper trading exits are single-option decisions — `ExitSignalEngine` determines the action before a council could be consulted;
`apply_action()` constraints make deliberation redundant. (2) Roll decisions must be deterministic and backtestable — LLM outputs are non-deterministic across runs and model versions,
and cannot be replayed against historical data without hindsight leakage. (3) A signature mismatch between `StrategyMonitor._dispatch_event`
(calls `send_approval_request(event, context_str)`) and `TelegramGateway.send_approval_request` (expects `CouncilOutput, SignalEvent, str`)
meant the council was bypassed with a latent `TypeError` anyway — fixed in CR0. Deterministic roll rules added to `ExitSignalEngine`:
`evaluate_roll_csp()` uses IVR-tiered strike selection (IVR < 0.25 → blocked; 0.25–0.35 → ATM; 0.35–0.50 → ATM−50; > 0.50 → ATM−100) with delta floor 0.30;
`evaluate_roll_overlay()` uses fixed ATM±50 offset with base-DTE guard (base DTE ≤ 10 → emit `ROLL_BASE_FIRST` WARN). Both are pure functions, replayable against historical data.
`RapidCouncil` is retained as a module for Phase 1 live trading use — criterion for wiring:
action space ≥ 2 defensible options AND real capital at stake AND strategy spec does not resolve the choice. Full story: `docs/plan/council-refactor/`.

**RapidCouncil status audit and re-flag criterion (2026-07-04):** Confirmed still true as of this date — `src/council/rapid.py` has zero live callers anywhere in `src/` or `scripts/`;
its only exercise is `tests/unit/council/test_rapid_council.py` (mocked HTTP, no real invocation). `docs/archive/plan/PAPER_TRADING_PLAN.md` (status: design doc, superseded)
originally scoped it to fire on every `ACTION`-severity `SignalEvent` from any strategy —
that design was replaced by the mechanical-threshold approach codified in the council-refactor entries above
(CSP/CC/PP/Collar/IC-V2 all use fixed numeric rules derived from a one-time design council, not a live per-event council). Audited every story in `docs/plan/`
(options_income, risk-gamma-phase-a, paper-exit-codification, signals-eval-core, backtest-eval-core,
broker-abstraction, historical-data-abstraction, variance-gate, telegram-leg-labels,
paper-store-position-granularity, mvp, dev-foundation)
— every entry/exit condition across all of them is a fixed threshold table, none require live discretionary judgment,
so none are candidates for wiring `RapidCouncil` in as currently scoped. The one place a live multi-model panel is justified —
the morning directional call with no open position and no time-critical execution risk — already exists as a separate, independently-built implementation: `SignalAggregator`
(`docs/plan/signals/`, S1.3) fanning out to GPT-4o/Grok/Gemini providers. `RapidCouncil` and `SignalAggregator` are not reconciled anywhere in this file or in either plan doc;
this is unintentional duplication, not a deliberate two-system design — no decision record justifies keeping two independent consensus-aggregation implementations.
**Flag `RapidCouncil` for revival, do not silently reinvent it,** when a future story proposes any of: (a)
a live per-event decision with real capital at stake where the action space has ≥2 defensible options and the strategy spec does not resolve the choice
(the original CR criterion, unchanged); (b) a circuit-breaker/halt or other event type the mechanical rule tables were never written to cover — i.e.,
an `ACTION` event with no matching threshold rule in the relevant strategy's spec doc; (c) any new multi-LLM-consensus need —
check `src/council/rapid.py` and `docs/plan/signals/` first and consolidate into one of them rather than authoring a third parallel implementation. Before wiring:
fix the `StrategyMonitor._dispatch_event` / `TelegramGateway.send_approval_request` signature mismatch noted in the CR entry above
(still present, never revisited since it was only relevant while bypassed).

**CC overlay scripts implemented as standalone CLI tools (council-refactor, CR):** Entry (`scripts/strategies/cc_calibration/paper_cc_entry.py`) and manual exit
(`scripts/strategies/cc_calibration/paper_cc_roll.py`) are kept separate from `CCOverlayV1`. Rationale: strike selection is delta-based (15Δ) vs OTM-based (3–5%) in the 3-track;
quantity constraint is NiftyBees-unit-driven (`compute_max_lots`); strategy name namespace is separate (`paper_covered_call_v1`).
CLI tools serve as manual override / dry-run path alongside automated EOD evaluation via `CCOverlayV1`. `compute_max_lots` lives in `src/paper/constants.py` —
recompute at each annual NiftyBees leg reset.

**CSP always-open design (council-refactor, CR):** CSP never truly closes — every exit cycles into a new position. State machine: OPEN → DEFENDED (delta breach + roll)
→ RE_ENTRY_PENDING (any close) → OPEN. Thresholds: profit target 70% (LTP ≤ 30% of entry), hard stop 2×, delta breach |δ| ≥ 0.40, time stop `days_held ≥ 21 AND dte ≤ 21`
(the DTE guard was added by EC-4 so a short put rolled onto a longer-dated contract is not force-closed on days-held alone), DTE roll ≤ 7. No second roll from DEFENDED state.

**CC automation design (council-refactor, CR):** CC mirrors CSP signal structure. All ACTION signals map to CLOSE_CC
(no roll variants — covered nature removes assignment risk complexity). Re-entry gated by IVR ≥ 0.25 after PROFIT_TARGET and DTE_REVIEW exits only; not after LOSS_STOP or DELTA_STOP
(market moved against position — reassess before re-entering). Strike selection: 4% OTM via `find_overlay_strikes.py`.
(EC-5 collapsed CC's `TIME_STOP`/`DTE_REVIEW` into one ACTION-severity `DTE_REVIEW` at DTE ≤ 5
and updated both `apply_action` re-entry allow-lists to include `DTE_REVIEW`; `TIME_STOP` is no longer emitted for CC.)

**ReEntryMixin pattern (council-refactor, CR):** Re-entry eligibility check extracted to `ReEntryMixin` (`src/strategy/reentry_mixin.py`). `CSPNiftyV1`, `CCOverlayV1`,
and `CollarOverlayV1` all inherit it. Class attributes (`reentry_leg_role`, `reentry_script_hint`) customise behaviour per strategy.
Future strategies add re-entry gates by inheriting the mixin and overriding two attributes. Gate changes (e.g., add ATR or regime filter) made once in the mixin.

**`_CC_MIN_ENTRY_CREDIT` and `_PROFIT_TARGET_RETENTION` are distinct thresholds (council-refactor, CC-1):** Two separate constants in `exit_signals.py`. `BELOW_FLOOR` (INFO)
fires at entry < ₹12 — position too cheap to manage. `PROFIT_TARGET` has an independent floor at `_CC_MIN_ENTRY_CREDIT = Decimal("15")`: if entry credit < ₹15 at entry,
PROFIT_TARGET never fires — the call decays to worthless without active management.
The ₹12 BELOW_FLOOR and ₹15 PROFIT_TARGET floor solve different problems and must not be collapsed into one threshold.

**`_PROFIT_TARGET_RETENTION` shared constant (council-refactor, CR):** `Decimal("0.30")` extracted as module constant in `exit_signals.py`.
Shared by `evaluate_profit_target_csp` and `evaluate_cc`. Rationale: 70% decay threshold is strategy-agnostic for short premium positions —
separating CSP and CC constants would allow accidental drift.

**PP always-reprotect design (council-refactor, PP):** PP (Protective Put) on NiftyBees tracks a simple two-state machine: OPEN ↔ RE_ENTRY_PENDING. No DEFENDED state —
there is no defensive roll for a long put. After CRASH_MONETIZE, strategy enters RE_ENTRY_PENDING and waits for IVR ≤ 0.60 before re-buying protection.
This prevents buying at peak post-crash IV. Delta range for new PP: fixed 0.20–0.30 (coverage depth, not IV-driven). Spread guard removed from CRASH_MONETIZE:
paper mode slippage handled by `PaperFillSimulator`; in a real crash, spread guard would block auto-execution at exactly the wrong moment. DTE roll
(ROLL_ELIGIBLE at DTE ≤ 5) auto-executes: straightforward forward roll, same delta.

**Proxy delta consecutive-day tracking (council-refactor, NT-1):** `ExitSignalEngine.evaluate_proxy_delta()` requires caller to maintain consecutive-day breach count across sessions.
Stored in `PaperStore` (`paper_strategies` table, `proxy_delta_breach_count INTEGER DEFAULT 0`) rather than in-memory, so the count survives daemon restarts.
Caller resets to 0 when delta recovers above 0.40. `PROXY_DELTA_WARN` (δ<0.65) is suppressed when `PROXY_DELTA_CRITICAL` fires — CRITICAL subsumes WARN to avoid redundant signal noise.

**`PROXY_PREMIUM_DECAY` fires only at DTE ≥ 5 (council-refactor, NT-1):** If mark < ₹0.50 and DTE < 5, the position is near expiry and rides to settlement.
Closing at DTE < 5 for a near-worthless deep ITM call creates unnecessary slippage and STT cost; let it settle. Guard: `DTE >= 5` only.

**IC V2 profit-lock design: spread-width contraction only (2026-06-27, IC-V2-PL):** Zone 2 profit-lock (≥50% credit captured)
rolls both long wings inward to ~19Δ via atomic 4-leg wing-only restructure. Floor guarantee enforced before execution: `max(W_put, W_call) + D_cum + D_lock + K ≤ 0.75 × C₀`.
If the inequality cannot be satisfied at liquid strikes, CLOSE_FULL executes automatically — no human decision point. Zone 1 (≥25%): log-only, no structural change. Zone 3 (≥75%):
CLOSE_FULL (existing profit target fires first; Zone 3's required width ~50 pts is too tight for reliable Nifty execution). D3 defensive rolls do not consume profit-lock budget
(profit-lock moves longs, not shorts); after profit-lock, D3 "original width" resets to new active width. All profit-lock actions are auto_execute=True;
Telegram notification fires after execution (confirmation only). Delta-neutral hedging and short-leg inward rolls explicitly rejected as guarantee mechanisms (no hard floor).
Council ruling: `docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md` Stage 3.

**Futures + standalone CC permanently blocked in `NiftyTrackComparisonV1` (council-refactor, NT-2):** Guard fires when the Futures namespace has a short call role AND no paired long put exists.
Collar exemption is structural — not a flag — because a collar is defined as short call + long put together. A degenerate collar
(short call without a put, e.g., put closed while call remains) also triggers the block. Guard is called at the top of `check_signals`, before any other signal evaluation,
so the ERROR is always visible even when other signals also fire.

**`__init__.py` required in every package directory:** `scripts/` was missing `__init__.py`, which caused `codebase-memory-mcp` to silently skip the entire directory —
all 12 functions in `daily_snapshot.py` were invisible to the graph despite the repo being indexed.
Adding `scripts/__init__.py` brought the node count from 1048 → 1684 and edge count from 3544 → 6077 in one re-index. Rule: every new `src/<module>/`, `scripts/`,
and test subdirectory must include `__init__.py`. Re-index after adding any new package.

**codebase-memory-mcp as primary code understanding tool:** Use `search_graph`, `get_code_snippet`, and `trace_path` before opening source files with `Read`.
The graph resolves function signatures, call chains, and callers/callees without consuming tokens on file content. `Read` is the fallback for markdown, config,
and fixtures not in the graph. This is especially important for large files like `daily_snapshot.py` (~600 lines) where only one or two functions are relevant to any given task.

**git log as primary intent discovery tool:** Every commit in this repo follows the structured format in `.claude/skills/commit/SKILL.md` with an explicit `Why:` line.
Before inferring intent from code, run `git log --oneline -15 <file>` to see the change sequence, then `git show <sha>` for the diff and rationale.
This is faster and more accurate than reverse-engineering intent from code alone.

---

## Market Calendar

**NSE Nifty monthly expiry moved from Thursday to Tuesday (2026-06-01, MKT-1):**
SEBI circular effective April 2026 moved all Nifty index option expiries from the last Thursday to the last Tuesday of each month.
This affects: `src/models/portfolio.py` (Leg validator — `_NSE_TUESDAY_EXPIRY_CUTOFF = 2026-04-01`; Thursday check skipped for post-cutoff expiries), `src/backtest/bhavcopy_ingest.py`
(`get_last_expiry_day()` replaces `get_last_thursday()`; old function kept as deprecated shim), `scripts/pipeline/gamma_daily_watch.py` (`resolve_expiries()` targets Tuesday).
Historical bhavcopy records pre-April 2026 still use Thursday expiries — the cutoff is enforced in `get_last_expiry_day()` by comparing against the cutoff date.

**Holiday data source: static YAML, updated annually.** `src/market_calendar/data/nse_{year}.yaml` —
a list of `{date, name}` entries seeded from NSE's published equity holiday calendar. Stored under `src/` (not `data/`) because `data/` is gitignored to protect the live SQLite DB;
the YAML is config and must be version-controlled. No live API query at cron time. Rationale: a network failure at 3:45 PM should not determine whether the snapshot runs.
NSE's holiday list for the year is deterministic; there is no operational benefit from runtime resolution.

**`src/market_calendar/holidays.py` is the sole consumer of the YAML.** Three public functions: `load_holidays(year)` → `frozenset[date]`, `is_trading_day(d)` → `bool`
(weekday AND not in holiday set), `prev_trading_day(d)` → `date` (walk backwards). Cache in module-level `_CACHE` dict to avoid re-parsing on repeat calls within the same process.

**Fail-open on missing YAML.** If `nse_{year}.yaml` does not exist (e.g. January 1st before the annual refresh), `is_trading_day()` logs a WARNING and returns `True`.
Safer than blocking a valid trading day due to a missing file. The WARNING is surfaced in cron logs so the gap is visible.

**Data gap on holidays: no rows written, no backfill.** When a script skips due to a holiday, no `daily_snapshots`, `mf_nav_snapshots`, or `nuvama_options_snapshots` rows are written.
Gaps are intentional and honest. `get_prev_snapshots()` uses `MAX(snapshot_date) < d` (calendar-agnostic) so day-delta P&L on the next trading day is correct with zero additional code.

**Annual maintenance ritual:** Each January, fetch the NSE equity holiday list for the new year, create `src/market_calendar/data/nse_{year}.yaml`, and commit. The refresh is manual;
automating it adds a web-scraping dependency with no operational upside for a once-a-year task.

---

## Data Layer

**UTC-only timestamps in intraday_market_snapshots:** `record_market_snapshot` raises ValueError on naive datetime; stores as UTC ISO string.
Prevents SQLite string-sort breakage when naive local and UTC-aware strings coexist. Ref: commit a259115.

**Intraday Market Context Separation (2026-05-08):** Market context separated into `intraday_market_snapshots` via `IntradayMarketStore`; Nifty+VIX fetched once in orchestrator.
Previously, Nifty spot was tracked redundantly in broker-specific options tables (e.g., `nuvama_intraday_snapshots`).
Separating it enables both Dhan and Nuvama trackers to share the same market context without redundant API calls.

**Shared SQLite connection factory (`src/db.py`):** Single `connect()` context manager used by both `PortfolioStore` and `MFStore`. WAL mode, `sqlite3.Row` factory, FK enforcement,
auto commit/rollback. Any PRAGMA change applies everywhere from one place.

**MF holdings use a transaction ledger model:** `mf_transactions` table stores every SIP/redemption as a plain INSERT. Current holdings derived at query time via `SUM(units)`.
Never mutate existing rows — new SIP = new INSERT. Enables full history and attribution.

**NAV data source: AMFI official flat file** (`https://www.amfiindia.com/spages/NAVAll.txt`). Semicolon-delimited, 6 fields: `code; ISIN growth; ISIN reinvest; name; NAV; date`.
No auth, no rate limits. Preferred over `mfapi.in` (third-party dependency) and Upstox (no MF API exists).

**AMFI flat file parsing gate:** `parts[0].strip().isdigit()` — single check that skips category headers, the column header line, blank lines, and malformed rows without any regex.

**NAV snapshots stored per-scheme** in `mf_nav_snapshots`; portfolio-level aggregation happens at query time. Enables per-fund P&L attribution.

**MF data shares the existing SQLite DB** (`data/portfolio/portfolio.sqlite`) — one file, one WAL, one backup target.

**`amfi_code` typed as `str` (pattern `^\d+$`), not `int`** — used as identifier and join key, never as arithmetic. Matches AMFI flat file representation.

**Monetary values stored as TEXT in SQLite** — preserves exact `Decimal` precision through round-trips. Read back via `Decimal(row["col"])`. Applies to: `units`, `amount`, `nav`,
`entry_price`, `ltp`, `close`, `underlying_price`, `price` in all tables.

**`get_holdings()` and `get_position()` aggregate in Python, not SQL** — same rationale: keeps exact `Decimal` arithmetic, avoids CAST rounding.

**`mf_transactions` unique constraint:** `(amfi_code, transaction_date, transaction_type)` — idempotent seed via `ON CONFLICT DO NOTHING`.
Assumes one transaction per type per NAV date per scheme.

**`mf_nav_snapshots` conflict policy:** `ON CONFLICT(amfi_code, snapshot_date) DO UPDATE` — last write wins, consistent with `daily_snapshots`.

**`trades` UNIQUE constraint:** `(strategy_name, leg_role, trade_date, action)` — allows one BUY and one SELL for the same leg on the same date (same-day roll), prevents double-seeding.

**Paper trades stored in same SQLite DB as live trades but in separate tables with `paper_` prefix on strategy names (2026-04-25):**
`paper_trades` and `paper_nav_snapshots` live in `portfolio.sqlite` alongside the live tables.
Rationale: reuse of the existing `src/db.py` connection manager, `PaperStore` → `PaperTracker` → `daily_snapshot.py` wiring,
and Telegram notification infrastructure with zero parallel infrastructure. The `paper_` prefix on `strategy_name` is the sole runtime guard against cross-contamination at query time.
No foreign-key cross-references to live tables.

**`PaperPosition.avg_sell_price` tracks SELL opening trades separately from `avg_cost` (BUY avg):** Options writing opens a position via SELL, not BUY.
Tracking both averages independently in `PaperPosition` keeps unrealized P&L semantically correct for both long (BUY-opened) and short (SELL-opened)
positions without requiring a direction flag on the position itself.

**MF store tests use `tmp_path`** (file-based SQLite), not `:memory:` — `_connect()` opens and closes a fresh connection on every call, so `:memory:` would lose state between calls.

**Online DB backup writes outside the repo mount (2026-07-07):** the backup cron writes to `BACKUP_DIR` (defaults to an external absolute path, e.g. `/var/backups/niftyshield`),
never a relative path inside the checkout. The primary risk the backup exists for is FUSE mount corruption of `data/portfolio/portfolio.sqlite`;
a backup on the same mount defeats the purpose.

---

## PortfolioStore

**2026-05-16 — Async factory sentinel pattern**: `PortfolioStore.create()` uses `object.__new__` to bypass `__init__`, avoiding `_skip_init` bool flag. Sync constructor (`__init__`)
unchanged for sync script callers. Sentinel approach chosen over `_skip_init` to prevent accidental uninitialized-store construction.

---

## Portfolio & Trade Model

**`Leg` vs `Trade` distinction:** `Leg` (in `ilts.py`, `finrakshak.py`) is a conceptual strategy role — instrument + direction + entry price as a definition. `Trade`
(in the `trades` table) is a physical execution — what actually transacted, when, at what price. They coexist permanently: `Leg` defines shape; `Trade` drives cost-basis and qty.

**`apply_trade_positions()` bridges Leg and Trade at runtime:** patches Leg qty/entry_price from weighted avg trade data, appends trade-only legs (LIQUIDBEES) as EQUITY/CNC,
drops zero-net-qty legs. Returns new Strategy without mutating original.

**Trade overlay internalized in `PortfolioTracker`:** `_get_overlaid_strategy()` / `_get_all_overlaid_strategies()` private helpers apply the overlay before returning. `compute_pnl`,
`record_daily_snapshot`, `record_all_strategies` all use overlaid data — no caller manually applies it for these paths.

**Trade-only legs auto-persisted via `store.ensure_leg()`:** When `record_daily_snapshot` encounters a leg with `id is None` (LIQUIDBEES appended by overlay),
it calls `ensure_leg(strategy_name, leg)` to upsert and obtain a DB id. Idempotent.

**`trades.strategy_name` must match `strategies.name` exactly:** Canonical names are `finideas_ilts` and `finrakshak`. Mismatch silently disables the overlay —
`get_all_positions_for_strategy()` returns empty, no error raised.

**SELL price excluded from weighted average buy price:** Premium received, not capital deployed. `get_position()` only averages BUY prices.

**LIQUIDBEES tracked in `trades` not in strategy `Leg` definitions:** Not a Finideas strategy leg.
`apply_trade_positions()` appends it as EQUITY/CNC at runtime so its mark-to-market is included in the ETF component.

**`seed_trades.py` separates `build_trades()` (pure) from `seed_trades()` (I/O):** mirrors `seed_mf_holdings.py` pattern. Tests call `build_trades()` directly with no DB.
Dates marked `2026-01-15` are placeholders pending contract note verification.

**Leg validation design debt and inline imports:** The domain model `Leg`
contains inline imports of `is_trading_day` to avoid circular dependencies
with `market_calendar`. Long-term, validation should be factored out of Pydantic
`model_validator` or accept pre-computed parameters.

**Leg expiry whitelist is hardcoded in domain model:** The irregular expiry
whitelist is currently hardcoded in `portfolio.py` to prevent cyclic import
issues. It should ideally reside in a configuration file or a calendar module
with a clean interface.

**`is_nifty` detection uses denylist check on name and key:** Strike grid
validation identifies Nifty 50 options by checking both `display_name` and
`instrument_key`, excluding "BANK", "FIN", "MIDCP". This denylist approach will
misidentify new Nifty index variants. This is a latent trap if other index
options are traded in the future.

**`OverlayCloser.close_collar_all` returns `bool` (2026-07-22):** `True` when the position ends up flat (already-flat short-circuit, or the atomic write succeeds),
`False` when the write fails and both legs remain open. `auto_close_overlay`'s `overlay_collar_call` branch checks it immediately and raises `RuntimeError` on `False`,
routing into the existing "AUTO-CLOSE FAILED" handler rather than sending a plausible-looking "COLLAR CLOSED" for a close that never happened.

---

## P&L & Reporting

**`PortfolioSummary` frozen dataclass** in `src/portfolio/models.py`. Carries all combined totals (`mf_value`, `etf_value`, `options_pnl`, `total_value`, `total_pnl`, `total_pnl_pct`)
plus four day-delta fields (all `Decimal | None`). `_build_portfolio_summary()` in `daily_snapshot.py` owns all arithmetic.

**Combined portfolio P&L formula:** `total_value = MF current value + ETF mark-to-market + options net P&L`. ETF legs identified by `leg.asset_type == AssetType.EQUITY`
(not string prefix).

**Two distinct P&L metrics:** (1) Inception P&L — current value minus total invested; (2) Day-change P&L —
today vs previous snapshot via `get_prev_snapshots()` / `get_prev_nav_snapshots()` (MAX date < today, calendar-agnostic). Δday column omitted silently on first run.

**P&L quantization boundary:** `current_value` and `pnl_pct` quantized to 2 dp (ROUND_HALF_UP); `pnl` kept as exact difference so `sum(scheme.pnl) == total_pnl` without rounding drift.

**`PortfolioTracker.compute_pnl()` returns `Decimal`** via `StrategyPnL.total_pnl`. No bridging cast needed when combining with other Decimal values.

**MF snapshot is non-fatal in cron:** the MF block in `daily_snapshot.py` is wrapped in `try/except Exception`. AMFI unreachable at 3:45 PM does not abort the portfolio snapshot.

**AMFI NAV timing:** AMFI publishes after market close (7–9 PM IST). The 3:45 PM cron fetches T-1 NAV for MFs — this is expected and correct.
Combined P&L shows mixed-timestamp data by design.

**`FinRakshak protection stats`:** `finrakshak_day_delta` isolated from combined `options_day_delta` in `_build_portfolio_summary`. `_format_protection_stats()` appends hedge verdict
(✅/⚠️) to log output and Telegram header.

**Nuvama options: Intelligent EOD Snapshot pattern for cumulative realized P&L.** Nuvama's `NetPosition()` response returns `rlzPL` as a _daily_ realized figure —
it resets each session. To get lifetime cumulative realized P&L, the daily snapshot stores each day's `rlzPL` per `trade_symbol` in `nuvama_options_snapshots`,
and `get_cumulative_realized_pnl()` uses a single SQL `GROUP BY trade_symbol` query
(AR-8, 2026-04-23) with the result mapped through `Decimal(row["cumulative"])` at the boundary to preserve Decimal precision. Flat positions
(net_qty == 0) are intentionally included because their `rlzPL` still counts toward cumulative tracking.
Alternative of fetching a running total from Nuvama directly is not available via the SDK.

**Overlay P&L invariants (SNAP-5 / BUG-032 / BUG-028):** never average cost bases or LTPs across strikes before computing P&L — sum independently-computed per-instrument P&L instead.
`paper_leg_snapshots.ltp` is `NULL` (not the newest leg's LTP) when a role holds `n > 1` open positions.
`total_pnl == unrealized_pnl + realized_pnl` must hold on every `paper_nav_snapshots` row (enforced at write time by `record_nav_snapshot` / `record_leg_snapshot`).
One canonical overlay row per `(STRATEGY_OVERLAY, overlay_type, snapshot_date)` — overlay trades and canonical overlay snapshots share one strategy namespace;
shared overlay P&L is never persisted once per base track; read-time track comparisons never write back into the snapshot tables.
Missing overlay source data renders as `None` / "No data", never `Decimal("0")` — a zero is only emitted when observations genuinely exist and compute to zero.

**Nuvama intraday snapshots use DECIMAL column type (not TEXT).** The five-minute intraday table (`nuvama_intraday_snapshots`) stores `ltp`, `unrealized_pnl`,
`realized_pnl_today` as `DECIMAL` and `nifty_spot` as `DECIMAL`. This intentionally deviates from the TEXT-for-Decimal rule —
the read path in `get_intraday_extremes()` wraps every value in `Decimal(str(row[...]))` at the boundary, which absorbs any SQLite float representation.
The deviation is acceptable here because intraday data is purely for graphing (not P&L accounting) and the boundary cast neutralises precision risk.

---

## Nuvama SDK Exit Handling

**`os._exit()` required in any script that initialises `APIConnect`.** The Nuvama SDK (`APIConnect.__init__`) launches a non-daemon background thread (Feed thread).
`sys.exit()` blocks on non-daemon threads and hangs the process. `os._exit(exit_code)` terminates immediately. Applies to: `daily_snapshot.py`, `nuvama_login.py`, `nuvama_verify.py`,
`nuvama_intraday_tracker.py`. Any new script that calls `load_api_connect()` or instantiates `APIConnect` directly must also terminate via `os._exit()`.

---

## daily_snapshot.py Design

**Deferred I/O imports:** Module-level imports are stdlib + `src.portfolio.models` only. All I/O-triggering imports (`dotenv`, `UpstoxMarketClient`, `PortfolioStore`, etc.)
deferred inside `_async_main()`. Pure helpers importable in tests with zero side effects.

**Single `asyncio.run()` entry point:** entire live-mode logic runs inside `_async_main()`. Historical mode (`--date`) runs in `_historical_main()` — no async needed (DB only).

**`_format_combined_summary()` produces text; `_print_combined_summary()` wraps with print.** Both terminal and Telegram receive identical strings without double-computing or stdout capture.

**`PortfolioTracker.record_daily_snapshot` and `record_all_strategies` return computed P&L alongside counts (AR-11, 2026-04-23).** Both methods previously returned `int` / `dict[str, int]`
(snapshot counts only). They now return `tuple[int, StrategyPnL | None]` and `tuple[dict[str, int], dict[str, StrategyPnL | None]]` respectively.
The change eliminates the redundant `compute_pnl()` call in `daily_snapshot._async_main` — P&L is computed from the prices dict already fetched during snapshot recording.
Any caller that unpacks the old single-value return (`count = await tracker.record_daily_snapshot(...)`) must be updated to `count, pnl = ...`.
`compute_pnl()` is retained for ad-hoc single-strategy queries.

**`paper_snapshot.py` runs one no-flag cron (2026-07-21):** `paper_snapshot.py --no-dry-run` (no `--strategy` flag)
auto-discovers every `paper_*` strategy with trades via `store.get_strategy_names()` — no cron edit at strategy-creation time. Its per-strategy loop body runs inside try/except:
a failure logs `paper_snapshot.strategy_failed` / `batch_partial_failure` and continues to the next strategy;
the script exits 1 if any strategy failed while still snapshotting every unaffected one. `record_nav_snapshot` is a single upsert in one `connect()` context,
so a mid-loop exception rolls back before re-raising — no half-written NAV row.

**Single-row-per-service cron heartbeat state (2026-05-18):** The `cron_heartbeats` table uses `service TEXT PRIMARY KEY` + `INSERT OR REPLACE` to store exactly the last known execution state
(status, last run timestamp, and optional status message) for each cron service. This is a deliberate low-overhead choice for liveness checks;
if historical execution logging or failure rate trends are needed in the future, it will require a schema migration to a history-log model.

---

## Client Layer & BrokerClient Protocol

**BrokerClient protocol design (`src/client/protocol.py`):** Three narrow sub-protocols (ISP) — `MarketDataProvider` (tracker/signal), `OrderExecutor` (execution), `PortfolioReader`
(monitoring). `BrokerClient` kept flat (not inheriting from sub-protocols) so its full method list is readable. Python structural typing —
any class satisfying all 10 `BrokerClient` methods automatically satisfies all three sub-protocols. Stub type aliases (`X = Any`)
with `# TODO` comments stand in for Pydantic models not yet in `src/models/`. `from __future__ import annotations` means zero import-time dependency on `src/models/`.

**Composition root pattern (`src/client/factory.py`):** `create_client(env)` is the only `src/` function that imports `UpstoxLiveClient` or `MockBrokerClient` directly.
All other modules receive a `BrokerClient` via constructor injection — they import only `src.client.protocol.BrokerClient`. `VALID_ENVS: Final = ("prod", "sandbox", "test")`.

**`UpstoxLiveClient` delegation pattern:** holds `self._market: UpstoxMarketClient` (Analytics Token). `get_ltp` and `get_option_chain` are pure async pass-throughs to `_market`.
No inheritance — protocol conformance is structural.

**Two-token constraint:** Analytics Token (long-lived, `UPSTOX_ANALYTICS_TOKEN`) powers market data. Daily OAuth token (`UPSTOX_ACCESS_TOKEN`) required for positions, holdings,
margins. `UpstoxLiveClient` currently holds only the Analytics Token; portfolio-read methods raise `NotImplementedError`.

**`NotImplementedError` policy for blocked methods:** Three categories: (1) Order execution — `_raise_order_blocked()` centralises the message; (2) Portfolio read —
Daily OAuth token required; (3) Data constraints — historical candles (not wired), expired contracts (paid subscription). Callers see a clear error rather than silent wrong behaviour.

**`MockBrokerClient` design:** Stateful offline broker client. Margin tracked as `Decimal`; order notional deducts `price * quantity * 0.1` as NRML proxy.
`simulate_error(method, exc)` is one-shot: fires once on next call, then removed. `reset()` clears orders/positions/error queue, restores default margin;
preserves `_price_map` and `fixtures_dir`. Missing fixtures log WARNING, return `None`/`[]`/`{}` — never raises.

**`upstox_market.py` is a pre-protocol legacy module:** Built before the BrokerClient abstraction. Sync `requests` client. Violates DI rule. Wrapped inside `UpstoxLiveClient` —
no consumer outside `src/client/` imports it. Do not add new dependents on it directly.

**Error hierarchy (`src/client/exceptions.py`):** Full tree rooted at `BrokerError`: `AuthenticationError`, `RateLimitError`, `DataFetchError` → `LTPFetchError`,
`OrderRejectedError` → `InsufficientMarginError`, `InstrumentNotFoundError`.
`get_ohlc_sync` and `get_option_chain_sync` raise `DataFetchError` rather than returning empty dicts silently.

---

## Notifications

**Telegram notifier is optional and non-fatal:** `build_notifier()` returns `None` when env vars absent. `send()` catches all `Exception` broadly, returns `False` with WARNING log.
The cron never aborts due to Telegram failure. `build_notifier()` constructs a fresh uncached `Settings(_env_file=None)` on every call —
a deliberate exception to the "env vars only via the `settings` singleton" rule,
because this one call site's return value gates a real external side effect and must not depend on cache-invalidation working across the process lifetime (BUG-011, 2026-08-06).

**Message format (MarkdownV2, migrated off HTML 2026-08-25, MD-1..MD-7.3):**
`TelegramNotifier.send()` / `TelegramGateway.send_notification` / `send_approval_request` all send `parse_mode: MarkdownV2`.
`send()` does **not** auto-escape — every caller escapes dynamic values via `mdcode()` / `escape_markdown()` (`src/notifications/markdown.py`).
The static-scan guard test `tests/unit/notifications/test_escaping_guard.py` fails any new
`.send()` / `.send_plain_message()` / `.send_notification()` call site that interpolates an unescaped dynamic value
(`_BASELINE_UNESCAPED` allowlist for the one won't-fix, `scripts/dev/send_test_telegram.py`). Known gaps tracked in `docs/bugs/bugs.md`:
`escape_markdown()` does not escape literal backslashes; BUG-038 (`OverlayCloser`'s unawaited `notifier.send()` coroutines).

**WARN-severity Telegram dedup (2026-08-06):** WARN-severity `SignalEvent`s alert once on the OFF→ON transition (not a time-based cooldown), stay silent while breached,
and clear on recovery so the next re-breach alerts immediately. State persists in the `warn_signal_state` table (`PaperStore`, keyed `(strategy_name, event_type, leg_role, expiry)`)
so it survives daemon restarts. No periodic re-fire, no escalation tier.

---

## Models & Types

**`frozen=True` for computed types:** `SchemePnL`, `PortfolioPnL`, `StrategyPnL`, `LegPnL`, `PortfolioSummary`, `MFNavSnapshot`, `MFTransaction`, `Trade` — all immutable.

**Enum compatibility:** `Direction`, `ProductType`, `AssetType` use `(str, Enum)` — not `StrEnum` (3.11+ only; project targets 3.10+).

**`nav_fetcher` injected as `NavFetcherFn = Callable[[set[str]], dict[str, Decimal]]`** — tests pass a lambda, production gets the real AMFI fetcher.
Missing NAV codes skipped with WARNING, not raised.

**`MFHolding` defined in `src/mf/models.py`**, not `tracker.py` — avoids the circular import that would result from `store.py` importing a type defined in `tracker.py`.

**`src/models/` migration complete (2026-04-16):** `portfolio/models.py` and `mf/models.py` moved to `src/models/portfolio.py` and `src/models/mf.py`. All consumers in `src/`,
`scripts/`, and `tests/` updated. Old files deleted. `src/models/__init__.py` re-exports everything for convenience. Canonical import paths:
`from src.models.portfolio import Leg` and `from src.models.mf import MFTransaction`. `src/strategy/`, `src/execution/`,
`src/backtest/` can now import shared types without coupling through `src/portfolio/`.

---

## Dhan Portfolio Integration

**Scope: read-only equity and bond holdings.** `GET /v2/holdings` for demat positions; `POST /v2/marketfeed/ltp` for current prices. No F&O, no intraday.

**ISIN → Upstox key derivation:** For NSE equities, Upstox instrument key = `NSE_EQ|{ISIN}`. Derived directly from the Dhan `isin` field — no lookup file, no config.

**Classification is config-driven, not automatic.** Dhan API returns all demat holdings as exchange-traded securities with no bond/equity distinction.
`_BOND_SYMBOLS: frozenset[str]` in `reader.py` maps known liquid/bond ETF symbols (LIQUIDCASE, LIQUIDBEES, LIQUIDIETF, CASHIETF, LIQUIDADD, LIQUIDSHRI) to `"BOND"`.
Everything else is `"EQUITY"`. Adding a new bond instrument requires one line in this frozenset.

**Double-count prevention:** Dhan `GET /v2/holdings` returns all demat holdings, including instruments already tracked by strategies (EBBETF0431, LIQUIDBEES).
`build_dhan_holdings()` accepts an `exclude_isins: set[str]` parameter — `_async_main` extracts ISINs from `NSE_EQ|{ISIN}` strategy leg keys before calling.
Filtered holdings are never persisted or included in totals.

**Non-fatal design:** Dhan fetch block in `_async_main` is wrapped in `try/except`. `ValueError` (missing credentials) silently skips with an info print; network errors log WARNING.
If Dhan is unavailable, `dhan_summary=None` is passed down — all Dhan fields in `PortfolioSummary` default to `Decimal("0")` and `dhan_available=False`.
Formatter shows `[unavailable]` in Bonds section and a NOTE in Total section.

**24h token expiry by design.** Dhan access tokens expire daily. Users refresh via `python -m src.auth.dhan_login`. No auto-refresh implemented.

**`PortfolioSummary` Dhan fields default to zero.** All nine new Dhan fields
(`dhan_equity_value`, `dhan_equity_basis`, `dhan_equity_pnl`, `dhan_equity_pnl_pct`, `dhan_equity_day_delta`, and bond equivalents + `dhan_available: bool`) have safe defaults —
all existing tests and callers are unaffected.

**SQLite table:** `dhan_holdings_snapshots` shares `data/portfolio/portfolio.sqlite`. `UNIQUE(isin, snapshot_date)` with upsert semantics — re-runs on same day are idempotent,
last write wins.

**Day-change delta computation:** `DhanStore.get_prev_snapshot()` uses `MAX(snapshot_date) < today` — calendar-agnostic,
handles weekends/holidays without explicit market-calendar dependency.

**LTP source: Upstox batch fetch, not Dhan market API.** Dhan's `POST /v2/marketfeed/ltp` requires the paid Data API (₹499/month) and returns 401 on free tier. Instead,
`_async_main` pre-fetches Dhan holdings before the Upstox LTP batch, derives Upstox keys via `NSE_EQ|{ISIN}` using `upstox_keys_for_holdings()`, adds them to `all_keys`,
then calls `enrich_with_upstox_prices()` after the single Upstox batch LTP call. Single batch, zero extra API cost. `enrich_with_ltp()` (Dhan API path)
is retained in `reader.py` for completeness but not used in production.

---

## Nuvama Integration

**Scope: read-only.** Bonds/holdings for margin tracking + EOD positions. Order execution NOT wired for Nuvama.

**Session persistence:** `APIConnect` persists session token in `NUVAMA_SETTINGS_FILE` (path in `.env`). No daily re-auth after first login via `python -m src.auth.nuvama_login`.
Unlike Upstox daily OAuth, session survives until explicitly invalidated.

**`parse_holdings()` is a pure function** — maps `eq.data.rmsHdg` response to a flat list. Independently testable without a live session.

**`src/nuvama/` module architecture (added 2026-04-15):**

**Cost basis stored in `nuvama_positions` table, not derived from API.** Nuvama's `Holdings()` response has no `avgPrice` field — current value only (`totalVal = ltp × qty`).
Cost basis seeded once via `scripts/seed_nuvama_positions.py` into `nuvama_positions(isin TEXT PRIMARY KEY, avg_price TEXT, qty INT, label TEXT)` in `portfolio.sqlite`.
`reader.py` joins positions at parse time. New purchases require re-running the seed or a future `record_nuvama_trade.py` CLI.

**Day-change delta derived from `chgP` field.** The API returns `chgP` as a string percentage (e.g. `'-1.28'`). `day_delta = current_value × Decimal(chgP) / 100`.
This avoids a prior-snapshot dependency and is accurate enough for bonds (low intraday volatility). Snapshots are still stored in `nuvama_holdings_snapshots` for historical tracking.

**All Nuvama holdings classified as BOND.** Nuvama account holds only debt instruments. `asTyp` field is always `'EQUITY'` in the API
(Nuvama makes no bond/equity distinction in their response schema). Classification is not API-driven.
`_EXCLUDE_ISINS: frozenset[str]` in `reader.py` excludes instruments already tracked elsewhere (initially: LIQUIDBEES `INF732E01037`).

**LTP sourced directly from Holdings() response — no Upstox enrichment.** Unlike Dhan (which requires a separate LTP call), Nuvama's Holdings() includes current LTP inline.
No secondary API call needed.

**`nuvama_holdings_snapshots` table.** `UNIQUE(isin, snapshot_date)` with upsert — same pattern as `dhan_holdings_snapshots`.
Stores `isin, snapshot_date, qty, ltp, current_value` for historical trend tracking. Shares `portfolio.sqlite`.

**Non-fatal design.** Nuvama fetch block in `_async_main` is wrapped in `try/except`. `ValueError` (missing credentials/settings) skips with info print; network/API errors log WARNING.
`nuvama_summary=None` passed down — `PortfolioSummary.nuvama_*` fields default to zero, `nuvama_available=False`. Formatter shows `[unavailable]` in Bonds section.

---

## Dhan Integration

**Two API tiers:** Trading APIs (free — portfolio, positions, funds, orders) vs Data APIs (₹499/month or ₹4,788/year — option chain, historical data, expired options, market depth).
Current integration uses free tier only.

**Scope: read-only.** Holdings, positions, fund limits for after-market P&L review. No order execution wired for Dhan.

**Raw `requests` client (no `dhanhq` SDK):** All Dhan APIs are plain REST with `access-token` header auth.
The `dhanhq` package is a thin wrapper that adds no value for read-only calls. Raw requests give us full control over request/response shapes —
essential for building Pydantic models for the backtesting engine later. Migration cost to SDK is near-zero if ever needed.

**Manual 24-hour token from `web.dhan.co`:** Token generation requires Application Name (e.g. `NiftyShield`), optional Postback URL, Token validity (default 24h). No OAuth flow —
simpler than both Upstox and Nuvama.

**Data Source for Backtesting Engine — SUPERSEDED (2026-04-27):** See "Backtest Data Source Decision (2026-04-27)" in `docs/archive/DECISIONS_pre-2026-07.md`.
DhanHQ was the original choice; it has been rejected after evaluation. NSE F&O Bhavcopy (free, from exchange) is now the programmatic data source for options OHLCV backtesting.

**Local Storage Architecture for Historical Chains — REVISED (2026-04-27):** TimescaleDB was originally selected to handle the volume of DhanHQ's 1-minute data (~500M rows).
DhanHQ has been rejected; the NSE F&O Bhavcopy pipeline produces EOD data (~4M rows for 8 years across all NIFTY strikes) — well within Parquet + SQLite capacity.
TimescaleDB is **deferred indefinitely** — revisit only if a future paid minute-level data source is adopted. All new backtest storage uses Parquet (`data/offline/`)
+ existing `portfolio.sqlite`.

**Parquet partition scheme designed for DuckDB glob-query compatibility (2026-04-27):** All Parquet outputs under `data/offline/` use the partition path `{year}/{month}/` (EOD data)
or `{year}/{month}/{day}/` (intraday data). This is intentional:
DuckDB can glob-query the full dataset without any schema migration via `read_parquet('data/offline/<series>/**/*.parquet')`.
Do not install DuckDB yet — Parquet + pyarrow/pandas is sufficient for Phase 1 volumes.
If complex multi-file range queries become slow in Phase 2 (e.g., querying 16M-row intraday chain sets),
introduce DuckDB as a zero-migration query layer on top of the existing files.
The partition scheme is the only forward-compatibility requirement.

**Chain snapshot storage: Parquet at `data/historical/option_chain/` (2026-04-27, confirmed 2026-05-27; path corrected 2026-08-06):** Originally specified as a TimescaleDB hypertable;
revised to Parquet on 2026-04-27 (TimescaleDB deferred). Tasks 1.10 + 1.10a implemented via the `chain-data` story (archived at `docs/archive/plan/chain-data/`, completed 2026-05-29) —
`1_10_dhan_chain_client.md` is ABANDONED. **Path correction (2026-08-06):** this entry originally read `data/offline/chain_snapshots{,_5min}/`;
live capture as of this date is confirmed writing to
`data/historical/option_chain/eod/{year}/{month}/upstox_{date}_{label}.parquet` and
`data/historical/option_chain/intraday/{year}/{month}/{day}/upstox_{HHMM}_{label}.parquet` instead
— `{label}` (weekly/monthly/quarterly/yearly) disambiguates multiple expiries per run (BUG-006). The `data/offline/` paths still exist on disk from earlier test runs
(stale, not receiving new writes) — do not confuse with the live tree. Schema:
`snapshot_ts, underlying, expiry_date, strike, option_type, spot, ltp, bid, ask, oi, volume, iv, delta, gamma, theta, vega`. Query layer: DuckDB glob-scan via `ChainReader`
(`src/backtest/chain_reader.py`). **Coverage confirmed (2026-08-06):** full chain, all strikes both sides, not liquidity-filtered —
cross-checked row-for-row against a live diagnostic pull for monthly and quarterly buckets, exact match. 42 trading days of intraday data present as of this date (2026-06-01 onward),
37 days of EOD. **Known gap:** intraday capture depends on the operator's machine being online — multi-hour gaps occur when offline/off-network
(confirmed 2026-08-06, not a pipeline defect). **Weekly bucket added 2026-08-06** to both `upstox_chain_snapshot.py` and `upstox_chain_intraday.py`'s `_PREFERENCE` list
(previously monthly/quarterly/yearly only).

**Intraday live option chain snapshots at 5-min cadence (2026-04-27, migrated to chain-data story 2026-05-27):** 5-min intraday cron (`*/5 9-15 * * 1-5`)
accumulates real bid/ask and Greeks throughout the trading day. Volume: ~67K rows/day, ~16M rows/year, ~2–3 GB/year compressed. Rationale:
(1) real intraday bid/ask spread distribution is the empirical input for the slippage model in task 1.4;
(2) intraday delta drift from real Upstox Greeks against BS-reconstructed Greeks quantifies the structural bias in task 1.6a; (3) cannot be back-filled. Operational cost:
3 API calls per 5-min interval = 225 calls/day; well within Upstox Analytics Token budget. Implementation story: `docs/archive/plan/chain-data/` task CD2.1 (completed 2026-05-29).

---

## OptionChain Model

**Source-agnostic `OptionChain` Pydantic model (decided 2026-04-24, implemented 2026-04-25):** `OptionLeg`, `OptionChainStrike`, `OptionChain` defined in `src/models/options.py`.
Field names are source-agnostic (`delta`, not `greeks_delta`). Translation from Upstox/Dhan response shapes happens in each client's parser, not in the model.
`OptionLeg` carries no `instrument_key` — lookup is by strike price + asset_type (both on the `Leg` model), so the OptionChain model stays vendor-neutral.

**Upstox-first for live chain (confirmed 2026-04-27):** Upstox Analytics Token is already active — zero marginal cost. Live chain snapshots (EOD + intraday)
use Upstox via `parse_upstox_option_chain`. Dhan Data API is subscribed for historical expired options data (backtesting).
If a future strategy requires Dhan-sourced live Greeks for vendor consistency, the `MarketDataProvider` protocol enables a swap without touching strategy code —
but no such requirement exists yet.

**Strike lookup: `Decimal(str(leg.strike))` dict key.** `OptionChain.strikes` is keyed by `Decimal`. Nifty strikes are always integers.
`Decimal("22250.0") == Decimal("22250")` is True in Python (value equality governs dict lookup), so float-origin strikes round-trip correctly.

**`_parse_option_leg` coerces null/non-numeric Greeks to `Decimal("0")` with WARNING.** Best-effort contract — a bad Greek field never aborts the snapshot.

**`get_option_chain_sync` pre-existing return-type bug:** Returns `resp.json().get("data", {})` — the data field is a list, not a dict; default `{}` is wrong;
return annotation `dict[str, Any]` is wrong. Deferred fix — absorb in `parse_upstox_option_chain` by accepting `list[dict]`. Do not fix the bug in this task.

---

## Strategy & Research Decisions

> Full rationale for each decision lives in the referenced council file or strategy doc.
> This section is an index — one line per decision. Read the source file for reasoning.

- **2026-04-25** — CSP underlying → Nifty 50 index options (NiftyBees rejected: OI <1,000, spread >5% of mid) _(source: `docs/strategies/csp_nifty_v1.md`)_
- **2026-04-25** — NiftyBees collateral modelled as `long_niftybees` leg in paper P&L; annual reset in January _(source: `docs/strategies/csp_nifty_v1.md`)_
- **2026-04-26** — NiftyShield integrated: CSP Leg 1 + put spread 4 lots (8–20% OTM) + tail puts 2 lots (5-delta quarterly) _(source: `docs/strategies/niftyshield_integrated_v1.md`)_
- **2026-05-02** — Leg 2 strike selection: %OTM (long put at 8% below spot, short put at 20% below spot) over delta-based;
  delta-based rejected due to cost unpredictability at high VIX and dead-zone variability in low-vol regimes
- **2026-04-26** — Static beta 1.25 for MF hedge ratio; switch to rolling 60d beta after 12+ months NAV history _(source: `docs/strategies/niftyshield_integrated_v1.md`)_
- **2026-04-26** — Two-tier backtest: Tier 1 = Bhavcopy + Black '76 IV; Tier 2 = synthetic pricer for deep OTM protective legs _(source: `BACKTEST_PLAN_PHASE1.md §1.9a`)_
- **2026-04-27** — Data stack: TrueData + DhanHQ rejected; Stockmock (calibration) + NSE Bhavcopy (programmatic) adopted _(source: `BACKTEST_PLAN_PHASE1.md §1.1, §1.3`)_
- **2026-04-27** — TimescaleDB deferred indefinitely (Bhavcopy EOD ~4M rows fits Parquet + SQLite) _(source: `BACKTEST_PLAN_PHASE1.md §1.2`)_
- **2026-04-30** — IV reconstruction: Black '76 with Nifty Futures forward; stepped RBI repo rate; quadratic smile fit for delta _(source: `BACKTEST_PLAN_PHASE1.md §1.6a`)_
- **2026-04-30** — Slippage: absolute INR, VIX-regime-aware + OI liquidity multiplier; base at 60–70th percentile _(source: `BACKTEST_PLAN_PHASE1.md §1.4`)_
- **2026-05-01** — Donchian: signal-in-only (ATR trailing stop → flat, not always-in); credit spreads uniform; ATR-proportional spread width
- **2026-05-01** — ORB: ATR primary filter + VIX-IVP 90th-pct structural exclusion; event-day calendar exclusion mandatory; DTE ≤ 2 → skip to next weekly
- **2026-05-02** — CSP delta: 22-delta default (85% of 25d credit, ~half stop-out rate); 25-delta when IVR 25–40; parameterised in scripts
- **2026-05-02** — Gap Fade VIX-IVP filter: 75th percentile (vs ORB 90th); asymmetry is structural and binding
- **2026-05-02** — IC v1: mild put-side asymmetry (short put 16Δ / short call 14Δ normal; 18Δ/12Δ high-IVR); symmetric deltas rejected
- **2026-05-02** — 3-track comparison: Track C = Deep ITM Call (delta ≈ 0.90); Track B + Covered Call / CSP programmatically blocked
- **2026-05-02** — Near-expiry buy research: Gamma Gearing primary; Speed secondary; OI velocity confirmation only; weekly 0–1 DTE Nifty; paper trading Phase 0
  (not Phase 3) _(source: `docs/strategies/near_expiry_buy_v1.md`)_
- **2026-05-15** — Dhan Data API (₹499/month) subscribed for: (1) L2 order book depth for gamma_scan.py fill simulation;
  (2) historical expired options data supplementing NSE Bhavcopy for Phase 1 backtest pipeline _(source: `docs/strategies/near_expiry_buy_v1.md §3`)_
- **2026-05-02** — Live monitoring: CUSUM lower-sided (k=0.50, h_warn=3.0, h_reduce=4.0, h_halt=5.0) replaces weekly Z-score
- **2026-05-02** — Phase 0.8 gate: 4 criteria (A–D); Z-score is smoke test only; graduated deployment tiers 0 → 0.5 → 1 → 2 → 3 _(source: `docs/plan/variance_gate.md`)_
- **2026-05-03** — NSE Bhavcopy: old archive URL covers 2016–~Nov 2024 only; Dec 2024+ uses new UDiFF format at a different URL and CSV schema _(source: `TODOS.md → P1-NEXT UDiFF fix`)_
- **2026-05-23** — TradingView MCP (`tradesdontlie/tradingview-mcp`) validated as real-time regime signal channel; `docs/strategies/regime_probe.pine` is the canonical probe script;
  multi-timeframe regime divergence (1D vs 1W) is a mandatory check before strangle entry _(source: `docs/archive/tv_mcp_testing_framework.md`)_
- **2026-05-24** — Settle vs LTP: Bhavcopy `settle_price` is daily VWAP (3:00–3:30 PM), not EOD LTP. Actual IV divergence correction (using Upstox/Dhan EOD LTP validation target)
  is deferred until programmatic IV reconstruction is implemented. _(source: `docs/reviews/audit_2026-05-15.md` finding [23])_
- **2026-05-27** — chain-data story supersedes tasks 1.10 + 1.10a: both tasks implemented via `docs/archive/plan/chain-data/` story
  (completed 2026-05-29) with Parquet storage confirmed. `1_10_dhan_chain_client.md` archived as ABANDONED.
- **2026-05-28** — CSP/CC profit target: **70% captured** — mark ≤ 30% of entry credit (`_PROFIT_TARGET_RETENTION = Decimal("0.30")`, `exit_signals.py`).
  Applies to CSP and CC identically.
  _(Council text read "50%"; realigned to 30% retention 2026-06-07 / codified 2026-06-26.
  Source: `docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md`.)_
- **2026-05-28** — CSP delta stop: **\|delta\| ≥ 0.40 ACTION** (`exit_signals.py`); delta warn at 0.35 (INFO/WARN, no close).
  Premium backstop at 1.75× entry credit. _(Council text read 0.45; code is 0.40 — see "CSP always-open design".)_ _(source: `docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md`)_
- **2026-05-28** — CSP time stop: 21 calendar days from entry date → ACTION. DTE ≤ 5 → WARN
  (no auto-close). _(source: `docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md` — Chairman Synthesis)_
- **2026-05-28** — CC profit target: **70% captured** (mark ≤ 30% of entry credit) AND entry credit ≥ ₹15/unit. Entry credit < ₹12/unit → BELOW_FLOOR (INFO, hold to DTE, no % exit).
  ₹12–₹15 band: no profit target exit;
  premium backstop and delta stop still apply.
  _(Council text read "50% decay"; realigned to 30% retention 2026-06-07.
  Source: `docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md`.)_
- **2026-05-28** — CC loss/delta stops: call mark ≥ 2.5× entry credit → LOSS_STOP ACTION. Short call delta ≥ +0.55 → DELTA_STOP ACTION; ≥ +0.45 → DELTA_WARN (no close).
  **DTE ≤ 5 → DTE_REVIEW ACTION** — flat, no ITM/delta/residual compound condition
  (EC-5, 2026-08-01, replaced the old `DTE_FORCED` compound rule). _(source: `docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md`)_
- **2026-05-28** — PP (Protective Put): hold to expiry by default. CRASH_MONETIZE ACTION when put delta ≤ −0.80 OR (put value ≥ 5× entry debit AND bid/ask spread ≤ 10% of mid).
  DTE ≤ 5 → DTE_REVIEW INFO only.
  Replacement leg optional if DTE ≥ 14 and liquidity adequate. _(source: `docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md` — Chairman Synthesis)_
- **2026-06-15** — Collar Overlay exits: collar call evaluated via `evaluate_cc` (30% PROFIT_TARGET, 2.5x LOSS_STOP, 0.55 DELTA_STOP, 21d TIME_STOP).
  The long put is dragged along and closed atomically with the call via `store.record_trades`. Independent long put crash monetization (`COLLAR_PUT_CRASH`)
  is dropped. _(source: docs/plan/council-refactor/stories_collar.md)_
- **2026-06-15** — EOD Auto-Close execution: EOD snapshot ACTION signals automatically execute trades and update status to ACTED (or RE_ENTRY_PENDING for PP)
  using OverlayCloser. _(source: docs/plan/council-refactor/stories_auto.md)_
- **2026-05-28** — Collar sequencing: in a crash, buy back cheap short call first, then sell long put to monetise. Rationale: restores uncapped upside before monetising downside;
  avoids being short a call with no protection if put sale executes first. _(source: `docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md` — Chairman Synthesis)_
- **2026-05-28** — Dual-signal audit mandate (Q2 council): on every sell-leg exit event (CC + Collar short call), always record `delta_stop_would_fire`, `premium_stop_would_fire`,
  and `actual_rule_used` in `paper_exit_events`.
  Evaluate after 6–12 cycles which mechanism produces better exit timing. _(source: `docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md` — Chairman Synthesis)_
- **2026-05-28** — Automation tier: Tier 1 (EOD via `paper_3track_snapshot.py`) mandatory for Phase 0. Tier 2 (intraday `StrategyMonitor` 90s tick)
  wired but disabled via `MONITOR_OVERLAYS=0` env gate;
  opt-in after Tier 1 validation. _(source: `docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md` — Chairman Synthesis)_
- **2026-05-29** — scripts/ restructured from flat layout into functional axis: pipeline/ (cron, produces data), lookup/ (on-demand query), record/ (human write CLI),
  strategies/<name>/ (strategy-specific), plus portfolio/, intraday/, seed/, council/, dev/.
  Axis chosen because paper-backbone daemon and future strategies need to distinguish shared infra from strategy-owned scripts.
  New scripts must be classified by this axis before placement. _(source: scripts-restructure)_
- **2026-06-02** — StrategyMonitor fetch architecture: keep full chain fetch (Option A) through Phase 0. Watchlist/batch-LTP optimisation deferred to Phase 1
  (triggers: ≥5 strategies, ≥15 open legs, multiple expiries, rate utilisation >10%). _(source: `docs/council/2026-06-02_strategy-monitor-watchlist-design.md` — Chairman Synthesis)_
- **2026-06-02** — Roll target selection (Option Y): strategy selects exact target strike from in-memory chain inside `check_signals`;
  target packed into `SignalEvent.payload` before council prompt and Telegram approval. Executor performs final sanity check at execution time; rejects if target materially stale.
  Option Z (executor-lazy) deferred to Phase 1+. _(source: `docs/council/2026-06-02_strategy-monitor-watchlist-design.md` — Chairman Synthesis)_
- **2026-06-02** — Shared roll utility: `src/strategy/roll_utils.py` —
  `find_strike_by_delta(chain, option_type, delta_range, target_delta)` used by all strategy `_select_*_roll_target()` helpers.
  No duplication across strategy files. _(source: `docs/council/2026-06-02_strategy-monitor-watchlist-design.md` — Implementation Guidance)_
- **2026-06-02** — Multi-expiry fetching for overlay rolls: NiftyTrackComparisonV1 targets next expiry for overlay rolls.
  Strategy fetches next-expiry chain immediately during ACTION construction inside `check_signals`. Not a watchlist architecture —
  targeted second chain fetch only when a roll-qualifying signal fires. _(source: `docs/council/2026-06-02_strategy-monitor-watchlist-design.md` — Architectural Note)_
- **2026-06-02** — Phase 1 protocol upgrade path: when watchlist optimisation is introduced, use mandatory `PaperStrategyV2` protocol with `market_requirements() -> MarketDataRequest`
  — not backward-compatible optional `watchlist()`.
  Avoids conditional fetch logic in monitor. _(source: `docs/council/2026-06-02_strategy-monitor-watchlist-design.md` — Chairman Synthesis)_
- **2026-06-07** — Covered Call profit target aligned to 30% retention (70% captured) instead of 50% capture,
  to match CSP symmetrical exit engine architecture. _(source: council-refactor)_
- **2026-06-07** — DTE_FORCED ACTION exit removed, replaced with a flat DTE_REVIEW at DTE ≤ 5. **Superseded by EC-5 (2026-08-01): DTE_REVIEW is ACTION-severity, not WARN** —
  it auto-closes at DTE ≤ 5. _(source: council-refactor)_
- **2026-06-07** — entry_date is None fallback to days_held = 0 with a warning log to prevent silent gaps. _(source: council-refactor)_
- **2026-07-06** — Full-repo-review epic (FR-0..FR-9) closed — 7 CRITICAL + 8 ERROR findings, 9 fix stories spawned under `docs/plan/`; `CLAUDE.md` gained the 3 promoted review rules
  (severity-by-mission-impact, verify-own-citations, state-uncovered-perspective).
  Full write-up in the worklog archive. _(source: `docs/plan/full-repo-review/findings/FR-7_synthesis.md`)_
- **2026-08-05** — IC time-stop de-tiered: `time_stop_dte` / `dte_warn` no longer scale to entry-DTE. Monthly / leaps / yearly all `time_stop_dte=7`, `dte_warn=14`
  (`ic_expiry_config.py`); weekly unchanged at `2` / `4`. **Noted, deferred:** the `7` is a Phase 0 research default paired with DT-3 counterfactual logging —
  review after 6 monthly cycles. _(source: `docs/council/2026-08-05_ic-time-stop-dte-tiering.md`)_

### Dissenting / deferred notes (full-repo-review epic, 2026-07-06)

**Row 6 (Greeks/parity absence) severity divergence, preserved per FR-7 not collapsed:** FR-5 rates the absence of any Black-Scholes reference test or put-call-parity check CRITICAL
("is the correctness test missing for financial logic" axis); FR-2 rates the same absence WARNING ("absence of a test is not itself a wrong result" axis),
rating only its *consequences* (row 1's live P&L bugs) CRITICAL. FR-7's chairman kept CRITICAL because the epic's own evidence proves the consequence —
the absence demonstrably let two live CRITICAL accounting errors survive undetected until manual reconciliation.
Deferred to `docs/plan/greeks-parity-validation/` pending an `options-strategist`/`greeks-analyst` council consultation on tolerance bands and reference-model assumptions before implementation.

**Row 10 (suppression-comment hygiene) severity divergence:** FR-4 rated CRITICAL per the letter of REVIEW.md's suppression-comment rule;
FR-7's chairman downgraded to ERROR because most bare `E402`/`F401` suppressions are self-describing and the load-bearing fix is a REVIEW.md policy carve-out,
not 100+ mechanical comment additions. Deferred to `docs/plan/suppression-hygiene-triage/`.

**Personas not represented (FR-7 §"Personas Not Represented") — logged so they are not rediscovered in production:**
- **Regulatory/Compliance persona (margin, STT, tax):** correctly identified as covered by nobody, but load-bearing only once real orders are placed — hard-blocked today
  (`_raise_order_blocked()`, static IP). **Trigger: mandatory before the order-execution block is lifted.**
- **Cold-start / new-contributor onboarding persona:** real but low-yield for a single-operator repo with two established AI collaborators; deferred indefinitely,
  no trigger condition set.
- **Market-Data Adversarial Reviewer** (option-chain parser behavior under circuit-breaker halts, crossed bid/ask, expiry-day degenerate chains): genuinely new persona,
  no existing role approximates it, attached to the row-6 CRITICAL. If a second full-repo-review-style pass is ever funded, this is the first new persona to add —
  pairs naturally with the row-6 parity work (same fixtures, same session).
- **Options-strategist weighing absence-of-retry missed-gate risk** (row 18, WARNING):
  routed through the existing `options-strategist`/`greeks-analyst` agents when the static-IP constraint is revisited — no new persona needed, not scheduled now.

### Dissenting Notes (council 2026-06-02)

**Q2 minority — Option Z (executor-lazy target selection):** 2 of 5 panelists argued that `check_signals` should emit roll intent only (delta range + expiry constraints),
with the executor resolving the specific strike at approval time. Rationale: cleaner separation of concerns, avoids duplicating target logic in strategy and executor.
**Overruled by Chairman:** approval semantics require the user to approve a specific trade, not an abstract policy. Phase 0 auditability is the deciding constraint.
Option Z deferred to Phase 1+ consideration when approvals may become constraint-based for automated execution.

### Dissenting Notes (council 2026-05-28)

**Q2 minority position — premium-multiple-only stop for Phase 0:** One council voice argued that delta-based stops add model risk in Phase 0
(model error contaminates the exit signal before we have empirical delta accuracy). Recommended using only the 1.75× (CSP) / 2.5× (CC)
premium backstop for Phase 0 and deferring delta stops until Phase 1 delta reconstruction is validated. **Overruled by Chairman:** dual-signal fields
(`delta_stop_would_fire`, `premium_stop_would_fire`) in `paper_exit_events` are the resolution — both signals are evaluated and recorded,
but the committee retains both as active exit triggers. Comparison data collected over 6–12 cycles will determine whether delta adds signal or noise post-Phase 0.

---

## Archived — historical reference

**Completed-work log (RDO-9b, 2026-08-28)** →
[docs/archive/DECISIONS_worklog_2026.md](docs/archive/DECISIONS_worklog_2026.md).
Every "fixed X, why" narrative from 2026-07 / 2026-08 — the chronological stream that
was at the top of this file, the `## Process` 3-track implementation log, the dated
`## BUG-*` sections, the NSE Bhavcopy UDiFF migration (delivered — `_parse_udiff` /
`_parse_legacy` + dual-URL in `src/backtest/bhavcopy_ingest.py`), and the Telegram
Markdown migration sequencing narrative. Still-enforced rules from those entries were
lifted into the sections above before the move.

**Five pre-2026-07 sections** →
[docs/archive/DECISIONS_pre-2026-07.md](docs/archive/DECISIONS_pre-2026-07.md)
(moved 2026-08-27, round-2 token-optimization #3b). One line each:

- **TradingView MCP Regime Probe (2026-05-23)** — CDP bridge experiment to TradingView Desktop; regime-probe findings, superseded by `docs/strategies/regime_probe.pine`.
- **Backtest Data Source Decision (2026-04-27)** — DhanHQ rejected; NSE F&O Bhavcopy adopted as the programmatic OHLCV source.
- **TrueData Historical Dump (2026-05-09)** — 1-min intraday dump-product evaluation and purchase scope (2022–2024 first).
- **Live Strategy Monitoring (2026-05-02)** — CUSUM-replaces-weekly-Z-score design for N<24 live cycles; early drawdown guards.
- **src/ Model Placement Rule (2026-05-31)** — shared types → `src/models/`, domain-local → `src/<module>/models.py` (src-restructure SS4).

---

## Risk, Delta & Entry Gates

**`src/risk/delta_tracker.py` stays pure / sync / zero-I/O (council 2026-07-02).** It does NOT take a `ChainReader` / `GammaStore` / `BrokerClient` dependency.
`aggregate_delta` / `_position_delta` accept an optional `position_deltas: dict[str, Decimal] | None` (keyed by `instrument_key`, real option deltas in delta units). The **caller** —
`scripts/strategies/ic/ic_entry_gates.py` / `paper_ic_entry.py`, which already fetches the chain — resolves this map and passes it in. Fallback (paper phase only):
a missing key or a stale/failed chain fetch → log WARNING/ERROR (never silent) and fall back to the `net_qty / lot_size` approximation, do not block entry.
**This leniency is paper-phase only** — ratcheting the missing/stale/failed cases to fail-closed for live money requires a fresh council pass.

**IC entry gates split THRESHOLD vs STRUCTURAL, `--log-only-gates` default-on (2026-07-03).** THRESHOLD gates (IVR floor, DTE window, liquidity floor, portfolio-delta cap)
encode a risk judgment; under `--log-only-gates=True` a threshold failure persists a `GateViolation` row (`gate_violations` table, pre-aggregated `GROUP BY strategy_name, gate_name`)
and the trade proceeds. STRUCTURAL gates (duplicate-entry, `_post_expiry_gate`, unresolved instrument key, stale/missing VIX → `ivr=None`) are never bypassed — they still hard-block.
Rationale: accumulate 6 months of paper data on which threshold violations actually correlate with losses while exercising the full pipeline. `--force-entry`
(manual IVR-gate override, including structural `ivr=None`) is unchanged and orthogonal.

**Gate failure semantics — "state unknown" must fail closed (2026-08-20).**
A gate that exists to prevent a duplicate or unsafe action must treat "I can't determine the current state" as "assume worst case,
block" — never collapse it into the same return value as "state confirmed safe." Any existence-check-plus-sub-decision helper splits the two:
a robust existence check that fails closed, and a separate resolution step whose failure is distinguishable from "nothing to resolve."

**Nifty lot size resolved from BOD, fallback constant = 65 (2026-08-10).** Overlay auto-entry and roll-target `LegSpec` construction read `lot_size` off the selected strike's own BOD record
(`InstrumentLookup.get_by_key`), falling back to a named constant — **65** (corrected from a stale hardcoded 75) — only when the BOD record is missing / `lot_size <= 0`.

**Monthly expiry band floor = DTE 14 (2026-08-11).** `get_expiry_candidates()`'s `"monthly"` band requires `dte >= 14`, matching every caller's own entry gate
(was 15 — a guaranteed one-day-per-month dead zone). The weekly-Tuesday-claim guard is narrowed to the single overlapping point (`dte == 14 and is_monthly`).

---

## §7.3 — Multi-Strategy Portfolio Risk Caps (implementation reference)

**All binding rules — apply from Phase 0.6c onwards:**

| # | Rule |
|---|------|
| 1 | All Nifty option strategies are ONE portfolio risk unit |
| 2 | Options-only bullish delta cap: **+1.0 lot** (warning at +0.75) |
| 3 | Options + NiftyBees bullish delta cap: **+2.0 lots** (warning at +1.5) |
| 4 | −10% Nifty / IV+10–15 vol stress loss: ≤ ₹3L options-only, ≤ ₹4L with NiftyBees |
| 5 | Absolute portfolio drawdown kill zone: **₹6L** |
| 6 | Far OTM long puts (>15% OTM) receive no stress-loss credit; 8–15% OTM receives 50–70% credit |
| 7 | Size from internal stress-loss budget — never from broker SPAN margin |
| 8 | Shadow Gross Margin: must survive simultaneous removal of ALL SPAN offsets without exceeding 80% of ₹45L post-haircut collateral pool |
| 9 | Maximum short-put lots across all concurrent strategies: **2** |
| 10 | Protective hedge entries (Legs 2 and 3) are **never** blocked by the delta cap |
| 11 | Log every skipped signal: `DELTA_CAP \| STRESS_LOSS_CAP \| MARGIN_CAP \| DUPLICATE_EXPOSURE \| EVENT_FILTER \| TREND_FILTER \| LIQUIDITY_FILTER \| MANUAL_BLOCK` |

**Trade priority when delta cap binding:** Risk-reducing exits → Protective hedges (Legs 2/3) → Integrated CSP (Leg 1) → Standalone CSP v2 → Bearish swing spreads →
(covered call blocked)

**Scope narrowing (paper phase, 2026-07-03):** IC entries are judged **in isolation** — no portfolio-delta gating and no self-adjustment loop. Rules 2/3 (delta caps)
currently bind CSP and the overlay book; IC does not participate in the delta gate. Revisit before live money:
either wire real chain-derived cross-strategy delta or make a deliberate risk-acceptance call.

**Open calibration (Noted, deferred):** the hardcoded ₹ figures — stress caps ₹3L / ₹4L / ₹6L (rules 4–5) and the ₹45L post-haircut collateral pool (rule 8) —
need periodic recalibration as the real collateral value drifts.

---

## IV Reconstruction Methodology (2026-04-30)

**Key choices:**
- Pricing model: **Black '76** (Nifty Futures `settle_price` as forward `F` — eliminates dividend yield + carry adjustment)
- Risk-free rate: **Stepped RBI Repo Rate** (~20 entries, 2016–2024) in `src/backtest/repo_rates.py`
- Option price: **Guarded blend** — `close` if volume >0 and `|close − settle| / settle < 0.50`; else `settle_price`; mark unusable rows
- IV inversion: **`scipy.optimize.brentq`** per strike, bounds σ ∈ [0.01, 3.0]; exclude DTE <5, price <₹1, extrinsic <₹0.50
- Delta: **Quadratic smile fit** in log-moneyness (`np.polyfit`), then Black '76 delta from smoothed IV

**Module shape:**

| Module | Contents |
|---|---|
| `src/backtest/repo_rates.py` | `get_repo_rate(date) → float` |
| `src/backtest/greeks.py` | `black76_price`, `black76_iv`, `black76_delta`, `black76_gamma`, `black76_theta`, `black76_vega` |
| `src/backtest/iv_reconstruction.py` | `select_price_for_entry`, `fit_smile_and_get_delta`, `compute_30dte_atm_iv`, `iv_percentile`, `process_daily_chain` → `DailyChainResult` |
| `src/backtest/strike_selector.py` | `select_strike_by_delta(smile_df, target_delta, option_type)` |

---

## Slippage Model (2026-04-30)

**Absolute INR, VIX-regime-aware. Fill: SELL at `settle − s`, BUY at `settle + s`.**

| India VIX | Base slippage `s` |
|---|---|
| ≤ 20 | ₹1.0 |
| 20–25 | ₹1.5 |
| 25–30 | ₹3.0 |
| > 30 | ₹4.0 |

**OI liquidity multiplier applied to base `s`:**

| Strike OI | Multiplier |
|---|---|
| ≥ 50,000 | 1.0× |
| 20,000–49,999 | 1.5× |
| 5,000–19,999 | 2.0× |
| < 5,000 | 2.5× (flag as potentially unexecutable) |

Stop-loss exit multiplier: 1.5× (spreads widest during crashes). All backtest reports must include optimistic / base / conservative scenario table.

---

## Variance Gate — Phase 0.8 Deployment Tiers (2026-05-02)

| Tier | Requirements | Constraints |
|---|---|---|
| 0 — Paper only | Recording works, P&L reconciles | No live capital |
| 0.5 — Two-cycle review | After 2 paper cycles: strike/fill/P&L reconcile sanity | Operational only, not statistical |
| 1 — Limited live pilot | All Phase 0.8 criteria A–D met; `\|Z\| ≤ 1.5` regime-matched; all exit paths validated | 1 lot max; manual approval per entry |
| 2 — Normal v1 live | N ≥ 12 cycles OR N ≥ 6 + ≥1 genuine stressed episode; ≥1 delta-stop live | Runs as designed at conservative size |
| 3 — Overlay integration | N ≥ 18–24; full regime coverage; hedge-overlay interaction verified | Prerequisite for NiftyShield integrated |

Full gate specification: `docs/plan/variance_gate.md`.

---

## Iron Condor V2 Core Design (2026-06-26, council q10)

| Decision | Ruling |
|---|---|
| Entry deltas | `short_put_delta=0.25`, `short_call_delta=0.22`, `delta_range=0.03` (skew-adjusted, not symmetric) |
| Wing sizing | 10Δ long wing (primary); floors: monthly min ₹15, weekly min ₹10, min delta 5Δ; SD-width as sanity guard only (warn if >1.5× or <0.4×) |
| Adjustment mechanism | Partial roll of the challenged vertical only (4-leg atomic close+reopen); profitable side untouched; ≤ 1 roll/side/cycle; roll debit ≤ 50% of credit; inverted-condor guard |
| Weekly DTE cutoff | DTE≥6 normal roll; DTE 4–5 strict guards; DTE≤3 CLOSE_FULL (both sides); DTE≤1 CLOSE_FULL no discretion |
| Architecture | Separate class `ic_nifty_v2.py` + `ic_expiry_config_v2.py`; strategy names `paper_ic_nifty_v2_weekly` / `paper_ic_nifty_v2_monthly` |

Source: `docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md`

---

## Paper-Trade Exit Philosophy — Codification (2026-06-26, council q11)

Confirmed that existing codebase already implements the canonical rules. Codification only.

| Decision | Ruling |
|---|---|
| CC profit target | 70% captured (LTP ≤ 30% of entry credit); floor: entry_credit ≥ ₹15 — already `_PROFIT_TARGET_RETENTION=0.30`, `_CC_MIN_ENTRY_CREDIT=15` |
| CC loss stop | Delta ≥ 0.55 (primary) OR LTP ≥ 2.5× entry credit (backstop) — already implemented; `delta_threshold=0.55` in `_get_sell_audit_fields` |
| PP exit | Hold to expiry; CRASH_MONETIZE at δ≤−0.80 OR mark≥5× debit — already implemented |
| Collar exit | Atomic via `OverlayCloser.close_collar_all`; `monetize_collar_put` for crash scenario — already implemented |
| Phase 0 exit regime | Strictly static mechanical; log IVR/VIX/regime but do not condition on them |
| Automation tier | Tier 1 (EOD signal detection) mandatory; Tier 2 intraday deferred to Phase 1 |
| Exit signal storage | Separate `paper_exit_events` table (already exists) with OPEN→ACKNOWLEDGED→ACTED/DISMISSED lifecycle |
| Open gap | ~~TIME_STOP vs DTE_REVIEW priority ordering in `evaluate_cc` (EC-1)~~ Retired 2026-08-02, superseded by EC-5 — no other exit-signal evaluator shares the gap |

Source: `docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md`

---

## Strategy Monitor Fetch Architecture (2026-06-26, council q12)

| Decision | Ruling |
|---|---|
| Fetch architecture | Keep Option A — full chain every 90s; no protocol change |
| Roll target timing | Immediate selection inside `check_signals()` (strategy-side); executor revalidates at execution |
| `watchlist()` versioning | Deferred to Phase 1 (>20 legs or >1.5s/tick or rate limits) |
| Observability | Add two structured log lines: `strategy_monitor.chain_fetch_complete` (latency, strike_count, strategy_name) and `strategy_monitor.tick_summary` (signals emitted per tick) |

Noted, deferred: Hybrid split-fetch (LTP every tick + periodic Greeks) for Phase 1 when scale warrants it.
Source: `docs/archive/council/data_architecture/2026-06-26_strategy-monitor-watchlist-design.md`

---

## IC V2 Profit-Lock Adjustment (2026-06-27, council q13)

| Decision | Ruling |
|---|---|
| Zone 1 (25% captured) | Log-only. Record `profit_lock_zone=1`. No structural change, no debit. |
| Zone 2 (50% captured) | **Option A: spread-width contraction** — roll long wings to ~18–20Δ (atomic 4-leg). Floor `max(W_put,W_call)+D_cum+D_lock+K ≤ 0.75·C₀`; fail / width<100pts → CLOSE_FULL. |
| Zone 3 (75% captured) | CLOSE_FULL. Formula `W + debits + costs ≤ 0.35 × C₀` too tight for Nifty chains. State tracking retained for future use. |
| Floor guarantee mechanism | Defined-risk payoff geometry only — spread width is the hard bound. Greeks are probabilistic and cannot guarantee a floor. |
| D3 roll budget | Profit-lock wing rolls do **not** consume D3 defensive-roll budget (longs only; shorts untouched). After profit-lock, D3 width reference resets to new active width. |
| Simultaneous D3 + Zone 2 | Profit-lock executes first (risk-reducing); re-evaluate D3 on next tick with updated width reference. |
| Automation | `auto_execute=True`. No Telegram approval gate. Telegram notification fires after execution (confirmation only). CLOSE_FULL path also auto-executes. |
| IV/VIX guards | Secondary only. Allow Zone 2 if VIX≥11 and IVR≥0.20, OR if formula passes with K≥15pts buffer. Never override the mathematical formula. |
| DTE guards (monthly) | Lock window: DTE 10–22. Below 10 → skip lock. Above 22 → allow only if very cheap (D_lock<20pts). Below 7 → CLOSE_FULL already fires. |
| Debit cap | D_lock ≤ 25% of original entry credit. |
| Rejected | B (short-leg inward roll): no floor guarantee. C (delta-neutral hedge): continuous rebalancing, undefined risk. D (IV-conditional only): secondary guard, not primary. |

Noted, deferred: Delta-neutral futures overlay for Phase 2+ when live execution infrastructure exists.
Source: `docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md`

---

## B002.3 — `PaperPosition.option_type` resolution strategy (2026-07-02)

Read-time lazy resolution in `PaperStore.get_position`/`get_positions` via `InstrumentLookup`, not a write-time column on `paper_trades` and not a `legs` table join. Rejected: (b)
`legs` join — couples `src/paper/` to `src/portfolio/` schema, and paper positions aren't reliably `legs`-backed anyway; (c) resolve inside `src/risk/delta_tracker.py` directly —
adds a BOD-JSON filesystem dependency to a module whose tests are currently pure-data; write-time population — `PaperPosition` is documented as reconstructed on demand, never stored,
so a write-time column would need a schema migration + backfill for zero benefit over read-time resolution.
Failure mode: BOD JSON missing/corrupt, unresolved key, or a resolved `instrument_type` outside CE/PE/FUT all degrade to `option_type=None` + WARNING — never raises
(added after code-reviewer C1/C2/W1 findings; `get_position`/`get_positions` had zero BOD-file dependency before this
and must not become a hard failure point for callers like `monitor.py`/`executor.py`/snapshot scripts).
Full rationale: `docs/bugs/task.md` B002.3. Consumed by B002.4 (delta calc), not yet implemented.
Source: this session, SHA 96398b4.

---

## Deferred / Not Yet Built

- `src/strategy/`, `src/execution/`, `src/backtest/`, `src/risk/` (except 0.6c), `src/streaming/` — all empty
- Expired instruments via Upstox — blocked (paid). NSE F&O Bhavcopy is the adopted alternative (free)
- Liquidity buffer rule + OI-based margin haircut — deferred to Phase 2 `src/risk/` expansion

