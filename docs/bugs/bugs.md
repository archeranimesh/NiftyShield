# Bug Registry

> One entry per confirmed defect. Do not log speculative issues here — confirm root cause
> first (graph trace / repro), then log. Suspicions belong in `TODOS.md` until confirmed.
> Status values: `🔴 Open` → `🟡 Fix in progress` → `✅ Fixed` (link commit SHA) → `⚪ Won't fix` (with reason).
>
> **Scope:** confirmed defects in live/shipped code (paper trading, cron scripts, live
> gates) — not unimplemented spec items, those are `docs/plan/` story tasks.
>
> **Relationship to root `BUGS.md`:** a bug registry already existed at the repo root
> (`BUGS.md`, single open entry `BUG-001` — `daily_snapshot.py` backfill gap, unrelated,
> low severity). This folder is the canonical home for *new* entries going forward; root
> `BUGS.md` is not migrated, it stays until `BUG-001` is fixed and deleted per its own
> convention. ID numbering is one shared sequence across both files — this registry
> starts at `BUG-002`.
>
> **This file holds only open work — the `stories.md` equivalent for `docs/bugs/task.md`'s
> checklist.** `docs/bugs/task.md` is the lean checkbox list; every entry here has the full
> symptom/root-cause/fix detail a task's checkbox alone can't carry. Once a `BUG-NNN`'s every
> `task.md` line is checked and the fix is committed, move its entry to
> `docs/archive/bugs/bugs.md` (and its checklist to `docs/archive/bugs/task.md`) in the same
> commit that flips `Status` to ✅ Fixed — mirrors the `docs/plan/` → `docs/archive/plan/`
> convention. **24 bugs archived 2026-08-13** (`BUG-002` through `BUG-028` minus the 5 below);
> see `docs/archive/bugs/bugs.md` for their full history.

---

## BUG-019 — Investigation: does every strategy show a live-tick vs. EOD-snapshot P&L disparity, not just `paper_ic_nifty_v2_monthly`?

| Field | Value |
|---|---|
| Severity | **Under investigation** — not yet confirmed as a bug beyond the BUG-018 case; diagnostic instrumentation added to gather evidence across all strategies |
| Status | 🔍 Diagnostics added and committed (2026-07-23, SHA `f7177b6`), awaiting a live trading day's data before any fix is scoped |
| Discovered | 2026-07-23, as a direct generalisation of BUG-018 — Animesh: "can we have some debugs added to check for all the strategy what is the PNL at 15:30 and what does the snapshot measure, i believe there is a disparency" |
| Location | `src/strategy/monitor.py::StrategyMonitor` |

**Hypothesis being tested:** BUG-018 showed `paper_ic_nifty_v2_monthly`'s own internal P&L computation (`_compute_combined_pnl` inside `check_signals`) never ran at all (silently short-circuited before reaching it) — so the "disparity" there was actually "the live side computed nothing," not "the two sides computed different numbers using the same inputs." Now that BUG-018 is fixed, Animesh suspects a *broader* disparity may exist across all strategies between what the live monitor tick sees intraday (specifically near close, ~15:30) and what `paper_snapshot.py`'s EOD cron records a few minutes later (~15:35-15:36). This could be: (a) a genuine last-minute market move between the last tick and the EOD read (not a bug), (b) a real computation/staleness bug independent of BUG-018, or (c) nothing — the two readings may in fact agree once V2 is no longer blind.

**Instrumentation added (2026-07-23):** `StrategyMonitor._log_live_pnl_diag()`, called at the end of every `_tick()`. Restricted to the 15:20-15:30 IST window (not every ~90s tick all day, to avoid adding a `get_ltp` batch call per strategy on every tick). For every registered strategy with at least one open leg (`net_qty != 0`), it calls `PaperTracker.compute_pnl(strategy_name)` — the *exact same function* `paper_snapshot.py`'s EOD cron calls, not an approximation — and logs `strategy_monitor.live_pnl_diag` with `unrealized_pnl`/`realized_pnl`/`total_pnl`/`time`. Because it's the identical function, any gap between this tick's reading (~15:20-15:30) and the EOD snapshot's own log line (`Recorded paper NAV snapshot for '<strategy>' ... total_pnl=X`, ~15:35-15:36) is a genuine timing/staleness disparity, not a methodology difference — the two sides can be diffed directly.

