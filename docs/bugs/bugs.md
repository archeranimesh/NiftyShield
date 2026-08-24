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

## BUG-036 — `_compute_overlay_pnl_snapshots`'s `prev_mark_value` blends today's live quantity with yesterday's LTP, understating/overstating `pnl_1d_pct`'s denominator

| Field | Value |
|---|---|
| Severity | **MEDIUM** — display/percentage-only defect. `pnl_1d_abs`/`total_pnl` (the absolute rupee figures) are computed additively and are unaffected; only `pnl_1d_pct`'s denominator is wrong, and only on days quantity changed since the prior snapshot. Pre-existing, not introduced by BUG-032's fix — merely surfaced by that fix's code review. |
| Status | ✅ Fixed — 2026-08-24, SHA `SHA pending — sandbox .git/index.lock held by a concurrent process, commit deferred to live host`. Symptom (2) (day-over-day quantity mismatch) fixed. Symptom (1) (multi-instrument NULL ltp) remains open — needs the per-instrument companion table the BUG-032 council ruling explicitly deferred. |
| Discovered | 2026-08-24, during the mandatory code-reviewer pass on the BUG-032 fix (`docs/bugs/task.md` B032.5). |
| Location | `scripts/strategies/three_track/paper_3track_snapshot.py::_compute_overlay_pnl_snapshots`, the `prev_mark_value` computation (search `BUG-036` — comment added in place). Feeds off `_position_qty()`, which by design returns *today's* live net quantity. |

**Symptom:** `prev_mark_value = Σ_r _mark_value(prev_by_role[r].ltp, _position_qty(store, STRATEGY_OVERLAY, r))` pairs yesterday's snapshot's `ltp` with today's current `_position_qty()` — not the quantity that was actually open as of that prior snapshot's date. Two distinct manifestations: (1) when yesterday's snapshot was a BUG-032 multi-instrument aggregate, `prev_by_role[r].ltp` is `NULL` by design, so that role contributes `0` to the denominator for one day (understates `pnl_1d_pct`'s denominator); (2) in the ordinary single-instrument case, if quantity changed between yesterday and today (a partial close or add), the denominator blends today's size with yesterday's price — an apples-to-oranges figure with no correctness guard, either direction.

**Root cause:** `PaperStore` does not retain historical per-day open quantity — `paper_leg_snapshots` stores P&L and `ltp` but not `net_qty` — so `_position_qty()` (necessarily) can only report the *current* quantity, and this call site was written assuming quantity is stable day-over-day, which is not guaranteed for any role that can partially close/add (all overlay roles, by design).

**Suggested fix:** Implemented (2026-08-24) — added `net_qty: int | None` to `PaperLegSnapshot`/`paper_leg_snapshots` (schema addition via the file's existing idempotent `ALTER TABLE ... ADD COLUMN` migration pattern, not a re-key — orthogonal to the BUG-032 council ruling's rejection of instrument-keying).

