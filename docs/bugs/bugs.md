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

## BUG-032 — `get_position()`'s ambiguous-match fallback silently drops one leg's P&L from the overlay book whenever a role has two open positions — `overlay_pp`'s daily snapshot has excluded the older `NSE_FO|61604` leg's unrealized P&L since 2026-08-20

| Field | Value |
|---|---|
| Severity | **CRITICAL** — live (paper) daily P&L understatement, not a reporting-format gap. `_compute_overlay_leg_totals()` and `_leg_entry_basis()`/`_position_qty()` in `paper_3track_snapshot.py` all call `PaperStore.get_position(strategy_name, leg_role)` with no `instrument_key`; per `get_position`'s own PG-2a ambiguous-match resolution (`src/paper/store.py:844-908`), when more than one position shares a `leg_role` it silently picks the single position with the most recent `entry_date` and logs a WARNING — the *other* open position's P&L is dropped from the aggregate entirely, not merged, not double-counted, just gone. This has been live since the 2026-08-20 `overlay_pp` duplicate-entry event BUG-031 documents (old `NSE_FO|61604` leg, opened 2026-08-11, was never closed; a second `NSE_FO|74009` leg opened 2026-08-20/21 under the same `overlay_pp` role). |
| Status | 🔴 Open — found 2026-08-24, not yet fixed. |
| Discovered | 2026-08-24, during the BUG-030 B030.4 backfill: recomputing `overlay_pp`'s historical P&L with `_compute_overlay_pnl_snapshots()` logged `paper_store.get_position_ambiguous leg_role=overlay_pp match_count=2` on every call. Traced live against `data/portfolio/portfolio.sqlite`: `paper_trades` has two open, never-closed `overlay_pp` legs — `NSE_FO|61604` (BUY 65 @ 58.85, 2026-08-11) and `NSE_FO|74009` (BUY 65 @ 94.20 on 08-20, BUY 65 @ 91.80 on 08-21, net 130 lots). Confirmed by reconstructing `paper_leg_snapshots` figures by hand: the 2026-08-21 row (`total_pnl = -65.00`, `ltp = 92.5`) matches `(92.5 - 93.0) * 130` exactly — the weighted-avg-cost and net_qty of `NSE_FO|74009` *alone*, with `NSE_FO|61604`'s 65 lots contributing nothing. Every `overlay_pp` snapshot from 2026-08-20 onward shows the same pattern: the row jumps from tracking the single pre-08-20 leg to tracking only the newer leg, with a step discontinuity in `ltp`/`total_pnl` right at the duplicate-entry date that has no market-move explanation. |
| Location | `scripts/strategies/three_track/paper_3track_snapshot.py`: `_compute_overlay_leg_totals()` (~line 1240-1303, the daily cron snapshot writer — the primary live-impact site), `_leg_entry_basis()` (~line 1136-1149) and `_position_qty()` (~line 1373-1376, both feed `_compute_overlay_pnl_snapshots()`'s %-denominators). Root mechanism: `PaperStore.get_position()` (`src/paper/store.py:844-908`). |

**Symptom:** since 2026-08-20, the daily `overlay_pp` leg snapshot (`paper_leg_snapshots`, `strategy_name=paper_nifty_overlay`, `leg_role=overlay_pp`) and every downstream `overlay_pp`/`pp` P&L row derived from it reflects *only* the newer `NSE_FO|74009` position. The older `NSE_FO|61604` position (65 lots, still open per the trade ledger, no `SELL` ever recorded against it) contributes zero to `unrealized_pnl`, `total_pnl`, or the entry-basis/quantity used for `pnl_inception_pct`/`pnl_1d_pct` — its LTP isn't even fetched (`_compute_overlay_leg_totals`'s `open_keys` list only includes the instrument_key `get_position` happened to return). This is a live understatement of the reported overlay book P&L that has been running for every cron tick since 2026-08-20 (4+ trading days as of discovery), not a one-time historical artifact.

**Root cause:** `get_position(strategy_name, leg_role)` was designed for the case where a role transitions cleanly from one instrument to the next (PG-2a's "roll overlap" comment) and, lacking an `instrument_key` to disambiguate, falls back to "most recent `entry_date` wins" with a WARNING log as the only signal. `_compute_overlay_leg_totals()`, `_leg_entry_basis()`, and `_position_qty()` all call it role-only, never per-instrument — they were written assuming (correctly, until BUG-031's underlying condition) exactly one open position per overlay role at a time. BUG-031 is *why* two positions are simultaneously open (the live monitor never saw `STRATEGY_OVERLAY` positions to close the old leg on roll) — this bug is a distinct, *downstream* defect: even once BUG-031 is fixed and future rolls close old legs promptly, this reporting-layer gap remains latent and will silently reproduce the same P&L drop the next time any overlay role legitimately has two open positions even briefly (e.g. a same-day roll that closes-then-reopens isn't atomic at the snapshot-cron's granularity). The per-role (not per-instrument) shape of `paper_leg_snapshots` and `_OVERLAY_ROLES` more broadly assumes single-position-per-role throughout this file, which this bug is the first confirmed case of that assumption breaking in production.

**Suggested fix:** not yet scoped in detail — needs a decision before implementation, mirroring BUG-030's B030.1 pattern:
- Option (a): change `_compute_overlay_leg_totals()`/`_leg_entry_basis()`/`_position_qty()` to sum across *all* open positions matching a `leg_role` (via `store.get_positions()` filtered by role, not `get_position()`'s single-match API) — correct for the "role can legitimately hold >1 open instrument" case, but changes the shape of `paper_leg_snapshots` from one-row-per-role to needing either a wider aggregate or a schema change to key by `(leg_role, instrument_key)`.
- Option (b): treat >1 open position under one overlay role as a hard error / `GateViolation` at the cron level (fail loud, matching REVIEW.md's "don't return None to signal failure" spirit) rather than silently aggregating or dropping — forces the duplicate to be resolved (manually or via BUG-031's fix) before P&L reporting continues, at the cost of the daily snapshot going missing entirely until resolved.
- Either way: a regression test simulating two open positions under one `leg_role` and asserting the resulting P&L reflects *both* (option a) or refuses to silently proceed (option b) — the current test suite has no coverage of `get_position`'s ambiguous-match branch being exercised from the overlay P&L path at all, which is exactly the class of gap that let this ship unnoticed for 4+ days.
- Given this touches live overlay P&L reporting (same shape as BUG-028/BUG-030), likely qualifies for the same council-checkpoint bar (`docs/council/README.md`'s three-condition check).

**Related:** BUG-031 (root cause of *why* two `overlay_pp` positions are simultaneously open — this bug is the downstream reporting-layer consequence, distinct and independently fixable); BUG-030 (same overlay-reporting file/pipeline, different defect — leg-role grouping vs. position resolution); discovered as a side effect of BUG-030's B030.4 backfill (`docs/archive/bugs/bugs.md`).

---
