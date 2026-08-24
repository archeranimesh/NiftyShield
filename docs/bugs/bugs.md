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

## BUG-033 — `CCOverlayV1`/`PPOverlayV1`/`CollarOverlayV1._parse_expiry` is regex-only, never resolves real numeric Upstox instrument keys — every DTE-gated exit signal (`ROLL_ELIGIBLE`/`DTE_REVIEW`) has been dead for every live overlay position since these classes existed

| Field | Value |
|---|---|
| Severity | **CRITICAL** — live (paper) risk-management gap, same class as BUG-031 but on the DTE axis specifically. Delta/premium-based signals (`CRASH_MONETIZE`, `LOSS_STOP`, `PROFIT_TARGET`, `DELTA_STOP`) are unaffected — only DTE-gated signals are dead. Directly time-sensitive: `overlay_pp` leg `NSE_FO|61604` expires **tomorrow (2026-08-25)** and, as of discovery, would get no `ROLL_ELIGIBLE` signal at all. |
| Status | 🟡 Partially fixed (SHA `ef1c341`, 2026-08-24) — B033.1-B033.4 done (code fix + tests + review + manual `NSE_FO|61604` action); B033.5 (close-out, blocked on BUG-034 landing) still open. Found 2026-08-24, during BUG-031's B031.4 manual exit-eligibility review. |
| Discovered | 2026-08-24, Animesh — ran `scratch/2026-08-24_bug031_manual_exit_review.py` (built for BUG-031's B031.4) live against the real broker/DB now that `strategy_name` is fixed (BUG-031, SHA `ea5df81`). Live chain fetch succeeded (2 `upstox.api_call status_code=200` log lines, both expiries), but `check_signals()` reported "No exit signals fired for any open leg" across all 5 open overlay legs — including `NSE_FO|61604`, whose own instrument-master DTE is 1 (expires 2026-08-25), well inside `evaluate_pp`'s `dte <= 5` `ROLL_ELIGIBLE` threshold. Confirmed live via direct call: `PPOverlayV1()._parse_expiry("NSE_FO|61604")` returns `None` — `_EXPIRY_RE` (`r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE\|CE)"`) only matches text-format keys like `NSE_FO|NIFTY29MAY2026PE`, never numeric exchange-token keys like `NSE_FO|61604` (the format Upstox's real BOD data actually uses, confirmed via `data/instruments/NSE.json.gz`). `check_signals()`'s own fallback (`dte = ... if expiry is not None else 9999`) then makes the DTE-gated branch permanently unreachable for any real position. |
| Location | `src/strategy/pp_overlay_v1.py:414-421` (`_parse_expiry`), `src/strategy/cc_overlay_v1.py` (own copy, same pattern, used at line ~129/210/367 call sites), `src/strategy/collar_overlay_v1.py` (own copy, used at line ~180/365). Each file defines its own private `_EXPIRY_RE`/`_parse_expiry` rather than sharing one implementation. |

**Symptom, confirmed via direct call (not inferred):** `PPOverlayV1()._parse_expiry("NSE_FO|61604")` → `None`. `_EXPIRY_RE.search("NSE_FO|61604")` → `None` (no match — the pattern requires an embedded `NIFTY<DD><Mon><YYYY><PE|CE>` substring that numeric exchange-token keys never contain). Live `scratch/2026-08-24_bug031_manual_exit_review.py` run against the real broker/DB (5 open legs, 2 live chain fetches, both `status_code=200`) reported zero signals fired for any leg — a false-negative "everything is fine" result masking that DTE-gated evaluation never runs at all for these positions.

**Root cause:** same bug class explicitly named as already-fixed elsewhere in this repo — TODOS.md's 2026-08-13/2026-08-20 entries describe `_open_pp_dte`'s and `paper_3track_overlay_entry.py`'s "regex-only expiry parser never matched real numeric Upstox instrument keys (same bug class as BUG-018/BUG-012)," fixed there via "regex-first/BOD-fallback resolution mirroring `ic_nifty_v2.py::_parse_expiry`." That fix was scoped to the entry-side script; these three live-monitor strategy classes' own independent `_parse_expiry` copies were never swept into it, despite each class already lazily loading an `InstrumentLookup` (`self._resolve_instrument_lookup()`, used elsewhere in the same files for leg lookup and label formatting) that could resolve exactly this case.

**Impact:** for every currently-open CC/PP/Collar overlay position filed under a real numeric instrument key (all 5 confirmed open legs, per BUG-031's B031.4 review), `ROLL_ELIGIBLE` (PP, DTE ≤ 5) and `DTE_REVIEW`/roll-priority DTE checks (Collar) can never fire, regardless of how close to expiry the position actually is. This was masked until now because BUG-031 meant these classes never evaluated real positions at all — BUG-031's fix (SHA `ea5df81`) surfaced this as the next layer down, exactly as intended by B031.3/B031.4's "test with real data, not a unit-level assertion" approach.

**Suggested fix:** repoint each file's `_parse_expiry` to try the existing regex first, then fall back to `self._resolve_instrument_lookup().get_by_key(instrument_key)`'s `expiry` field (epoch ms → `date`) when the regex misses — mirrors the fix already proven for `_open_pp_dte`/`paper_3track_overlay_entry.py` and for `ic_nifty_v2.py::_parse_expiry`. Given three near-duplicate `_parse_expiry`/`_EXPIRY_RE` copies already exist across these files (a maintenance smell independent of this bug), consider factoring one shared helper in `src/strategy/_price_utils.py` (already imported by all three files for `find_option_leg`) rather than patching three copies in place — but the regex-first/BOD-fallback *behavior* fix should not wait on that refactor decision. Needs regression tests using real numeric instrument keys (not the text-format fixtures the existing unit test suites use) asserting a resolvable near-expiry DTE actually fires `ROLL_ELIGIBLE`/`DTE_REVIEW` — same "test with real data" gap B031.3's note already flagged as the class of thing that let bugs like this ship unnoticed.

**Immediate manual action, independent of the code fix:** `overlay_pp` leg `NSE_FO|61604` expires 2026-08-25 (tomorrow) with no auto-roll signal — Animesh should decide whether to roll/close it by hand before expiry rather than wait for this fix to land. This is in addition to, not a substitute for, BUG-031's still-open B031.4 (general exit-eligibility review) — B031.4 can now be re-run once this bug is fixed to get real DTE-based signal coverage, not just delta/premium coverage. **Closed (B033.4, 2026-08-24):** Animesh closed all `overlay_pp` positions manually ahead of expiry, including `NSE_FO|61604` — no roll executed, position exited flat.

**Related:** BUG-031 (this bug was found *during* B031.4, its manual-review task, and depended on BUG-031's fix landing first to be observable at all — StrategyMonitor never evaluated real positions before that); BUG-032 (same `NSE_FO|61604` leg, different defect — P&L reporting drop vs. dead exit signal); TODOS.md 2026-08-13/2026-08-20 entries and DECISIONS.md same dates (the already-fixed sibling instances of this exact bug class in the entry-side script — this is the live-monitor-side instance that fix never covered). **Superseded in priority by BUG-034** — the leg_role filter that bug describes runs *before* `_parse_expiry` in `check_signals()`, so for PP/CC this bug's DTE-parsing gap has been unreachable/unverified the whole time this session; fix BUG-034 first, then re-verify this one is still live for the legs that survive that filter (Collar is unaffected by BUG-034 and was always independently exposed to this DTE bug).

**Implementation progress (B033.1-B033.3, SHA `ef1c341`, 2026-08-24):** added `resolve_option_expiry(instrument_key, lookup)` as a shared helper in `src/strategy/_price_utils.py` (regex-first, then BOD-JSON fallback via `lookup.get_by_key()` → `src.instruments.lookup.parse_expiry` epoch-ms/str normalization → `date.fromisoformat`), mirroring `ic_nifty_v2.py::_parse_expiry`'s proven BUG-018 fix — went with the shared-helper option per the suggested-fix note rather than patching three copies in place. `CCOverlayV1`/`PPOverlayV1`/`CollarOverlayV1._parse_expiry` now each delegate to it via `resolve_option_expiry(instrument_key, self._resolve_instrument_lookup())`; the three per-file `_EXPIRY_RE` module constants (and now-unused `import re` / `datetime` imports) were removed since nothing else in those files referenced them (confirmed via grep before deleting). Tests added: `tests/unit/strategy/test_price_utils.py` (11 new cases covering symbolic-regex path, numeric-key BOD resolution, epoch-ms expiry field, missing/malformed BOD `expiry` field, key-not-in-BOD, and regex-still-wins-when-both-resolvable) plus one numeric-key + one regex-precedence regression test per strategy class in `test_pp_overlay_v1.py`/`test_cc_overlay_v1.py`/`test_collar_overlay_v1.py`, asserting `ROLL_ELIGIBLE`/`DTE_REVIEW` actually fires end-to-end through `check_signals()` for a real `NSE_FO|61604`-style key. Verified against the live repo state (not a stale clone) with a full `pytest tests/unit/` run: 111/111 pass in the four touched files; the broader ~2800-test suite shows zero regressions attributable to this diff (pre-existing 29 failures — missing VIX data dir, one already-dirty unrelated WIP test file — are identical before/after). Independent `general-purpose`+review-substitute pass (B033.3) flagged one plausible defect (unguarded `lookup.get_by_key()` in the BOD fallback) — verified safe (`InstrumentLookup.get_by_key` is a simple linear scan, can't raise) — and one test-coverage gap (missing/malformed BOD `expiry` field), which was closed with the two additional test cases above. B033.4 (manual `NSE_FO|61604` decision, expires 2026-08-25) and B033.5 (close-out, blocked on BUG-034) remain open.

---

## BUG-034 — `PPOverlayV1.LONG_PUT_ROLES`/`CCOverlayV1.SHORT_CALL_ROLES` are stale pre-S2r role-name sets that never match the real production `leg_role` (`overlay_pp`/`overlay_cc`) — `check_signals()` silently evaluates **zero** real PP/CC positions, independent of BUG-031/BUG-033

| Field | Value |
|---|---|
| Severity | **CRITICAL — more severe than BUG-033, and the actual primary blocker.** `check_signals()` filters `if pos.leg_role not in <ROLES_SET>: continue` *before* any DTE/delta/premium logic runs. For PP and CC, that filter rejects every real position outright — BUG-033's DTE-parsing bug (and even a hypothetical correct DTE parse) was never actually reachable for a single real position this whole session. Collar is unaffected (its role constants already match production). |
| Status | 🔴 Open — found 2026-08-24, during the same live B031.4 review session that found BUG-033, not yet fixed. |
| Discovered | 2026-08-24, Animesh — asked for a script to close all open PP legs. Building it against `PPOverlayV1.LONG_PUT_ROLES` (the class's own published role set, the obvious thing to filter on) returned zero matching legs against the real `STRATEGY_OVERLAY` position list, despite `get_positions()` independently confirming 3 open `overlay_pp` legs (`NSE_FO|61604`, `NSE_FO|74009`, `NSE_FO|74046`). Confirmed live via direct call: `LONG_PUT_ROLES = {"long_put", "protective_put", "pp_long_put"}` (`pp_overlay_v1.py`), `SHORT_CALL_ROLES = {"cc_short_call", "short_call", "covered_call"}` (`cc_overlay_v1.py`) — neither set contains `"overlay_pp"`/`"overlay_cc"`, the actual `leg_role` strings `paper_3track_overlay_entry.py`'s `auto_pp_bootstrap()`/`auto_cc_bootstrap()` write (confirmed via `grep leg_role=\"overlay` against that file: lines 1051/1063/1079/1091). Direct positions/filter comparison: `len([p for p in positions if p.leg_role in LONG_PUT_ROLES])` → `0`, `len([p for p in positions if p.leg_role in SHORT_CALL_ROLES])` → `0`, against 3 real open `overlay_pp` + 1 real open `overlay_cc` position. `CollarOverlayV1.SHORT_CALL_ROLE`/`LONG_PUT_ROLE` (singular constants, not sets) are `"overlay_collar_call"`/`"overlay_collar_put"` — already correct, confirmed matching the same grep's `overlay_collar_*` lines. |
| Location | `src/strategy/pp_overlay_v1.py:54` (`LONG_PUT_ROLES`), `src/strategy/cc_overlay_v1.py:54` (`SHORT_CALL_ROLES`) — both module-level sets, used in each class's `check_signals`/`apply_action`/`describe_context`/leg-resolution paths throughout the file. The correct values already exist elsewhere in the codebase: `src/strategy/exit_signals.py:18-19` defines `_OVERLAY_SHORT_CALL_ROLES = {"overlay_cc", "overlay_collar_call"}` and `_OVERLAY_LONG_PUT_ROLES = {"overlay_pp", "overlay_collar_put"}` for `evaluate_roll_overlay()` — those are the real production role names, just never propagated back to `pp_overlay_v1.py`/`cc_overlay_v1.py`'s own filters. |

**Root cause:** same "S2r renamed the leg-role/namespace convention, class-local constants never got the memo" shape as BUG-031 (which was `strategy_name`) and BUG-033 (which was `_parse_expiry`'s key format) — a third independent instance of the same underlying pattern in the same three files. `LONG_PUT_ROLES`/`SHORT_CALL_ROLES` read like pre-S2r role names for a standalone (non-overlay) PP/CC strategy that predates the `overlay_*` naming convention `paper_3track_overlay_entry.py` actually uses. `CollarOverlayV1` escaped this because its role constants (`SHORT_CALL_ROLE`/`LONG_PUT_ROLE`) were apparently authored after — or already using — the `overlay_collar_*` convention.

**Impact:** identical in shape to BUG-031's original finding — zero live exit-signal coverage — but for a *different* reason and, since this filter runs first, it's the reason that actually matters right now: even with BUG-031's `strategy_name` fix live (SHA `ea5df81`), `PPOverlayV1`/`CCOverlayV1.check_signals()` still evaluate exactly zero real positions. The "no exit signals fired" result from today's B031.4 live run (`scratch/2026-08-24_bug031_manual_exit_review.py`) was **not** informative for PP/CC — it never got past this filter to check delta/premium/DTE at all. It *was* informative for the `overlay_collar_put` leg (Collar's role constants are correct), so that leg's "no signal fired" read stands.

**Suggested fix:** repoint `LONG_PUT_ROLES` (`pp_overlay_v1.py`) to `{"overlay_pp"}` and `SHORT_CALL_ROLES` (`cc_overlay_v1.py`) to `{"overlay_cc"}` — a PP-only and CC-only set respectively (not reusing `exit_signals._OVERLAY_LONG_PUT_ROLES`/`_OVERLAY_SHORT_CALL_ROLES` directly, since those deliberately include the Collar variants too for `evaluate_roll_overlay`'s shared use — pulling them in here would make `PPOverlayV1` start processing Collar's put leg, a real behavior change out of scope for this fix). Needs regression tests using the real `"overlay_pp"`/`"overlay_cc"` leg_role strings (the existing unit test suites use `"short_call"`/`"protective_put"` as their default fixture values — see `test_cc_overlay_v1.py`/`test_pp_overlay_v1.py`'s `_make_position()` `leg_role` defaults — which is exactly how this shipped passing despite matching nothing real; same class of gap BUG-031's B031.3 already called out and partially fixed for `strategy_name`, this is the `leg_role` sibling of that same gap). Should ship together with or immediately after BUG-033 (both block PP/CC's live signal path; fix order doesn't matter functionally, but BUG-034 should land first since it's what's actually silently masking BUG-033 right now).

**Immediate manual action, independent of the code fix:** none beyond what BUG-033 already flagged (the `NSE_FO|61604` near-expiry decision) — this bug doesn't change what to do about any specific open leg, it changes how much to trust "no signal fired" as evidence that a leg is fine. Treat every currently-open PP/CC leg as unreviewed by automation until this + BUG-033 both ship; Collar's `overlay_collar_put` leg is the one leg this session's live check actually covers.

**Related:** BUG-031 (same three-file "role rename never propagated" pattern, `strategy_name` axis); BUG-033 (same pattern, `_parse_expiry` axis — and downstream of this bug for PP/CC, since this filter runs first); found while building the PP-close script for Animesh's "close all PP legs" request (`scratch/2026-08-24_close_all_pp_legs.py`), which uses the real `"overlay_pp"` literal directly rather than the buggy `LONG_PUT_ROLES` constant so it isn't blocked by this bug.

---
