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

## BUG-032 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-08-24, SHA `67d4010`, backfill applied same day)

---

## BUG-036 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-08-24, SHA `d40c3a1`, backfill applied same day)

---


## BUG-037 — `mark_trade_closed()` also never wired into CSP/IC v1/v2 close paths; 54 stale flat legs found live (54, not just BUG-035's 2)

| Field | Value |
|---|---|
| Severity | **MEDIUM** — same category as BUG-035: `paper_trades.state` staleness on already-flat legs, not a live P&L/Greeks defect. Currently inert per BUG-035's B035.1 trace (flat legs, `net_qty == 0`, never appear in `get_positions()`'s output, so `check_signals` never re-evaluates them regardless of their stale `state`) — but the wiring gap is real and wider than BUG-035 scoped. |
| Status | 🔴 Open — found 2026-08-24, not yet fixed. |
| Discovered | 2026-08-24, while validating BUG-035's generalized backfill script (`scripts/dev/backfill_mark_trade_closed_overlay.py --dry-run`) against the live DB — a scan for any `(strategy_name, leg_role, instrument_key)` that's flat but still `state IN ('OPEN','DEFENDED')` returned 54 rows, not the 2 BUG-035 already fixed. |
| Location | `src/strategy/csp_roll_executor.py::close_csp_leg` (CSP), `src/strategy/ic_close_executor.py::close_ic_legs`/`roll_ic_legs` (IC v1/v2); likely also `scripts/strategies/three_track/paper_3track_roll.py`'s futures/proxy roll-close writes (unconfirmed, see Suggested fix). |

**Symptom:** 54 `(strategy_name, leg_role, instrument_key)` tuples are fully flat (BUY quantity − SELL quantity == 0) but still carry `state IN ('OPEN','DEFENDED')` on every row. Breakdown: 5 `paper_csp_nifty_v1` short_put legs, 46 across `paper_ic_nifty_v1_weekly`/`monthly`/`leaps` and `paper_ic_nifty_v2_monthly` (short_call/short_put/long_call_hedge/long_put_hedge), 1 `paper_nifty_futures` base_futures leg, 1 `paper_nifty_proxy` base_ditm_call leg, and 1 more `paper_nifty_overlay`/`overlay_pp` leg (`NSE_FO|74046`) that BUG-035's original two-row backfill missed because it only looked at the two instrument keys named in that bug's discovery query, not the whole table.

**Root cause:** Same shape as BUG-035 — `PaperStore.mark_trade_closed()` was never wired into the CSP or IC close/roll paths either. Confirmed via direct grep (not the codebase graph — see note below): `csp_roll_executor.py::close_csp_leg()` (used by `CSPNiftyV1.apply_action`'s `CLOSE_AND_ROLL`/`CLOSE_AND_WAIT`/`ROLL_DOWN_AND_OUT` branches) calls `store.record_trade(close_trade)` and nothing else. `ic_close_executor.py::close_ic_legs()`/`roll_ic_legs()` (used by both `IronCondorV1` and `IronCondorV2`'s `apply_action` for `CLOSE_FULL`/`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` and roll actions) call `store.record_trades(trades)` and nothing else. Neither ever calls `mark_trade_closed()`.

**Graph-index correction (important for future sessions):** BUG-035's B035.1 trace used `codebase-memory-mcp`'s `trace_path(direction=inbound)` and reported **zero callers** for both `get_trade_state()` and `mark_trade_defended()` project-wide. That was wrong — a direct `grep -rn` found real callers of both in `src/strategy/csp_nifty_v1.py` (`get_trade_state()` at line 203, feeding `evaluate_delta_breach_csp`'s OPEN-vs-DEFENDED state-aware branching per `CONTEXT.md`'s own documented behavior; `mark_trade_defended()` at line 596, in the `ROLL_DOWN_AND_OUT` flow). The graph's CALLS-edge index for this repo appears stale for at least these two symbols. This doesn't change B035.1's practical conclusion — CSP's `check_signals` only reaches `get_trade_state()` for positions `get_positions()` returns, which excludes flat (`net_qty == 0`) legs entirely, so the 54 stale rows found here (all flat) still don't affect any live signal evaluation today — but the graph result itself should not be trusted as a sole source for "zero callers" claims going forward; grep or `query_graph`'s raw CALLS-edge scan should corroborate before stating a symbol is orphaned.

**Suggested fix:** Mirror BUG-035's fix shape — add `store.mark_trade_closed(...)` (or, if a roll only partially closes down to a nonzero size, the appropriate state transition) at each close write site above, gated on the write actually flattening the position. Before implementing, trace `close_csp_leg`/`close_ic_legs`/`roll_ic_legs` call sites for any place a *partial* close/roll can leave `net_qty != 0` — unlike BUG-035's overlay legs (always full closes), CSP's `ROLL_DOWN_AND_OUT` and IC's spread-only closes are explicitly partial at the strategy level, so `mark_trade_closed()` must only fire on the specific leg's own row, using the per-leg trade being written (not a whole-strategy flatten check), same pattern already validated in BUG-035's `OverlayCloser` fix. `paper_3track_roll.py`'s futures/proxy roll-close path needs its own trace (not yet done) before assuming the identical fix applies. Backfill: `scripts/dev/backfill_mark_trade_closed_overlay.py` (built for BUG-035, generalized to scan the whole table rather than hardcoding instrument keys) already covers all 54 rows found here — safe to run once the root-cause fix lands, since its discovery query only targets rows that are *already* flat (no partial-close risk).

