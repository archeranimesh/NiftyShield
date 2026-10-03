# Gamma Scan Phase B — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

Source spec for every layer, threshold, ranking formula and exit rule: `docs/strategies/near_expiry_buy_v1.md` §6 (do not restate thresholds here — read them there). Each task's "Before any code" step
is mandatory: read the Phase A module it builds on via the graph (`src/gamma/derive.py`, `GammaStore`).

---

## GS-1 — `gamma_signal_log` model, DDL and store methods

**Files to change:** `src/gamma/models.py` (new frozen `GammaSignalLogEntry`), `src/gamma/store.py` (DDL + methods), `DB_REGISTRY.md`, `src/gamma/CLAUDE.md`, `tests/unit/gamma/test_gamma_store.py`.

**Before any code:** read `DB_REGISTRY.md` first; read strategy doc §11 for the `gamma_signal_log` DDL; `get_code_snippet("GammaStore")`.

**What to implement:** the frozen model and the idempotent `CREATE TABLE IF NOT EXISTS` (monetary/precise values stored as TEXT, read back via `Decimal`). Store methods: `insert_signal_log` (one row
per evaluated strike, carrying `watchlist_hit`, `watchlist_elevated`, the failing-layer reason code and the paper-trade attempted/filled flags), `update_signal_exit` (E1/E2/E3 exit fields), and
`get_open_signal_positions` (rows with an entry and no exit, per direction).

**Tests:** insert + read-back round-trips `Decimal` exactly; re-running table creation is a no-op; `update_signal_exit` on an unknown id is a no-op that returns `False`; `get_open_signal_positions`
returns only un-exited entries.

**Commit:** `feat(gamma): add gamma_signal_log model and store`

---

## GS-2 — Signal stack (Layers 0–4)

**Files to change:** `src/gamma/signals.py` (new), `tests/unit/gamma/test_signals.py` (new), `src/gamma/CLAUDE.md`.

**Before any code:** read strategy doc §6 in full; `get_code_snippet("GammaChainSnapshot")`; the Phase A `derive.py` field list so predicates consume fields instead of recomputing them.

**What to implement:** each layer condition is a small predicate `(Candidate, SignalConfig) -> ReasonCode | None` (`None` = pass). `SignalConfig` is a frozen dataclass holding every threshold.
`SignalStack` holds an ordered list of layers and evaluates them in a loop, returning the first failing reason code or a pass. No `elif` chain, no threshold literals in predicate bodies. Layer 3
Condition B (IV percentile) is skipped — with a distinct reason code, not a pass-by-default — until `strike_iv_pctile_20d` exists. `watchlist_hit` is carried on the result but never changes the
outcome.

**Tests:** per predicate, one pass and one fail at the boundary value; stack stops at the first failure and reports its code; Layer 3 Condition B absent-history path; `watchlist_hit` does not alter
pass/fail.

**Commit:** `feat(gamma): add signal stack layers 0-4`

---

## GS-3 — Depth source

**Files to change:** `src/gamma/depth.py` (new Protocol + `NullDepth`), `src/dhan/` adapter implementing it (follow `src/dhan/CLAUDE.md`), tests for both.

**What to implement:** `DepthSource.fetch(instrument) -> DepthSnapshot | None` Protocol (constructor-injected into the scan). `NullDepth` always returns `None` (reduced mode, used when
`DHAN_DATA_API_KEY` is unset). The Dhan adapter wraps API/timeout/rate-limit failures into the existing exception hierarchy and the scan treats any failure as `None`, never as a crash. Use an explicit
timeout on the call.

**Tests:** `NullDepth` returns `None`; adapter happy path from a fixture; adapter timeout and HTTP error paths map to the hierarchy; no network (recorded fixture only).

**Commit:** `feat(gamma): add depth source protocol and dhan adapter`

---

## GS-4 — Ranking and exits

**Files to change:** `src/gamma/ranking.py`, `src/gamma/exits.py`, `tests/unit/gamma/test_ranking.py`, `tests/unit/gamma/test_exits.py` (all new), `src/gamma/CLAUDE.md`.

**What to implement:** `rank_candidates(candidates) -> list[Candidate]` implementing the §6 formula `(gamma_gearing × 0.7) + (watchlist_hit × 0.3 × gamma_gearing)` with `Decimal` and a deterministic
tie break. `evaluate_exit(position, tick, config) -> ExitDecision | None` with E1/E2/E3 as separate small rules in an ordered list (same shape as the signal stack); each returns its exit reason.

**Tests:** ranking order including the watchlist boost and a tie; each exit rule fires at its boundary and not one tick before; no exit returns `None`.

**Commit:** `feat(gamma): add candidate ranking and exit rules`

---

## GS-5 — `scripts/gamma_scan.py`

**Files to change:** `scripts/gamma_scan.py` (new, logger name `scripts.gamma_scan`, `setup_logging()` per `LOGGING.md`), `tests/unit/scripts/test_gamma_scan.py` (new), `src/gamma/CLAUDE.md`.

**What to implement:** thin orchestration of the §6 "gamma_scan.py responsibilities" sequence, with every collaborator injected: `ChainSource`, `DepthSource`, `GammaStore`, `SignalStack`, a
paper-entry adapter (wraps the existing `record_paper_trade` functions — **not** a subprocess), and the notifier. Reuse Phase A's `derive_snapshots` and `get_active_watchlist` (for `watchlist_hit` and
`watchlist_elevated`). Write one `gamma_signal_log` row per evaluated strike regardless of outcome. **Double-fire protection (required):** hold a non-blocking process lock for the whole run (a second
concurrent run logs and exits 0), and perform the "no open position in this direction" check and the entry insert in one DB transaction so two runs cannot both open. Skip outside DTE 0–1 and on
non-trading days. Telegram is non-fatal. Support `--dry-run`: evaluate and write `gamma_signal_log` rows (that data is the point of the dry-run) but never record a paper trade or send Telegram.

**Tests:** end-to-end with all mocks (stages run in order); lock held → second run exits without trading; existing open position in the same direction → no second entry; reduced mode (`NullDepth`)
still evaluates; notifier failure is non-fatal; non-DTE-0/1 day is a no-op.

**Commit:** `feat(gamma): add gamma_scan intraday signal scan`

---

## GS-6 — Cron and dry-run validation

**Files to change:** crontab entry (documented in `docs/strategies/near_expiry_buy_v1.md` §12 / the cron doc named in `CLAUDE.md` Quick reference), `.env.example` (`DHAN_DATA_API_KEY`, `GAMMA_*`
overrides), `TODOS.md`.

**Re-derive the days first:** the strategy doc's `3,4` (Wed/Thu) predates the April 2026 move to Tuesday expiry — DTE 1 is Monday and DTE 0 is Tuesday, so the cron days are likely `1,2`. Confirm via
`REFERENCES.md` and `resolve_expiries`, and fix §3/§12 of the strategy doc, before adding the line. The daily-watch script path in §12 is also stale (`scripts/pipeline/gamma_daily_watch.py`).

**What to implement:** add the cron line (days per the re-derivation above; the doc's `*/5 9-15 * * 3,4` is the stale baseline); run `gamma_scan.py --dry-run` on the first qualifying scan day (not
necessarily a Wednesday — see above) and review the log for stale-OI, rate-limit and market-close edge cases; record findings. No code change expected — a code fix found here becomes its own follow-up
task.

**Commit:** `docs(gamma): enable gamma_scan cron and record dry-run`
