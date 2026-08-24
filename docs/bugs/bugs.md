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

**Investigation result (2026-08-24):** ran the diff the "Next step" above calls for, across 5
separate trading days now present in `logs/monitor_daemon.log`/`logs/paper_snapshot.log`
(08-14, 08-17, 08-19, 08-20, 08-21) — last `strategy_monitor.live_pnl_diag` tick (15:28-15:29)
vs. the EOD `Recorded paper NAV snapshot` line (~15:35-15:36) for each strategy:

| Date | Strategy | live total_pnl | EOD total_pnl | diff |
|---|---|---|---|---|
| 08-14 | v1_leaps | 3805.75 | 3675.75 | -130.00 |
| 08-14 | v2_monthly | 2129.29 | 2002.54 | -126.75 |
| 08-17 | v1_leaps | 4056.00 | 4062.50 | +6.50 |
| 08-19 | v1_weekly | 3692.00 | 3692.00 | 0.00 |
| 08-19 | v1_monthly | 4917.79 | 4882.04 | -35.75 |
| 08-19 | v1_leaps | 3003.00 | 2944.50 | -58.50 |
| 08-19 | v2_monthly | 5828.88 | 5825.62 | -3.26 |
| 08-20 | v1_weekly | 3695.25 | 3734.25 | +39.00 |
| 08-20 | v1_monthly | 5281.79 | 5223.29 | -58.50 |
| 08-20 | v1_leaps | 4400.50 | 4179.50 | -221.00 |
| 08-20 | v2_monthly | 5731.38 | 5802.88 | +71.51 |
| 08-21 | v1_leaps | 4494.75 | 4468.75 | -26.00 |
| 08-21 | v1_monthly | 5337.04 | 5311.04 | -26.00 |
| 08-21 | v1_weekly | 4176.25 | 4166.50 | -9.75 |
| 08-21 | v2_monthly | 6108.37 | 6137.62 | +29.25 |

No systematic bias — sign flips constantly, magnitude tracks how much the market actually moved
that day (near-zero on the quiet 08-19 weekly reading vs. -221 on the more volatile 08-20
leaps reading), and one exact 0.00 diff (08-19 weekly) confirms the two sides agree perfectly
when the market genuinely didn't move in the 15:28→15:36 window. This matches hypothesis (a) —
ordinary last-minute intraday price drift between the last live tick and the EOD read — not
(b), a real computation/staleness bug. Per the "Next step" exit criteria above, this would
normally mean removing the diagnostic; **Animesh's call (2026-08-24): leave it running longer**
rather than closing/removing now. `docs/bugs/task.md`'s BUG-019 section moved to the bottom of
the file (still open, deliberately deprioritized below BUG-030/031) so the session-start
protocol doesn't pick B019.1 up next.

**Related:** BUG-018 (the specific case that prompted this generalisation).

---

## BUG-030 — `_overlay_type_groups()` elif-precedence drops an `overlay_cc` leg whenever an `overlay_collar_put` leg is also present same-day; corrupts the Collar P&L figure and produces a false "CC No data" line in the recovery digest

| Field | Value |
|---|---|
| Severity | **HIGH** — live P&L-correctness defect, not just a reporting gap. Silently drops a real, open leg's P&L (`overlay_cc`, +₹53.625 on 2026-08-13) from both `paper_overlay_pnl_snapshots` and the daily "NiftyBees vs overlays" Telegram digest, and folds a mislabeled result into the `collar` row instead — the displayed Collar P&L (-₹973) is understated by the missing call leg's contribution (true value -₹919.75). No exception, no warning specific to this combination — same silent-failure shape as BUG-026/027/028. |
| Status | ✅ Fixed — SHA 86db6a2 (2026-08-24). B030.4 (backfill/discontinuity note for 08-12/08-13 rows) remains open separately. |
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

**Implementation progress (2026-08-24, SHA `86db6a2`):** B030.1's entry-side question resolved by direct code inspection, not a council checkpoint — `build_overlay_trades()`/`_record_collar_trades()` in `paper_3track_overlay_entry.py` already contain a deliberate, documented dedup guard: when a collar entry is submitted and an `overlay_cc` short call is already open on the same instrument key, the code intentionally skips inserting a second `overlay_collar_call` leg ("the existing CC serves as the collar call... recording a second SELL on the same contract would double-count the short position"). `_validate_collar_pairs()` and `_query_open_call_role()` implement the same convention on the validation side (`test_put_only_exempt_when_existing_cc_covers_call`). So the `overlay_cc` + `overlay_collar_put` combination is the intended tagging, not a mistagging — converting the call leg's role at entry would be wrong. The fix was purely reporting-side: added an explicit `has_cc and has_put` branch to `_overlay_type_groups()` that merges `overlay_cc` + `overlay_collar_put` into the `collar` group, matching the entry-side semantics, ordered before the existing `has_put`-only branch so it doesn't regress the collar-call-rolled-off warning path. Updated the grouping-convention comment block above `_OVERLAY_ROLES` to document the new combination.