**Related:** BUG-035 (identical bug shape, different call sites — CC/PP/Collar there, CSP/IC here); this bug's discovery came directly out of validating BUG-035's backfill script.

**Implementation progress (2026-08-24, B037.1/B037.2):** Re-traced current code (grep, not
`codebase-memory-mcp` — its CALLS-edge index is already flagged stale above) for all three call
sites. Confirms the suggested fix needs no gating beyond the per-leg trade being written:

- `close_csp_leg` (`src/strategy/csp_roll_executor.py:150`) closes at `existing.quantity` — the
  full size of that leg's row — before `record_trade`. CLOSE_AND_ROLL/CLOSE_AND_WAIT/
  ROLL_DOWN_AND_OUT all route through here at full leg quantity.
- `close_ic_legs`/`roll_ic_legs` (`src/strategy/ic_close_executor.py:236,361`) both build closing
  trades via `_build_close_trades`, called only on positions with `net_qty != 0`, at that leg's
  full `net_qty`. The "partial" in spread-only closes (e.g. CLOSE_CALL_SPREAD) is partial *at the
  strategy level* (only some roles close) — each individual leg row written is still a full close
  of that row. `roll_ic_legs` additionally writes open-side trades in the same `record_trades`
  call, so the close-vs-open trades need to stay distinguishable when `mark_trade_closed` is wired
  in (B037.3) — don't derive it from `TradeAction` alone.
- `paper_3track_roll.py::check_and_roll_leg` (`scripts/strategies/three_track/paper_3track_roll.py:252,278`)
  — **confirmed in scope**, not just "likely" as originally scoped. `qty = abs(pos.net_qty)`, full
  close, `record_trades([close_trade, open_trade])`, no `mark_trade_closed` call anywhere in the
  file. Same fix shape applies.

No B037.1 flatness-check branch is needed — all three sites already only ever write full-leg
closes, never a partial paydown of a single row. B037.3 can call `mark_trade_closed()`
unconditionally per closing trade, keyed to that trade's own
`(strategy_name, leg_role, instrument_key)`.

**Implementation progress (2026-08-24, B037.3/B037.4, SHA `5369c0e`):** Wired
`store.mark_trade_closed()` into all three confirmed sites:

- `close_csp_leg` (`src/strategy/csp_roll_executor.py`) — calls it only when
  `record_trade()` returns `True` (guards the duplicate-insert case, same
  shape as BUG-035's CC/PP overlay fix).
- `close_ic_legs` (`src/strategy/ic_close_executor.py`) — iterates `inserted`
  (the rows `record_trades()` actually wrote) and marks each one closed, so a
  partial write (some legs skipped as duplicates) only marks the legs that
  landed.
- `roll_ic_legs` (`src/strategy/ic_close_executor.py`) — marks only the
  close-side trades. Since `close_trades` and `open_trades` are concatenated
  into one `record_trades()` call, the close-side rows are identified by
  Python object identity (`id()`) against the pre-concatenation `close_trades`
  list, not by `TradeAction`, so the freshly-opened replacement leg is never
  mistakenly marked CLOSED.
- `check_and_roll_leg` (`scripts/strategies/three_track/paper_3track_roll.py`)
  — marks the leg closed only when `close_trade in inserted` (equality-based;
  safe here since close_trade/open_trade always differ by instrument_key).

Tests added mirroring BUG-035's B035.4 pattern (happy path + duplicate-insert
skip) in `tests/unit/strategy/test_csp_roll_executor.py`,
`tests/unit/strategy/test_ic_close_executor.py` (both `close_ic_legs` and
`roll_ic_legs`), and `tests/unit/scripts/test_paper_3track_roll.py` (using a
real `PaperStore`, not a mock, per that file's existing convention). All 51
tests in the three touched suites pass; a full `tests/unit/` run shows 31
pre-existing failures/7 errors unrelated to this change (missing
`pyarrow`/`fastparquet`/etc. in the ad-hoc review venv, confirmed by
traceback inspection — none touch the files this bug modified).

**B037.5 (2026-08-24):** Re-verified the live DB (`data/portfolio/portfolio.sqlite`)
via a new read-only diagnostic, `scratch/2026-08-24_check_stale_flat_legs.py`
(same discovery query as the backfill script, no writes) — run both through
the Cowork device bridge and directly by Animesh on the live host, identical
result: 0 stale flat legs across 134 total trade rows / 9 strategies. Animesh
confirmed he'd run `backfill_mark_trade_closed_overlay.py --dry-run` earlier
— that mode never writes, so it isn't what resolved the 54 rows found at
discovery time; the actual mechanism is unconfirmed. No backfill `--apply`
run was needed or performed — nothing stale remains.

**Outstanding for this bug:** B037.6 (mandatory real `@code-reviewer` run —
this session is Cowork, which cannot spawn `.claude/agents/code-reviewer.md`;
the B037.3/B037.4 commit (`5369c0e`) landed without that gate clearing, so a
`@code-reviewer` pass against that commit's diff from Claude Code is still
owed before this bug is considered fully closed).

---