**Tests:** `tests/unit/strategy/test_strategy_monitor.py` — `test_live_pnl_diag_logged_inside_close_window`, `test_live_pnl_diag_skipped_outside_window`, `test_live_pnl_diag_skipped_when_strategy_flat`, `test_live_pnl_diag_swallows_compute_pnl_exception`, `test_live_pnl_diag_skipped_when_compute_pnl_returns_none`, `test_live_pnl_diag_window_boundaries` (parametrized, added after code review — see below). **Not run in-sandbox** (same disk-quota limitation as BUG-018) — verified via `py_compile` only, pending live-host `pytest` run.

**Code review (2026-07-23):** general-purpose agent loaded `.claude/agents/code-reviewer.md` + `REVIEW.md` directly and reviewed the scoped diff. 1 CRITICAL, 2 WARNING, 1 INFO — all resolved before commit:
- **CRITICAL** (REVIEW.md G5): `except Exception:` in `_log_live_pnl_diag` lacked the required inline `# Intentional: ...` comment (the docstring rationale doesn't satisfy the rule as written). Fixed: added inline comment on the `except` line.
- **WARNING**: the diag call was awaited *before* `_write_heartbeat`, so a slow/hanging `get_ltp` inside the comparison window could delay heartbeat freshness — a real (if narrow) production effect for something meant to be a pure side-channel. Fixed: reordered so `_write_heartbeat` runs first, diag call moved after.
- **WARNING**: the original tests covered only one clearly-inside (15:25) and one clearly-outside (11:00) time, leaving the inclusive `_PNL_DIAG_WINDOW_START`/`_MARKET_CLOSE` boundaries (15:20, 15:30) and the just-outside minutes (15:19, 15:31) unasserted — exactly where off-by-one errors hide. Fixed: added `test_live_pnl_diag_window_boundaries` (parametrized, 4 cases).
- **INFO**: mocking `monitor._tracker` post-construction (rather than mocking broker/store) verified as a reasonable unit-test strategy — the real `PaperTracker(store, broker)` wiring still runs in `__init__` via `_make_monitor`, no integration gap hidden. No action needed.
Decimal correctness (`str(unrealized)` etc., no float leakage) and the `PaperTracker(store, broker)`/`BrokerClient`-satisfies-`MarketDataProvider` wiring both verified clean.

**Next step:** after the next trading day, grep `logs/monitor_daemon.log` for `strategy_monitor.live_pnl_diag` (per strategy, 15:20-15:30 entries) and `logs/paper_snapshot.log` for `Recorded paper NAV snapshot` (same day), diff the last live reading against the EOD figure for every strategy. If a real gap shows up beyond what a few minutes of market movement could plausibly explain, escalate to a proper BUG-0XX with root-cause investigation; if not, remove this diagnostic (same 2026-07-24-style cleanup as BUG-018's temp logs, timeline TBD based on how many days of data are needed).

**Committed:** SHA `f7177b6`.

**Related:** BUG-018 (the specific case that prompted this generalisation).

---

## BUG-025 — MC-3b review follow-ups: `roll_ic_legs` open-only write shape, `PROFIT_LOCK_ZONE2` state/write ordering

| Field | Value |
|---|---|
| Severity | **LOW** — both are theoretical/edge-case findings from the MC-3b review pass, not confirmed live symptoms; logged so they aren't lost, not because either is known to have fired. |
| Status | 🔴 Open (not fixed — deliberately deferred, not blocking) |
| Discovered | 2026-08-06, `@code-reviewer`-substitute pass on MC-3b (IC-CLOSE-2 roll persistence, `docs/plan/monitor-and-close-hardening/tasks.md`). |
| Location | `src/strategy/ic_close_executor.py::roll_ic_legs` (W1); `src/strategy/ic_nifty_v2.py::IronCondorV2.apply_action`'s `PROFIT_LOCK_ZONE2` branch (W2). |

**W1 — `roll_ic_legs`'s empty-check doesn't require `to_close` non-empty when `open_legs` is non-empty.** The guard is `if not to_close and not open_legs: ... return []` — if `closed_roles` matches zero live positions (stale role, already-closed leg from a race) but `open_legs` is non-empty, the function proceeds and writes an open-only trade: a new leg with nothing closed. Not the naked-position failure mode MC-3b was built to prevent (this is the inverse — extra/duplicate exposure), and in every current call site `closed_roles` is derived from the same in-memory position list passed as `close_positions`, so it's unlikely to diverge today. No fix applied — either assert `to_close` non-empty when `open_legs` is non-empty, or explicitly document an open-only write as an accepted `roll_ic_legs` outcome, next time this function is touched.

**W2 — `PROFIT_LOCK_ZONE2`'s `ProfitLockState` persistence and Telegram notification happen before `roll_ic_legs`'s success is known.** `apply_action` calls `store.set_profit_lock_state(..., zone2_lock_executed=True)` and sends the Zone 2 notification in one branch, then calls `roll_ic_legs` in a separate, later branch. If `roll_ic_legs` fails (broker/store exception, or its own price-guard aborts), the state store already says the zone-2 lock executed while the actual leg replacement never persisted — a state/reality divergence visible on the next signal-evaluation tick. This ordering pre-dates MC-3b (the state persistence already existed; only the trade-write call is new) so it isn't a regression introduced by this task, but MC-3b was the natural point to reorder (persist state only after confirming `roll_ic_legs` returned non-empty) and that reorder wasn't done. No fix applied — flagged for a fast-follow.

**Related:** MC-3b (`docs/plan/monitor-and-close-hardening/tasks.md`), BUG-023, BUG-024.

---

## BUG-027 — `scripts/healthcheck.py` never calls `load_dotenv()`; every healthcheck alert has silently no-op'd since at least 2026-08-04

| Field | Value |
|---|---|
| Severity | **HIGH** — not a financial-logic defect, but this is the project's dead-man's-switch cron (`CONTEXT_TREE.md`: "Dead man's switch for EOD cron validation"). Its entire purpose is to alert when something else is broken; it has been silently failing to alert for at least 4 trading days with zero downstream signal — the exact "silent automation failure" class `BUG-026` also hit. |
| Status | 🟡 Fix in progress — `load_dotenv()` added + 4 new tests green (`docs/bugs/task.md` B027.1-3 done), commit + `bugs.md` status flip still outstanding (B027.4) |
| Discovered | 2026-08-10, Animesh reported seeing healthcheck log entries but no Telegram messages, while other scripts' Telegram alerts (`paper_3track_snapshot.py`, `eod_summary.py`, etc.) were arriving normally — investigated during the `telegram-markdown-migration` ROLL-11 workshop session. |
| Location | `scripts/healthcheck.py` (imports, lines 16-30) — missing `from dotenv import load_dotenv` + `load_dotenv()` call present in every sibling cron script. |

**Symptom:** `logs/healthcheck.log` shows, on every single run from 2026-08-04 through 2026-08-07 (and presumably every run since): the check messages print correctly (`✅ DB: accessible`, `⚠️ VIX data: N days stale`, etc.), `has_issue=True` is correctly detected, `main()` logs `WARNING System healthcheck failed or warned`, then immediately: `[INFO] [__main__] Telegram notifier not configured. Skipping alert.` No Telegram message is ever sent, on any run where an alert should have fired.

**Root cause:** `build_notifier()` (`src/notifications/telegram.py:119-151`) deliberately constructs a fresh, uncached `Settings(_env_file=None)` on every call (see `BUG-011`'s 2026-08-06 fix) — it reads `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` **only** from the real OS process environment, never from `.env`. Every other cron-invoked script in this codebase (`paper_3track_snapshot.py`, `eod_summary.py`, `daily_snapshot.py`, `paper_ic_snapshot.py`, `paper_ic_entry.py`, ~25 files total, confirmed via `grep -rn "load_dotenv"`) calls `from dotenv import load_dotenv` + `load_dotenv()` near the top of the file *before* `build_notifier()`/`settings` is ever touched. `load_dotenv()` mutates `os.environ` directly as a side effect — that's what actually gets the token into the process environment `build_notifier()`'s `Settings(_env_file=None)` reads from. Cron's own environment never has these vars set directly (confirmed — `logs/cron.log`'s tracked crontab entries have no env-var preamble, and healthcheck's crontab line is a bare `cd ... && .venv/bin/python -m scripts.healthcheck`, identical in shape to every other job). `scripts/healthcheck.py`'s import block (lines 16-30) has no `dotenv` import and no `load_dotenv()` call at all — so under cron, `os.environ` is genuinely empty for these two vars by the time `build_notifier()` runs, and it correctly (per its own contract) returns `None`.

**Why other scripts aren't affected:** identical `build_notifier()` call, identical cron invocation pattern (`cd <repo> && .venv/bin/python -m scripts.<module>`, no env-var prefix) — the only difference is every working script's own `load_dotenv()` call populating `os.environ` first. This was confirmed directly, not inferred: `grep -rn "load_dotenv"` across `src/`+`scripts/` returns the pattern in ~25 files; `scripts/healthcheck.py` is not among them.

**Impact:** the healthcheck cron (`55 15 * * 1-5`) has been running "successfully" (exit code aside — `main()` still returns 1 on `has_issue`, so the cron *does* register a failure exit code, but with no human-visible alert) with zero operator-visible signal for at least the 4 trading days captured in the current `logs/healthcheck.log` window, and plausibly since the script was first deployed (`RO-4`, `docs/archive/plan/reporting-and-ops-fixes/tasks.md`) — no evidence in that task's spec that this was ever tested end-to-end against a real cron environment (only interactively, where a developer's shell likely already had the tokens exported).

**Suggested fix:** add the same two-line pattern every sibling script already uses, before `build_notifier()`/`settings` is used:

```python
from dotenv import load_dotenv
...
load_dotenv()
```

placed the same way `eod_summary.py`/`paper_3track_snapshot.py` do it (module-level, near the top, before other project imports that might touch settings). This is a real code fix, not a docs-only or formatting change.

**Suggested regression test:** mirror the pattern other `load_dotenv()`-bearing scripts' test files use (if any test asserts this — check via `search_graph` before assuming none exists) — a test that clears `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` from `os.environ` via `monkeypatch.delenv`, writes a fixture `.env` file with both values set, imports/reloads `scripts.healthcheck`, and asserts `build_notifier()` now resolves to a real notifier (not `None`) — proving the module-level `load_dotenv()` call actually runs and actually populates the environment before any notifier construction.

**Related:** `BUG-011` (the `build_notifier()` `Settings(_env_file=None)` design this bug's root cause depends on); `BUG-026` (same failure shape — a live-capital-adjacent automation silently no-op'ing with no downstream alert, discovered the same way: an operator noticing an absence rather than an error).

**Implementation progress (2026-08-13, moved here from `task.md` during archival cleanup):**
`from dotenv import load_dotenv` + a module-level `load_dotenv()` call added to
`scripts/healthcheck.py`, placed before the `src.*` imports — same placement convention as
`scripts/eod_summary.py` (`# noqa: E402` on the now-late `src.*` imports). 4 new tests in
`tests/unit/test_healthcheck.py` (8/8 total pass): the core regression test (patches
`dotenv.load_dotenv`, reloads the module, asserts called once — this is the test that would have
failed pre-fix), a real-fixture-`.env` resolution test, a no-regression "still `None` without
configured env" test, plus a `_reload_healthcheck_without_touching_real_env()` helper (discovered
mid-session that real `load_dotenv()` mutates `os.environ` directly, leaking into later tests
unless carefully isolated; also confirmed `monkeypatch.chdir()` does not control which `.env`
`load_dotenv()` discovers — it walks up from the caller's source file, not `cwd`). Self-reviewed
against `REVIEW.md` (import ordering, no unused imports, comment explains *why* not just *that*)
— a real `@code-reviewer`/`general-purpose` agent pass is still recommended before commit.
**Not yet done:** commit, flip this Status line to ✅ Fixed + SHA, `TODOS.md` session log line.

---

## BUG-029 — `paper_exit_events.counterfactual_dte_marks` migration committed but never run against the live DB; `paper_3track_snapshot.py`'s 15:35 EOD cron has crashed every market day since 2026-08-05

| Field | Value |
|---|---|
| Severity | **HIGH** — not a P&L-correctness defect, but a full crash of the daily 3-track snapshot script before it reaches exit-signal evaluation (delta-stop/premium-stop checks for all base + overlay legs) or the overlay P&L/leg-snapshot/protection-recovery pipeline (BUG-028's fix target). Zero downstream signal — the crash is logged but nothing alerts on it, same silent-failure shape as BUG-026/027. |
| Status | 🟡 Discovered 2026-08-10 while investigating BUG-028 Phase 3. Test coverage for the pre-existing (2026-08-05) migration script committed, SHA `c8d5baa` — all 4 tests confirmed green on live host. **Migration run against the live DB 2026-08-10** (Animesh) — `counterfactual_dte_marks` confirmed present on `paper_exit_events` via direct `PRAGMA table_info` check, and the previously-crashing query now executes clean. Note: today's (2026-08-10) 15:35 cron ran *before* the migration and still crashed as usual — that run's overlay P&L/leg-snapshot/protection-recovery rows were never written (script terminated at the exit-signal step, confirmed via `logs/paper_snapshot.log` traceback at `paper_3track_snapshot.py:1925`). **Still outstanding**: confirm tomorrow's (2026-08-11) 15:35 cron completes with no traceback, then backfill 2026-08-10's missed rows via `paper_3track_snapshot --no-dry-run` (B029.4), plus B029.5 (healthcheck coverage, non-blocking) and B029.6 (commit + close). See `docs/bugs/task.md` B029.1+. |
| Discovered | 2026-08-10, while checking `logs/paper_snapshot.log`/`logs/cron.log` to see whether today's PP overlay trade had propagated to `paper_overlay_pnl_snapshots`/`paper_leg_snapshots`. It hadn't — traced to a crash in the same cron run, not a data-attribution gap. |
| Location | `src/paper/store.py::PaperStore.get_open_exit_events()` (crash site, `SELECT` includes `counterfactual_dte_marks`); `scripts/strategies/three_track/paper_3track_snapshot.py::compute_and_record_exit_signals()` → `_run()` (caller, crash occurs before overlay P&L/leg-snapshot/protection-recovery code further down the same function ever runs); `scripts/dev/migrate_exit_events_counterfactual_dte_marks.py` (the fix — already existed, never executed). |

**Symptom:** `logs/paper_snapshot.log`'s `35 15 * * 1-5` cron entry (`scripts.strategies.three_track.paper_3track_snapshot --no-dry-run`) has thrown an identical unhandled `sqlite3.OperationalError: no such column: counterfactual_dte_marks` traceback at `compute_and_record_exit_signals()` → `store.get_open_exit_events()` on every market day from 2026-08-05 through 2026-08-10 (confirmed by direct log inspection, not inference — same file/line/error on 08-05, 08-07 [Wed/Thu logs rotated out but 08-05/08-07/08-10 confirmed present], 08-10). A separate, unrelated cron entry (`36 15 * * 1-5`, `scripts.portfolio.paper_snapshot`) writes to the same log file and succeeds independently — its `total_pnl` NAV rows continuing to appear made the crash easy to miss, since *something* useful still landed in the DB every day.

**Root cause:** Commit `17b4ff9` (`feat(paper): add counterfactual_dte_marks column to paper_exit_events`, 2026-08-05 13:11 IST, Animesh) correctly added the column to `_SCHEMA`, to `create_exit_event`/`get_exit_event`/`get_open_exit_events`'s queries, **and** shipped a migration script (`scripts/dev/migrate_exit_events_counterfactual_dte_marks.py`) in the same commit — the code-side change was done properly. But committing a migration script does not run it: nothing in `docs/bugs/task.md`, `TODOS.md`, or `DECISIONS.md` records it ever being executed against `data/portfolio/portfolio.sqlite`, and a direct schema diff (fresh in-memory DB built from `_SCHEMA` vs. the live DB, checked 2026-08-10) confirms the live table is still missing the column. This is a process gap, not a code defect — the same class of "committed the fix, never ran the migration" miss, just never surfaced until a code path that actually selects the column executed (`get_open_exit_events`, called daily by the 3-track snapshot script, but apparently not exercised by anything else that runs more frequently/visibly).

**Fix:** run the existing migration (`python -m scripts.dev.migrate_exit_events_counterfactual_dte_marks`) against the live DB; add test coverage for the migration script, which had none (`tests/unit/scripts/test_migrate_exit_events_counterfactual_dte_marks.py`, 4 tests: column added + existing row preserved, idempotent re-run, dry-run no-write, no-op on an already-migrated DB). `general-purpose`+`REVIEW.md` substitute review: no CRITICAL/ERROR/WARNING — migration script confirmed correct as originally written (idempotent, dry-run safe, correct use of `src.db.connect()`, `ALTER TABLE ADD COLUMN` confirmed safe/cheap since `paper_exit_events` is non-`STRICT`); the review's one INFO note flagged that running the migration against the live DB is the actual operational fix and is separate from committing test coverage — see `docs/bugs/task.md` B029.1+ for whether that's been done this session.

**Related:** BUG-026/BUG-027/BUG-028 — same silent-failure shape (a broken automation path producing zero operator-facing signal until someone manually checks a log file); unlike those three, the code itself was correct from day one here — this is purely a "shipped fix, never deployed it" gap, suggesting the missing safeguard is process (a migration-execution checklist item, or `scripts/healthcheck.py`/`position_health_check.py` gaining coverage for "did the 3-track snapshot script's last run exit 0") rather than anything to fix in the migration script itself.

---

## BUG-030 — `_overlay_type_groups()` elif-precedence drops an `overlay_cc` leg whenever an `overlay_collar_put` leg is also present same-day; corrupts the Collar P&L figure and produces a false "CC No data" line in the recovery digest

| Field | Value |
|---|---|
| Severity | **HIGH** — live P&L-correctness defect, not just a reporting gap. Silently drops a real, open leg's P&L (`overlay_cc`, +₹53.625 on 2026-08-13) from both `paper_overlay_pnl_snapshots` and the daily "NiftyBees vs overlays" Telegram digest, and folds a mislabeled result into the `collar` row instead — the displayed Collar P&L (-₹973) is understated by the missing call leg's contribution (true value -₹919.75). No exception, no warning specific to this combination — same silent-failure shape as BUG-026/027/028. |
| Status | 🔴 Open — found 2026-08-13, not yet fixed. |
| Discovered | 2026-08-13, Animesh flagged that the "NiftyBees vs overlays" Telegram digest showed `CC No data` despite an open, correctly-recorded CC position (`STRATEGY_OVERLAY`, `overlay_cc`, SELL 65 lots, opened 2026-08-12, today's `paper_leg_snapshots.total_pnl` = +53.625). Traced live against `data/portfolio/portfolio.sqlite` during the investigation — not inferred from logs. |
| Location | `scripts/strategies/three_track/paper_3track_snapshot.py::_overlay_type_groups()` (lines 1081-1117, root cause); `_compute_overlay_pnl_snapshots()` (lines 1137-1219, downstream — never emits an `overlay_type='cc'` row when this fires); `_build_recovery_digest()` (lines 1537-1593, renders the resulting gap as "CC No data" — that part of BUG-028 Phase 2 is working exactly as designed, it just never sees a `cc` row to render). |

**Symptom:** `paper_overlay_pnl_snapshots` has zero `overlay_type='cc'` rows for either 2026-08-12 or 2026-08-13, despite `paper_leg_snapshots` showing a real, open `overlay_cc` leg with nonzero `total_pnl` on both dates (-537.875 on 08-12, +53.625 on 08-13 — confirmed via direct query). The `collar` row for the same dates contains only the `overlay_collar_put` leg's P&L (08-13: `pnl_inception_abs = -973.375`, exactly matching the put leg alone) — the `overlay_cc` leg's P&L is not merged into it, not reported separately, and not visible anywhere downstream. The digest renders `CC No data`, which BUG-028 Phase 2 correctly distinguishes from a false `+0` — but the underlying condition it's flagging (no `cc` row exists) is itself the bug, not a legitimately absent leg.

**Root cause:** `_overlay_type_groups(present_roles)` decides which `overlay_*` leg_roles combine into a `cc`/`pp`/`collar` reporting row via an `if/elif` chain:

```python
if has_call and has_put:
    groups["collar"] = ["overlay_collar_call", "overlay_collar_put"]
elif has_call:
    groups["cc"] = ["overlay_collar_call"]
elif has_put:
    groups["collar"] = ["overlay_collar_put"]      # fires here
elif has_cc:
    groups["cc"] = ["overlay_cc"]                   # never reached
```

`has_call`/`has_put`/`has_cc` are computed independently from `present_roles`, but the chain only ever branches on `has_call`/`has_put` — `has_cc` is checked last and is unreachable whenever `has_put` is `True`, regardless of whether `has_cc` is also `True`. The live position hit exactly this: a short call opened under leg_role `overlay_cc` (not `overlay_collar_call`) and a long put opened under `overlay_collar_put`, both same-day (2026-08-12) — economically a collar, but tagged with a `cc`-style role for the call leg rather than a `collar`-style one. `has_call=False`, `has_put=True`, `has_cc=True`. The chain falls into the `elif has_put` branch, builds `collar` from `overlay_collar_put` alone, and the `overlay_cc` leg is never added to any group in `groups`, so `_compute_overlay_pnl_snapshots`'s `for overlay_type, roles in groups.items()` loop never sees it — no row is ever written for it, silently.

This is orthogonal to BUG-028: that bug was entirely about *which `strategy_name` to query* (track-scoped vs. `STRATEGY_OVERLAY`) and none of its four phases touched leg-role grouping. `_overlay_type_groups` predates BUG-028 and was carried over unmodified by all four phases — this defect exists whether or not BUG-028's fix is applied.

**Two distinct questions, not yet resolved:**
- **Entry-side:** should the call leg have been tagged `overlay_collar_call` instead of `overlay_cc` when the put was added same-day, converting what may have started as a standalone CC into a collar? If so the real fix is in the overlay entry path (`paper_3track_overlay_entry.py`'s collar/CC entry logic), not here. Not yet investigated — flagged, not diagnosed.
- **Reporting-side, true regardless of the above:** `_overlay_type_groups` has no branch for `has_cc and has_put` simultaneously. Even if the entry-side tagging is intentional (e.g., an operator manually added a hedge put against an existing CC without converting its role), the grouping function must not silently drop one of the two legs — it needs an explicit branch that either merges `overlay_cc` + `overlay_collar_put` into `collar`, or reports both legs' P&L (as separate `cc`/`collar` rows or a combined row), matching whichever semantics is actually decided for the entry-side question above.

**Suggested fix:** do not patch this inline without a decision on the entry-side question first — the two questions are coupled (the grouping fix depends on what the correct leg_role *should* have been). At minimum, add a regression test asserting `_overlay_type_groups({"overlay_cc", "overlay_collar_put"})` does not silently drop either role, whatever the resolved semantics turn out to be. Given this affects live daily P&L reporting the same way BUG-028 did, this likely qualifies for the same council-checkpoint bar BUG-028 used (`docs/council/README.md`'s three-condition check) if the entry-side fix changes how future collar/CC positions get tagged.

**Related:** BUG-028 (same file, same overlay-reporting pipeline, same "silent gap read as legitimate zero/no-data" failure shape, but a different root cause — namespace vs. leg-role grouping — and BUG-028's four phases did not cover this).

---