Tests added (`tests/unit/scripts/test_paper_3track_overlay_pnl.py`): 6 unit tests on `_overlay_type_groups()` covering all 5 reachable leg-role combinations (including the BUG-030 regression case) plus pp-independence; 1 end-to-end test on `_compute_overlay_pnl_snapshots()` reproducing the live 2026-08-13 figures (+53.625 cc / -973.375 put → merged collar row, no separate cc row). All 14 tests in the file pass. Self-reviewed against `REVIEW.md` in lieu of a real `code-reviewer` subagent (not available in this environment) — ruff and `py_compile` clean, one line-length violation (G2, >80 chars) caught and fixed before commit.

---

## BUG-031 — `CCOverlayV1`/`PPOverlayV1`/`CollarOverlayV1` filter positions by their own pre-S2r `strategy_name` constants, not `STRATEGY_OVERLAY` — every auto-entered CC/PP/Collar leg has had zero live exit-signal coverage since S2r shipped (2026-07-29)

| Field | Value |
|---|---|
| Severity | **CRITICAL** — not a reporting gap like BUG-028/030, a risk-management gap on live (paper) capital. No delta-stop, premium-stop, profit-target, time-stop, or DTE-triggered roll signal has ever fired for any CC/PP/Collar overlay leg opened by the auto-entry crons, for the full three weeks since S2r shipped. Positions silently accumulate with nothing watching them; the only reason this surfaced is a human noticing a duplicate entry, not any alert. |
| Status | 🔴 Open — found 2026-08-20, not yet fixed (fix scoped, pending go-ahead per Animesh). |
| Discovered | 2026-08-20, Animesh — while investigating why `paper_3track_overlay_entry.py --auto-pp` entered a second `overlay_pp` put (`NSE_FO|74009`) on top of a still-open one (`NSE_FO|61604`, opened 2026-08-11). Root-caused across several steps in the same session: (1) confirmed via `logs/cron.log` that `--auto-pp`'s cwd/`--db-path` were correct, ruling out a path mismatch; (2) confirmed via `logs/base_roll.log`/`futures_entry.log`/`ditm_entry.log` that no concurrent 10:30 cron job wrote to `portfolio.sqlite` today, ruling out lock contention; (3) confirmed via the `overlay_pp` DTE decay in `logs/pp_entry.log` (13→12→11→8→7→6 on 2026-08-11→08-19) that 2026-08-20 was exactly the day DTE hit `_PP_ROLL_DTE_THRESHOLD=5` — today's fresh-put entry was the *correct, scheduled* routine-roll trigger, not a bug; (4) that meant the real defect had to be on the **close side** of the roll — the outgoing `NSE_FO|61604` leg was never closed by the live monitor; (5) `grep -c "overlay_pp" logs/monitor_daemon.log` returned `0` — the string never appears in that log's entire history, despite `PPOverlayV1` being registered every single day (confirmed at `09:15:07` today via `MONITOR_OVERLAYS=1 — registering overlay strategies` / `Registered overlay strategy name=PPOverlayV1`, and on 08-14/08-17/08-18/08-19 in the same log); (6) traced to `PPOverlayV1.strategy_name = STRATEGY_PP_OVERLAY = "paper_protective_put_v1"` filtering `pos.strategy_name != self.strategy_name`, while `auto_pp_bootstrap()` writes every `overlay_pp` trade under `STRATEGY_OVERLAY = "paper_nifty_overlay"` — confirmed via direct DB query that `paper_trades` has **zero rows, ever**, under `paper_protective_put_v1`. |
| Location | `src/strategy/pp_overlay_v1.py:60` (`strategy_name: str = STRATEGY_PP_OVERLAY`), `src/strategy/cc_overlay_v1.py:60` (`strategy_name: str = STRATEGY_CC_OVERLAY`), `src/strategy/collar_overlay_v1.py:76` (`strategy_name: str = STRATEGY_COLLAR_OVERLAY`) — all three filter open positions/legs against `self.strategy_name` throughout (`pp_overlay_v1.py:136`, `cc_overlay_v1.py:121`/`198`, `collar_overlay_v1.py:145`/`155`/`355`, plus each class's `apply_action` leg-resolution paths). Contrast with `src/paper/constants.py:26-28` (`STRATEGY_CC_OVERLAY = "paper_covered_call_v1"`, `STRATEGY_PP_OVERLAY = "paper_protective_put_v1"`, `STRATEGY_COLLAR_OVERLAY = "paper_collar_v1"`) vs. `src/paper/constants.py:36` (`STRATEGY_OVERLAY = "paper_nifty_overlay"` — the namespace `scripts/strategies/three_track/paper_3track_overlay_entry.py`'s `auto_cc_bootstrap`/`auto_pp_bootstrap`/`auto_collar_bootstrap` actually write trades under). Registration site: `scripts/monitor_daemon.py:335-360` (`MONITOR_OVERLAYS` env-gated block instantiating all three classes and appending them to `StrategyMonitor`'s `strategies` list). |

**Symptom, confirmed via direct queries (not inferred):**
- `SELECT strategy_name, COUNT(*) FROM paper_trades GROUP BY strategy_name` → the full distinct set is `paper_csp_nifty_v1`, `paper_ic_nifty_v1_leaps/monthly/weekly`, `paper_ic_nifty_v2_monthly`, `paper_nifty_futures`, `paper_nifty_overlay`, `paper_nifty_proxy`, `paper_nifty_spot`. `paper_protective_put_v1`, `paper_covered_call_v1`, and `paper_collar_v1` — the three namespaces `PPOverlayV1`/`CCOverlayV1`/`CollarOverlayV1` actually watch — have **zero rows, ever**.
- `SELECT leg_name, COUNT(*) FROM paper_exit_events WHERE leg_name LIKE 'overlay_%' GROUP BY leg_name` → empty result set. No `overlay_pp`/`overlay_cc`/`overlay_collar_call`/`overlay_collar_put` exit event has ever been recorded, for any leg, on any date.
- `grep -c "overlay_pp" logs/monitor_daemon.log` → `0`, across the log's entire retained history, despite `PPOverlayV1` being confirmed-registered on every checked day (08-14, 08-17 [13:55, an off-schedule restart], 08-18, 08-19, 08-20).
- Live consequence, today: `overlay_pp` leg `id=168` (`NSE_FO|61604`, BUY 65, opened 2026-08-11, `state='OPEN'`) sat unmonitored for 9 days while its DTE decayed from 14 to 5; when the entry-side cron correctly triggered a same-day routine roll (per `_open_pp_dte`'s design — see `TODOS.md` 2026-08-20 / `DECISIONS.md` 2026-08-20 for that half of today's investigation), the outgoing leg was never closed because nothing evaluates `ROLL_ELIGIBLE`/executes `ROLL_PP` against it. `portfolio.sqlite` now has two simultaneously-`OPEN` `overlay_pp` rows (`id=168` and `id=204`, `NSE_FO|74009`, today), with the same underlying gap meaning neither will ever auto-close.

**Root cause:** S2r (2026-07-29, `DECISIONS.md` same date, "Track-ownership overlay blocks removed") made overlay entry track-independent by deliberate design — `paper_3track_overlay_entry.py`'s `auto_cc_bootstrap`/`auto_pp_bootstrap`/`auto_collar_bootstrap` all write trades under the single shared `STRATEGY_OVERLAY` namespace instead of under whichever 3-track base (`paper_nifty_spot`/`futures`/`proxy`) they're conceptually attached to. **BUG-028** (root cause same date, fixed 2026-08-10) already found and fixed one consumer that this change broke: the P&L reporting pipeline (`track_snapshot.py::generate_track_snapshot()`, `paper_3track_snapshot.py::_compute_overlay_pnl_snapshots()`, the recovery digest) was still querying by track namespace and silently reported "P&L is zero" for every post-S2r overlay leg instead of "data is missing." BUG-028's three phases repointed that pipeline at `STRATEGY_OVERLAY`.

But `CCOverlayV1`/`PPOverlayV1`/`CollarOverlayV1` — the classes `StrategyMonitor` actually ticks to *evaluate exit signals and execute closes/rolls* (a completely different consumer from the reporting pipeline BUG-028 touched) — were never part of BUG-028's fix scope, and no other bug entry references them: grepped both `docs/bugs/bugs.md` and `docs/archive/bugs/bugs.md` for `cc_overlay_v1`/`pp_overlay_v1`/`collar_overlay_v1` — the only hit is an unrelated, already-fixed BOD-strike-parsing regex bug (2026-07-06 entry, archived) that explicitly flagged-but-deferred these three files' `strategy_name`/namespace question as a "not fixed, follow-up" item and it was never picked back up. Each class still carries its own pre-S2r dedicated `strategy_name` constant and has never been updated to match where the entry script actually files trades — so `StrategyMonitor`'s tick loop calls `check_signals()` on all three every poll interval, each one queries/filters against a namespace with zero trades, finds nothing, and silently does nothing. No exception anywhere in this chain — same "zero found read as legitimately flat" failure shape as BUG-026/027/028/030, just in the live-execution path instead of a reporting path.

**One nuance worth resolving before patching (mirrors BUG-030's entry-side/reporting-side split):** `STRATEGY_CC_OVERLAY` is not universally dead code — `scripts/strategies/cc_calibration/paper_cc_entry.py`/`paper_cc_roll.py` (an older, separate manual CLI tool, `leg_role="covered_call"` not `overlay_cc`) also reference it as their position-storage namespace, and `paper_3track_overlay_entry.py` itself uses all three constants (`STRATEGY_CC_OVERLAY`/`STRATEGY_PP_OVERLAY`/`STRATEGY_COLLAR_OVERLAY`) as informational `GateViolation.strategy_name` tags (`paper_3track_overlay_entry.py:316`/`480`/`789`) — those are gate-violation labels, not position-storage reads, and are not part of this defect. Confirmed via direct query that `paper_covered_call_v1`/`paper_protective_put_v1`/`paper_collar_v1` have zero trades regardless of `leg_role`, so the `cc_calibration` tool's namespace is also empty in practice today — but the fix needs to grep every reference to these three constants (not just the three `strategy_name: str = ...` class attributes) before repointing them, so it doesn't silently break the calibration tool's own (currently dormant but not deleted) code path.

**Impact:** every CC/PP/Collar overlay leg opened by the auto-entry crons since 2026-07-29 (three weeks of trading days at the time of discovery) has had no live exit-signal coverage whatsoever — no delta-stop, premium-stop, profit-target, time-stop, or DTE-roll has ever been evaluated or executed for any of them via `StrategyMonitor`. This is broader than the `overlay_pp` duplicate that surfaced it — every open CC and Collar leg needs the same manual exit-eligibility review, not just PP.

**Suggested fix:** repoint `strategy_name` on all three classes (`cc_overlay_v1.py:60`, `pp_overlay_v1.py:60`, `collar_overlay_v1.py:76`) to `STRATEGY_OVERLAY`, matching where `paper_3track_overlay_entry.py` actually writes and matching the direction BUG-028 already resolved for the reporting side of this same S2r change. Before patching: (a) grep every reference to `STRATEGY_CC_OVERLAY`/`STRATEGY_PP_OVERLAY`/`STRATEGY_COLLAR_OVERLAY` (not just the class attributes) and confirm the `cc_calibration/` tool and the `GateViolation` tagging call sites are unaffected or are deliberately updated too; (b) test coverage needs to be end-to-end (a CC/PP/Collar position opened under `STRATEGY_OVERLAY` gets picked up by a `StrategyMonitor` tick and evaluated for exit signals), not just a unit-level `strategy_name` equality assertion — that's exactly the class of gap that let this ship unnoticed; (c) given this governs live-capital-adjacent auto-execution (`MONETIZE_PP`, `ROLL_PP`, `CLOSE_CC`, `CLOSE_AND_REENTER_COLLAR`), this should get the same council-checkpoint treatment BUG-028/BUG-030 flagged for changes of this shape (`docs/council/README.md`'s three-condition check). Separately, immediate manual action independent of the code fix: review every currently-open CC/PP/Collar leg for exit-eligibility by hand, since nothing has been doing it automatically.

**Related:** BUG-028 (same root cause — S2r, 2026-07-29 — this is the un-remediated second half: live-monitor exit-signal classes vs. the reporting pipeline BUG-028 fixed); BUG-030 (same overlay-reporting file/pipeline as BUG-028, a different defect); `TODOS.md` 2026-08-20 entry (the `overlay_pp` duplicate-entry symptom that led to this discovery) and its companion `DECISIONS.md` 2026-08-20 entry (the entry-gate fail-safe fix, which is correct and complete on its own but does not address this).

---