**Implementation progress (2026-08-24):**
- `src/paper/models.py`: `PaperLegSnapshot.net_qty: int | None = None` — `None` means "unknown, pre-fix/pre-backfill row", never conflated with `0` (a valid flat position).
- `src/paper/store.py`: idempotent migration `ALTER TABLE paper_leg_snapshots ADD COLUMN net_qty INTEGER DEFAULT NULL`; `record_leg_snapshot` INSERT/UPSERT, `_row_to_leg_snapshot`, `get_leg_snapshot`, `get_prev_leg_snapshot` all carry `net_qty` through.
- `scripts/strategies/three_track/paper_3track_snapshot.py`: every leg-snapshot write site now populates `net_qty` (`_save_leg_snapshots` for the base leg; `_compute_overlay_leg_totals`'s n==0/n==1/n>1 branches for overlay legs, summing net_qty across instruments in the multi-instrument case — same "sum independently, never blend" discipline as BUG-032's P&L aggregation). `_compute_overlay_leg_totals`'s return tuple grew from 4 to 5 elements; every unpacking call site updated (`_save_overlay_leg_snapshots`, `_overlay_summary_row`'s type sig, the dry-run print loop in `_run`, and two existing tests in `tests/unit/paper/test_paper_3track_snapshot.py`). `_compute_overlay_pnl_snapshots`'s `prev_mark_value` now uses `prev_by_role[r].net_qty` (the quantity actually open on the prior snapshot date) instead of `_position_qty()` (today's live quantity), falling back to the old behavior only when `net_qty is None` (not-yet-backfilled legacy rows).
- `scripts/dev/backfill_leg_snapshot_net_qty.py` (new): one-off script reconstructing `net_qty` for the pre-fix rows from `paper_trades` (`SUM(BUY qty) - SUM(SELL qty)` bounded by `trade_date <= snapshot_date`, same convention as `PaperStore.get_position`) — writes via `PaperStore.record_leg_snapshot`, never raw SQL, per project convention. Idempotent (`--force` to override), `--dry-run` supported, backs up the DB before writing. **Bug found and fixed post-review (2026-08-24):** the script's `_find_target_rows`/`_net_qty_as_of` opened a raw `sqlite3.connect()` and queried `net_qty` directly, but that column only gets created by `PaperStore.__init__`'s migration — since `backfill()` never constructed a `PaperStore` before its first raw query in the `--dry-run` path, running `--dry-run` first (as intended) failed with `sqlite3.OperationalError: no such column: net_qty`. Fixed by constructing `PaperStore(db_path)` once at the top of `backfill()`, unconditionally, before any raw query. **Run against the live DB by Animesh, 2026-08-24** — dry-run output sanity-checked (correct signs: `overlay_cc` -65 short, `overlay_collar_put` +65 long, `overlay_pp` 0/65/130/195 across size changes, `base_etf` flat 5735 throughout), then executed for real. Confirmed via direct query: 229/229 rows populated, 0 remaining NULL.
- Tests added: `tests/unit/paper/test_store.py` (net_qty round-trip including negative/short values, and legacy-NULL-read distinct from 0); `tests/unit/scripts/test_paper_3track_overlay_pnl.py` (day-over-day quantity-change scenario with a real non-NULL `prev.ltp` — the exact gap B036.3 named, asserting the denominator uses yesterday's quantity (5000) not today's live quantity (2500)); `tests/unit/scripts/test_backfill_leg_snapshot_net_qty.py` (happy path reconstructing two rows' historical qty across a partial close, idempotency-without-`--force`, dry-run-writes-nothing).
- Review: `general-purpose` + `REVIEW.md` substitute (real `code-reviewer` subagent not available on this surface) run against the full diff. One WARNING raised (`_save_leg_snapshots`'s `pos.net_qty if pos else 0` risking None/0 conflation) — investigated and dismissed: `PaperStore.get_position` never returns `None` (always returns a flat-default `PaperPosition` with `net_qty=0`), and the ternary matches an existing idiom already used elsewhere in the same file (line ~1043). No CRITICAL/ERROR findings.
- **Not executed:** the device sandbox this session ran in has no working Python environment (broken venv symlink, disk full, no network for pip) — `pytest` could not be run to confirm the new/modified tests actually pass. Confirmed via `python3 -m py_compile` only (syntax-level). Recommend running `python -m pytest tests/unit/paper/test_store.py tests/unit/paper/test_paper_3track_snapshot.py tests/unit/scripts/test_paper_3track_overlay_pnl.py tests/unit/scripts/test_backfill_leg_snapshot_net_qty.py -q` locally before treating B036.3 as verified green.
- Commit blocked: `.git/index.lock` held by a concurrent process on the sandbox at commit time (permission denied to remove) — per `docs/bugs/prompt.md`'s lock-contention clause, work stopped before `git commit`. All files are written to the working tree and staged for commit once the lock clears.

**Related:** BUG-032 (this bug's `prev_mark_value` call site sits inside BUG-032's fixed block; surfaced during that fix's mandatory code review, not introduced by it).

---

## BUG-035 — `CCOverlayV1._record_close_trade()`/`PPOverlayV1._record_close_trade()` never call `PaperStore.mark_trade_closed()`; every fully-closed overlay leg's opening trade row stays `state='OPEN'` forever

| Field | Value |
|---|---|
| Severity | **HIGH** — not a P&L-value defect (net_qty math is unaffected), but `mark_trade_closed()`'s own docstring says its purpose is to "prevent the position from re-appearing in signal evaluation on the next tick"; if any live code path gates signal evaluation or position listing on `paper_trades.state`, a flat (net-zero) leg with a stale `state='OPEN'` row risks being treated as still-live. Plausibly the same failure shape as BUG-031 (monitor not seeing a leg as closed) — needs tracing before ruling that out. |
| Status | 🔴 Open — found 2026-08-24, not yet fixed. |
| Discovered | 2026-08-24, while investigating BUG-032: querying `paper_trades` for `leg_role='overlay_pp'` showed both `NSE_FO|61604` (BUY 65 @ 58.85 on 2026-08-11, SELL 65 @ 4.85 on 2026-08-24 — net 0) and `NSE_FO|74009` (BUY 65+65 on 08-20/08-21, SELL 130 @ 83.85 on 2026-08-24 — net 0) still showing `state='OPEN'` on every row despite both positions being fully flat. Traced `PaperStore.mark_trade_closed()` (`src/paper/store.py:625-649`) — the only function in the codebase that transitions a trade row to `CLOSED` — via `trace_path(direction=inbound)`: **zero callers** anywhere in `src/` or `scripts/`, only its own unit tests (`tests/unit/paper/test_store.py`) invoke it. Confirmed both overlay close paths independently omit the call: `CCOverlayV1._record_close_trade()` (`src/strategy/cc_overlay_v1.py:292-334`) and `PPOverlayV1._record_close_trade()` (`src/strategy/pp_overlay_v1.py:304-346`) both build a closing `PaperTrade` and call `self._store.record_trade(trade)` — neither ever calls `mark_trade_closed()` afterward, despite `mark_trade_closed()`'s docstring explicitly describing itself as the step that runs "after a close trade has been successfully recorded." `CollarOverlayV1`'s close path not yet checked — likely same pattern, needs confirming. |
| Location | `src/strategy/cc_overlay_v1.py:292-334`, `src/strategy/pp_overlay_v1.py:304-346` (both `_record_close_trade`); `src/paper/store.py:625-649` (`mark_trade_closed`, the orphaned target). |

**Symptom:** every overlay leg (CC/PP, and likely Collar) that gets closed via `apply_action`'s close path leaves its original opening `paper_trades` row permanently `state='OPEN'`, even after a closing SELL/BUY trade brings `net_qty` to 0. `get_positions()`/`get_position()` compute net_qty correctly regardless of `state` (they sum quantities, they don't filter by state), so this has *not* been masking BUG-032's symptom — but anything else in the codebase that filters `paper_trades` or `paper_strategies`-adjacent queries by `state='OPEN'` to decide what's "still open" would see these as live positions indefinitely.

**Root cause:** `mark_trade_closed()` was added (see its docstring/tests) as the intended state-transition step following a successful close-trade write, but was never wired into either overlay strategy's `_record_close_trade()`. The two methods are structurally identical (build `PaperTrade`, call `record_trade()`, log) and both independently missed the same follow-up call — this reads as the call being designed but the integration step dropped, not a logic error within either method.

**Suggested fix:** add `self._store.mark_trade_closed(pos.strategy_name, pos.leg_role, pos.instrument_key)` immediately after the `record_trade(trade)` call in both `_record_close_trade()` methods (and `CollarOverlayV1`'s equivalent, once confirmed). Backfill: the two existing stale rows (`paper_trades` ids 213, 214, `overlay_pp`) need a one-time `mark_trade_closed()` call or equivalent UPDATE once the live DB lock situation allows it — do not hand-edit `state` via raw SQL outside the store method, to keep the state-machine's `WHERE state IN ('OPEN','DEFENDED')` guard as the single source of truth for what's a legal transition. Needs a regression test asserting `_record_close_trade()` results in `state='CLOSED'` on the opening row — current test suite exercises `record_trade()` and `mark_trade_closed()` separately but nothing asserts the two are wired together end-to-end, which is exactly the class of gap that let this ship unnoticed.

**Related:** discovered investigating BUG-032 (`overlay_pp` ambiguous-match); potentially overlaps BUG-031 (live monitor not seeing overlay positions to close) if anything downstream gates on `state` — needs tracing to confirm or rule out before assuming independence.

---

