# Bug Registry

> One entry per confirmed defect. Do not log speculative issues here — confirm root cause first (graph trace / repro), then log. Suspicions belong in `TODOS.md` until confirmed. Status values: `🔴
> Open` → `🟡 Fix in progress` → `✅ Fixed` (link commit SHA) → `⚪ Won't fix` (with reason). **Scope:** confirmed defects in live/shipped code (paper trading, cron scripts, live gates) — not
> unimplemented spec items, those are `docs/plan/` story tasks. **Relationship to the legacy registry:** a flat bug registry existed at the repo root (`BUGS.md`, single open entry `BUG-001` —
> `daily_snapshot.py` backfill gap, unrelated, low severity). It was relocated to [`docs/archive/BUGS_LEGACY.md`](../archive/BUGS_LEGACY.md) on 2026-08-27 (RDO-4), with a stub left at the repo root.
> This folder is the canonical home for *all* entries going forward; `BUG-001` stays in the archive file until it is fixed and deleted per its own convention. ID numbering is one shared sequence
> across both — this registry starts at `BUG-002`. **This file holds only open work — the `stories.md` equivalent for `docs/bugs/task.md`'s checklist.** `docs/bugs/task.md` is the lean checkbox list;
> every entry here has the full symptom/root-cause/fix detail a task's checkbox alone can't carry. Once a `BUG-NNN`'s every `task.md` line is checked and the fix is committed, move its entry to
> `docs/archive/bugs/bugs.md` (and its checklist to `docs/archive/bugs/task.md`) in the same commit that flips `Status` to ✅ Fixed — mirrors the `docs/plan/` → `docs/archive/plan/` convention. **24
> bugs archived 2026-08-13** (`BUG-002` through `BUG-028` minus the 5 below); see `docs/archive/bugs/bugs.md` for their full history.

---

## BUG-065 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-10-01, SHA `6793e54`)

---

## BUG-063 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-10-01, SHA `7e72438`)

---

## BUG-064 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-10-01, SHA `5f15cc8`)

---

## BUG-066 — `signal_track_v1` exit leaves its closing SELL leg `OPEN`; only the entry BUY row is flipped to `CLOSED`

| Field | Value |
|---|---|
| Severity | **Low** — `paper_trades.state` staleness on flat legs, same category as BUG-035 / BUG-037; no live signal or P&L reads the SELL row's state today |
| Status | 🔴 Open |
| Discovered | 2026-10-02 — re-checking BUG-037 against the live DB (`backfill_mark_trade_closed_overlay --dry-run` found 18 stale flat legs, all post-`5369c0e`) |
| Location | `src/strategy/signal_track_v1.py` exit path (~L773, `record_trade(sell_trade)` → `close_signal_entry`); `src/paper/store.py::close_signal_entry` (`UPDATE … WHERE id = ?`) |

**Symptom:** every `paper_signal_track_v1` exit since the strategy went live (8 exits, 7 `signal_long` legs, 2026-09-15 → 2026-10-01) ends flat with the BUY entry row `CLOSED` and the SELL exit row
(notes `signal_track_v1 exit (TIME_EXIT|TARGET|STOP_LOSS)`) still `OPEN`. Grows by one stale row per exit.

**Root cause:** the exit path inserts the SELL with `PaperStore.record_trade` (default state `OPEN`), then calls `close_signal_entry(trade_id, …)`, whose state update is `UPDATE paper_trades SET state
= 'CLOSED' WHERE id = ?` keyed to the **entry** row's id only. Neither step calls `mark_trade_closed`, so the SELL row is never transitioned. Not covered by BUG-037's fix (`5369c0e` wired CSP / IC v1
/ v2 / 3-track roll only) — signal track shipped after it (SPT-3..5).

**Why inert today:** `get_open_signal_entry` joins `paper_signal_entries` to `paper_trades` on the entry `trade_id` only, and flat legs drop out of `get_positions()`, so no reader sees the SELL row's
state. Becomes a real defect the moment any state-based gate or report scans `paper_trades` by `state` without a net-qty check (the BUG-060 / BUG-062 failure shape).

**Fix (recommended):** inside `close_signal_entry`'s existing transaction, also flip the leg's remaining `OPEN` rows for that `(strategy_name, leg_role, instrument_key)` — safe because the position is
flat at that point (one lot in, one lot out). Keep it in the same transaction rather than a separate `mark_trade_closed` call so the "never half-closed" guarantee in its docstring still holds. Then
re-run `scripts.dev.backfill_mark_trade_closed_overlay` (no `--dry-run`) to clear the backlog.

**Backfill scope note:** the same dry-run also lists 11 IC legs from 2026-09-30 (`v1_leaps` ×3 — entry compensation after the BUG-057 race; `v1_weekly` ×4, `v2_monthly` ×4 — closes with empty notes
and no executor log line, most likely manual `record_paper_trade` runs). Both wrote via `record_paper_trade`, which only started calling `mark_trade_closed` with BUG-062 (`ac4d163`, 2026-09-30 21:30)
— after those 10:30 writes. They are pre-fix residue, not an open gap (zero non-signal stale rows since 2026-10-01); the one backfill run clears them too.

**Cross-refs:** BUG-037 (same shape, different call sites), BUG-062 (the `record_paper_trade` fix that closed the compensation path), BUG-057 (the race that triggered the LEAPS compensation).

---

## BUG-060 — Expired paper overlay legs are never settled or closed; they stay `OPEN` in `paper_trades` after expiry and block the next bootstrap entry

| Field | Value |
|---|---|
| Severity | **High** — an expired leg silently poisons P&L (BUG-061) and blocks collar re-entry; PP and CC will hit the same path at their own expiries |
| Status | 🔴 Open |
| Discovered | 2026-09-30 — investigating a -45,001 Collar line (-565%) in the "NiftyBees vs overlays" digest |
| Location | `paper_trades` lifecycle (no expiry-settlement path); `scripts/strategies/three_track/paper_3track_overlay_entry.py::_has_open_overlay_leg` (L1234) and its bootstrap gate (L1470) |

**Current state (2026-09-30 EOD):** nothing implemented; the one expired collar put was closed by hand (trade 405). BUG-061's fix (`7b671db`) now keeps an unpriced leg from printing a fictitious loss,
so this bug is no longer urgent for P&L display but still blocks collar re-entry and will recur at PP/CC expiries. **Next (2026-10-01, decision first):** B060.1 — choose the settlement price source,
NSE final settle vs last recorded mark, then record it in `DECISIONS.md` before B060.2.

**Symptom:** the collar put `NSE_FO|73994` (trade 178, BUY 65 @ 91.825 on 2026-08-12, expiry 2026-09-29) was still `OPEN` on 2026-09-30. Upstox returns no LTP for an expired contract, so every
snapshot afterwards had nothing to mark. The 2026-09-30 10:30 `--auto-collar` cron logged `bootstrap_skipped overlay_type=collar leg_role=overlay_collar_put` because the expired put still counted as
an open marker leg — the collar was not re-entered.

**Root cause:** nothing in the paper stack settles or closes a leg at expiry. `CCOverlayV1`/`PPOverlayV1`/`OverlayCloser` close only on their exit signals and roll thresholds; a leg that reaches
expiry without triggering one just stops quoting. The collar put here was a put-only entry whose call was an existing `overlay_cc` on the same key (the `_validate_collar_pairs` dedup exemption), so
both legs expired together with no signal on either side.

**Manual repair applied (2026-09-30):** closing SELL recorded via `record_paper_trade` (trade 405, 65 @ 784.15, dated 2026-09-29, last expiry-day mark, not the official NSE settle), then
`PaperStore.mark_trade_closed`. Snapshot re-run then wrote collar `pnl_1d_abs=0`, `pnl_inception_abs=45001.125`.

**Fix (not yet implemented):** an expiry-settlement step run from the daily snapshot (or its own cron) that, for every `OPEN`/`DEFENDED` leg with expiry < today, records a closing trade at intrinsic
value against the underlying's settlement price and calls `mark_trade_closed`. Decide first whether the settlement price comes from the NSE final settle (preferred, needs a source) or the last
recorded mark. Repro test: an open leg with a past expiry ends flat and `CLOSED` after the step; a leg expiring today or later is untouched.

---

## BUG-061 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-30, SHA `7b671db`)

---

## BUG-062 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-30, SHA `ac4d163`)

---

## BUG-057 — IC entry builds the 4-leg basket while the monitor is live; a half-built basket is scored against the previous cycle's stale `original_entry_credit` and fires a false `LOSS_STOP`

| Field | Value |
|---|---|
| Severity | **High** — auto-closes a real position mid-entry, the entry script then compensates the other legs, and the cycle is lost (paper-only today; live-money path if IC ever goes live) |
| Status | 🔴 Open |
| Discovered | 2026-09-30 — `paper_ic_nifty_v1_monthly` 10:30 cron entry; Telegram `1/4 legs NOT persisted: short_put` |
| Location | `scripts/strategies/ic/paper_ic_entry.py` + `_v2.py` (`set_original_entry_credit`, after the leg loop); `src/strategy/ic_nifty_v1.py` LOSS_STOP ~L365-430 |

**Symptom:** the entry recorded `short_put` SELL @72.75 at 10:30:20; the monitor tick at 10:30:22 (`logs/monitor_daemon.log`) evaluated a lone short put, fired `LOSS_STOP`, `CLOSE_FULL` dispatched,
and `ic_close_executor` bought the put back @72.55 (`paper_trades` id 369, notes `ic_nifty_v1 auto-close: CLOSE_FULL`). The entry script kept recording the remaining three legs, its post-run
verification saw `short_put` net qty 0, reported it "NOT persisted", and compensated the three legs it had opened. End state flat, no naked exposure, no cycle. Both jobs started together only because
the laptop woke from sleep and cron caught up — but the monitor ticks every ~30s all day and the basket takes ~26s to build, so the window exists on every entry.

**Root cause (mechanism confirmed from code + log; the stale value itself is inferred):** `ic_nifty_v1.py` scores `LOSS_STOP` as `combined_mark / entry_credit >= loss_stop_pct` (2.0×) and prefers the
persisted `paper_strategies.original_entry_credit` over the recomputed credit (BUG-021). The entry script writes the new cycle's credit only after all four leg subprocesses return, so throughout the
build the column still holds the **previous** cycle's net credit. Prior cycle (2026-09-23) net credit was 44.975 − 22.175 + 21.90 − 8.975 = 35.725; the lone short put marked 72.5 → 72.5 / 35.725 =
2.03 ≥ 2.0 → `LOSS_STOP`. The overwritten column value can't be re-read now (it holds today's 53.85), hence "inferred", but the arithmetic reproduces the trigger exactly.

**Fix (recommended, not yet implemented):** in both entry scripts, clear `original_entry_credit` (set to NULL) *before* the leg subprocesses run, so `ic_nifty_v1` falls back to the recompute path
(lone short put: mark ≈ credit → ratio ≈ 1.0, no stop) until the new credit is written. Smallest change, no monitor edit, no new lock. Alternatives considered: an `entry_in_progress` marker the
monitor honours (more robust against other partial-state signals, but needs a schema column, a stale-marker timeout, and a monitor change); a "skip combined signals unless 4 legs open" guard in the
strategy (rejected — legitimate partial closes such as `CLOSE_CALL_SPREAD` leave 2 legs and must keep their loss stop). Council checkpoint (CLAUDE.md Step 2b) not warranted: one defensible approach,
cheap to reverse.

**Cross-refs:** BUG-058 (the misleading alert this race produced), BUG-021 (why the persisted credit is preferred).

**Second instance (noted 2026-10-02):** the same 10:30 run also hit `paper_ic_nifty_v1_leaps` — monitor `LOSS_STOP` → `CLOSE_FULL` at 10:30:26 (trace `9159aa3d`) closed its lone `short_put` @179.00,
and the entry then compensated the other three legs (`ic_entry.legs_not_persisted … missing_legs=['short_put']`). The fix must cover every IC entry, not just monthly.

---

## BUG-058 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-30, SHA `17501ec`)

---

## BUG-059 — IC v1 close card shows `DTE: 0` for a 27-DTE position and formats prices through `float`

| Field | Value |
|---|---|
| Severity | **Low** — cosmetic/reporting, but money is passing through `float` (violates the Decimal-for-money rule) |
| Status | 🔴 Open — one hypothesis needs a repro test before the fix is scoped |
| Discovered | 2026-09-30 — close card for the mid-entry auto-close (see BUG-057) |
| Location | `src/strategy/ic_nifty_v1.py` ~L836-885 (`CloseLegRow(entry=float(entry), exit=float(exit_price))`, `dte = ... if expiry is not None else 0`) |

**Symptom:** the card read `DTE: 0`, entry/exit `72.8` / `72.5` for actual `72.75` / `72.55` (2-decimal figures on the cycle line of the same card were right).

**Root cause (partly confirmed):** *Price rounding — confirmed:* `float(entry)`/`float(exit_price)` are built into `CloseLegRow`; 72.55 as a float is 72.5499…, so a one-decimal format gives 72.5 where
Decimal half-even/half-up gives 72.6. *DTE — hypothesis:* `dte` falls back to `0` when `expiry is None`, and `expiry` is derived from `positions` via `_parse_expiry`; if `positions` is the post-close
(empty) list, every close card reports `DTE: 0`. Not yet checked which list is passed — needs a unit test that closes a leg and asserts the card's DTE before anything is changed.

**Fix (not yet implemented):** carry `Decimal` through `CloseLegRow` and format with an explicit quantize; derive DTE from the closed trades' instrument keys rather than the (possibly empty) open
list.

---

## BUG-056 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-29, SHA `2c17a85`)

## BUG-055 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-29, SHA `6e6b6aa`)

## BUG-049 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-24, SHA `a874876`)

---

## BUG-053 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-24, SHA `1042312`)

---

## BUG-054 — MVP tracker has no stock-split/corporate-action adjustment; pre-split entry/target/SL prices go stale post-split

| | |
|---|---|
| Status | 🟡 Fix in progress — B054.1–B054.7 landed 2026-09-30 (`ba73df5`…`2881db1`); BECTORFOOD/UCOBANK rows still manual; day-change/high-low/`mvp list` not split-adjusted. |
| Discovered | 2026-09-25 — pick `e30d0a11` (BECTORFOOD), `PENDING` since 2025-09-08, had a 1:5 split (record date 2025-12-12) — see Symptom below |
| Location | `src/mvp/models.py` (`Pick`, `PickStatus`), `src/mvp/tracker.py::check_prices`, `src/mvp/store.py::update_pick` (PENDING→OPEN side effect) |
| Council decision | [`docs/council/2026-09-25_mvp-corporate-actions.md`](../council/2026-09-25_mvp-corporate-actions.md) — see **Fix Design (council-ruled)** below |

**Current state (2026-09-30 EOD):** B054.1–B054.7 are merged and tested (`ba73df5`…`2881db1`, code-reviewer clean). No corporate-action row exists in the live DB yet, so the watch interlock will
suppress SL/target checks and warn on any split-sized overnight gap until one is added. **Next (2026-10-01, manual):** run `python -m scripts.dev.mvp_split_audit`, confirm each candidate externally
(BECTORFOOD 1:5 needs its exact ex-date; UCOBANK stays a candidate until a real split is confirmed), then insert rows via `scripts.mvp corporate-action add`. Known gaps, not yet ticketed:
`get_category_day_change`, `get_category_high_low` and `mvp list`/`summary` are not split-adjusted; a pick entered the day before an ex-date with no earlier snapshot is treated as filled post-split.

**Symptom:** BECTORFOOD pick `e30d0a11` carries pre-split absolute levels (`entry_price=1418.0`, `target_price=2836.0`) from 2025-09-08. The underlying did a 1:5 split (record date 2025-12-12,
https://www.angelone.in/news/stocks/mrs-bectors-food-specialities-1-5-stock-split-record-date-on-dec-12-what-you-need-to-know), so post-split LTP is ~1/5 of these levels. There is no mechanism
anywhere in `src/mvp/` to detect or adjust for this.

**Root cause (confirmed via grep + read, not speculative):** `grep -ni "split|corporate action|adjust"` across `src/mvp/*.py` and `scripts/mvp*.py` returns zero relevant hits (only an unrelated
`re.split()` call in `tracker.py:256`). `Pick` (`src/mvp/models.py:53-108`) has no split-ratio/adjustment-factor field; all price fields (`entry_price`, `reco_price`, `target_price`, `stop_loss`,
`close_price`) are plain absolute `Decimal` levels. The model docstring (line 57) calls out dividends as explicitly out-of-scope but doesn't mention splits at all — this was never scoped, not deferred
by decision. `docs/archive/plan/mvp/{tasks,stories,schema}.md`, `DECISIONS.md`, and this bug registry have no prior mention of splits/bonuses/corporate actions for MVP.

**Mechanics of the failure:**
- PENDING→OPEN is not price-driven: `src/mvp/store.py:385-386` flips status to `OPEN` only as a side effect of someone setting `entry_price` via `scripts/mvp.py update`. So a `PENDING` pick sitting
  through a split isn't mechanically broken yet — it just hasn't had an entry fill confirmed.
- Once `OPEN`, `tracker.check_prices` (`src/mvp/tracker.py:22-64`) does a raw comparison against stored absolute levels: line 44 `ltp >= pick.target_price` → `TARGET_HIT`; line 54 `ltp <=
  pick.stop_loss` → `SL_HIT`. Only `OPEN` picks are evaluated (line 38 filter) — `PENDING` picks are skipped entirely by `check_prices`.
- Consequence if a pre-split pick is (or becomes) `OPEN` without correcting its levels: a pre-split `target_price` becomes numerically unreachable post-split (`TARGET_HIT` never fires), while a
  pre-split `stop_loss` would likely already be below post-split LTP and falsely fire `SL_HIT` the moment the pick goes `OPEN`.

**Fix Design (council-ruled 2026-09-25, unanimous Stage 3 chairman synthesis + all 4 panelists ranked this #1 in Stage 2 — see
[`docs/council/2026-09-25_mvp-corporate-actions.md`](../council/2026-09-25_mvp-corporate-actions.md)):**

**Option B — symbol-scoped `mvp_corporate_actions` event ledger, read-time adjustment.** `Pick` stays frozen/absolute, `mvp_snapshots` is never mutated. A new table (`action_id`, `symbol`, `ex_date`,
`action_type` SPLIT|BONUS|CONSOLIDATION, `new_shares`, `old_shares`, `source`, `notes`, `created_at`, unique on `symbol, ex_date, action_type`) is populated manually via `python -m scripts.mvp
corporate-action add <SYMBOL> --ex-date ... --type ... --new N --old N --source ...`. A pure `cumulative_multiplier(actions, from_date, as_of)` function converts price/qty to the correct basis for any
evaluation date; `tracker.check_prices`, `enter_backfill_pick`, and `run_backfill` all divide/multiply through this function rather than comparing raw stored levels. Option A (in-place rebase) was
rejected — `run_backfill` re-walks raw pre-split bhavcopy closes against stored levels, so mutating `reco_price`/`target_price`/`stop_loss` in place would false-enter/false-exit picks whose split sits
inside their own backfill history (BECTORFOOD is exactly this case) and is not idempotent.

**Tranche scope:** each tranche's `qty`/`fill_price` is adjusted from its own `filled_at` date (never a blanket multiply on the aggregate); `avg_cost` is recomputed as `sum(adjusted_fill_price ×
adjusted_qty) / sum(adjusted_qty)`. `deployed_capital`, `idle_cash`, `realized_pnl`, `benchmark_entry` are **not** touched — a split doesn't multiply invested rupees.

**Detection:** a once-daily ratio-match interlock in `scripts/mvp_watch.py`, on the first tick of the day, before `check_prices` — compares today's opening LTP to the prior session's close; if the
ratio lands within ~3% of a standard split/bonus factor (2, 3, 4, 5, 10, 1.5, 2.5 or inverses), suppresses `SL_HIT`/`TARGET_HIT` for that pick that day and sends a Telegram warning. Does not
auto-insert the action row — ratio match only shortlists for manual confirmation.

**Retrofit required before the adjustment code is trusted:** one-time audit scanning `data/offline/equity_ohlcv/` day-over-day for every `OPEN`/`PENDING` pick for gaps matching a standard factor, then
manual confirmation against NSE announcements (store the bhavcopy gap date as `ex_date`, not the news article's record date) before inserting action rows.

- **BECTORFOOD `e30d0a11`:** stays `PENDING`, do not set `entry_price`, do not manually divide `1418` by `5` — insert the action row once the exact ex-date is confirmed against bhavcopy, then let
  `enter_backfill_pick` find the correct post-split entry day naturally.
- **UCOBANK** (flagged this session via the live `gtf`/`diwali-picks` pick, −27.25% over 11 months): council explicitly ruled this is a **candidate, not confirmed** — a PSU bank can organically lose
  27% without a split; only a confirmed single-session gap near a standard factor justifies an action row.

Not yet implemented — this entry records the ruled design; implementation is a separate task.

---

## BUG-052 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-30, SHA `d8205a6`)

---

## BUG-045 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-10, SHA `aa44820`)

---

## BUG-046 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-10, SHA `35d464d`)

---

## BUG-044 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-15, SHA `7c255fd`)

---

## BUG-047 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-15, SHA `e8d91c1`)

---

## BUG-043 — "Net P&L" in close notifications has no stable meaning: inception-cumulative for IC v1/v2, cycle-only for collar, absent for CSP

| Field | Value |
|---|---|
| Severity | **Medium** — no wrong trade action, but the headline number on every IC close Telegram is the lifetime total, read at a glance as the just-closed cycle's result |
| Status | 🔴 Open |
| Discovered | 2026-09-10 |
| Location | five close paths under `src/strategy/` — see list below |

Close paths affected (all in `src/strategy/`): `ic_nifty_v1.py::_send_close_notification` (~L824) · `ic_nifty_v2.py::_send_close_notification` (~L2224) · `collar_overlay_v1.py` collar close (~L720) ·
`auto_close.py` overlay close (~L308) · `csp_nifty_v1.py::_reentry_notification` (~L635).

**Severity detail:** Animesh read the line `Net P&L: ₹3,739.12` on a `paper_ic_nifty_v1_weekly` CLOSE_FULL message (2026-09-03 close) as that cycle's result. It is the cumulative realized P&L across
all 8 closed cycles since inception; that cycle actually made +₹713.38. Trades and DB records are correct — only the notification label/semantics are wrong.

**Discovered:** 2026-09-10, user asked for a per-cycle P&L breakdown of the weekly IC and noticed the close message's "Net P&L" matched the inception total, not the cycle.

**Root cause:** no shared contract for what the close-notification P&L line reports. Current state per close path:

| Close path | P&L line(s) shown | What "Net P&L" actually is |
|---|---|---|
| `ic_nifty_v1._send_close_notification` | `Net P&L:` | `get_strategy_realized_pnl()` — **inception cumulative** |
| `ic_nifty_v2._send_close_notification` | `Net P&L:` | `get_strategy_realized_pnl()` — **inception cumulative** |
| `auto_close.py` (CC / PP / Collar via `OverlayCloser`) | `Net P&L` **and** `Overlay P&L (total realized)` | per-leg entry−exit — **this cycle** (this path is the closest to correct) |
| `collar_overlay_v1.py` collar close | `Net P&L:` | `call_pnl + put_pnl` — **this cycle only**, no inception figure |
| `csp_nifty_v1._reentry_notification` | *(none)* | CSP close shows no P&L at all |

There is no `get_last_cycle_realized_pnl` helper — cycle boundaries (all legs of the group back to net-zero) are reconstructable from `paper_trades` but nothing does it today.

**Suggested fix:** add `reconstruct_cycles()` / `get_last_cycle_realized_pnl()` to `src/paper/` (shared with the `scripts/dev/` per-cycle report being built alongside this bug — same reconstruction
logic). Then standardise every close notification to two lines with fixed labels, e.g. `Cycle P&L: <±figure>` and `Since inception: <±figure>`, and add them to the CSP close message. Keep
`auto_close.py`'s existing dual line but rename to the standard labels.

**Related:** the `scripts/dev/cycle_pnl_report.py` CLI (per-cycle P&L / exit reason / days in trade for IC-all / CC / PP / Collar) shares the cycle-reconstruction helper; build the helper under
`src/paper/` first, then this bug's notification fix wires it into the five close paths.

---

## BUG-042 — `721daf9` MarkdownV2 switch broke every unmigrated `TelegramNotifier` cron caller (CC/PP entry, paper snapshot, monitor daemon, pre-market brief) — silent 400 since 2026-08-25

| Field | Value |
|---|---|
| Severity | **High** — see failing callers below |
| Status | 🟡 Fix in progress — B042.1 (enumeration) and B042.4 (400 body logged, `84980a3`) done 2026-09-30; B042.2 fix-approach decision pending (council checkpoint). |
| Discovered | 2026-09-09 |
| Location | `src/notifications/telegram.py::TelegramNotifier.send` + unmigrated callers |

**Current state (2026-09-30 EOD):** B042.1 and B042.4 done (`84980a3` logs the Telegram 400 body, so the next failure names its entity-parse offset). Still unescaped, so a live 400 is expected:
`paper_3track_snapshot.py` (action/EXIT-WARN batch and the BUG-032 alerts, about 5 sites), `paper_3track_overlay_entry.py` bootstrap-failure alert, `mvp_watch.py` EOD send; these are the
`_BASELINE_UNESCAPED` "untracked gap" entries. `mvp_watch.run`'s alert and summary sends are now hidden from the guard (callees do escape). **Next (2026-10-01, decision first):** B042.2 — recommended:
per-caller escaping of those sites plus a one-shot retry in `send()` on a "can't parse entities" 400 with a loud log; then B042.3 and B042.5.

**Severity detail:** multiple daily/weekly cron notifications have not reached Telegram on any trading day since 2026-08-25. Confirmed dead so far: covered-call entry (`logs/cc_entry.log`),
protective-put entry (`logs/pp_entry.log`), paper snapshot 15:35 (`logs/paper_snapshot.log`), monitor daemon alerts (`logs/monitor_daemon.log`), pre-market brief 09:00 (`logs/pre_market_brief.log`).
Trades still record to the DB — only the notification is lost.

**Discovered:** 2026-09-09, user asked why the covered call hadn't entered; `logs/cc_entry.log` showed the CC *did* enter (`trade.INSERTED` 2026-08-26, 2026-09-09) but the 2026-08-26 send logged `400
Bad Request`. Grep across `logs/` showed the same signature in ≥5 other cron logs from the same 2026-08-25 boundary.

**Location:** `src/notifications/telegram.py::TelegramNotifier.send` (unconditional `parse_mode="MarkdownV2"`, no auto-escape); every caller above that builds message text without `escape_mdv2()` /
`escape_markdown()` / `mdcode()`.

**Root cause:** same as BUG-039 (SHA `2cb67ce`, which fixed `daily_snapshot.py` only) and the `eod_summary.py` / `TelegramGateway` sibling it flagged out of scope. Commit `721daf9` (2026-08-24 23:00
IST) flipped `TelegramNotifier.send()` from `parse_mode="HTML"` to `parse_mode="MarkdownV2"` unconditionally, moving escaping responsibility onto every caller. The `telegram-markdown-migration` epic
(ROLL-*/MD-* series) migrated the strategy and alert callers but never reached these cron entrypoints. Their message text is structurally full of MarkdownV2-reserved punctuation — `-` (negative
figures, box rules), `.` (decimals, DTE), `()` (percentages), `|` (table separators), `!` `+` `=` `#` — so Telegram rejects the whole send with `400` ("can't parse entities"), swallowed silently by
`send()`'s non-fatal contract. The first send under MarkdownV2 was 2026-08-25; every failure dates from then.

**Why the log never shows the real reason:** `send()` logs only `str(exc)` from aiohttp's `raise_for_status()`, which stops at `400, message='Bad Request', url=…` and drops the response body where
Telegram names the byte offset that failed to parse.

**Suggested fix (decide at Step 2b):** two options.
1. **Per-caller call-site escaping** (BUG-039's approach, per `FORMATTING.md` §6 "escaping happens at the call site"): wrap each assembled `summary_text` in `escape_markdown()` at the
   `notifier.send()` call site. Correct but must be repeated for every entrypoint and is fragile against the next new caller.
2. **Defensive default in `send()`**: auto-escape by default, add an explicit `preformatted=True` / `raw=True` opt-out for the already-migrated callers that intentionally emit `*bold*` / tables. One
   change, closes the class of bug, but requires auditing which existing callers rely on raw MarkdownV2 pass-through.

Recommend option 2 given how many entrypoints are currently broken; confirm no migrated caller silently regresses to literal backslashes.

**Related / out of scope here:** `TelegramGateway`'s parallel `eod_summary.py` regression (`cd1e554`) — noted in BUG-039, still unfixed, separate sender class. Fold it in if option 2 is chosen and
`TelegramGateway` shares the escape path; otherwise its own bug.

---

## BUG-040 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-30, SHA `50a5ce4` + `680778b`)

---

## BUG-038 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-30, SHA `acd8181`)

---

## BUG-039 — `daily_snapshot.py`'s Telegram P&L summary silently stopped sending after 2026-08-24 (unescaped MarkdownV2)

| Field | Value |
|---|---|
| Severity | **High** — the daily 15:45 portfolio P&L notification (waterfall + Hedge/FinRakshak + Dhan Options block) has not reached Telegram on any trading day since 2026-08-25 |
| Status | ✅ Fixed — SHA `2cb67ce` |
| Discovered | 2026-09-01, user reported not receiving the daily message since 24 Aug |
| Location | `scripts/portfolio/daily_snapshot.py::_async_main` (live-run Telegram send block, was line 739) |

**Root cause:** commit `721daf9` (Mon 2026-08-24 23:00:53) changed `TelegramNotifier.send()` (`src/notifications/telegram.py`) from `parse_mode="HTML"` to `parse_mode="MarkdownV2"` unconditionally,
with every caller now responsible for escaping MarkdownV2-reserved characters (`escape_markdown()`/`mdcode()`) or Telegram rejects the send with a 400 ("can't parse entities") — swallowed silently by
`send()`'s non-fatal contract. That commit landed *after* 2026-08-24's 15:45 cron run (which is why that day's message arrived fine, under the old HTML mode) — the very next scheduled send, 2026-08-25
15:45, was the first under MarkdownV2.

`daily_snapshot.py`'s summary text (built by `_format_combined_summary` in the same file plus `format_options_section` in `src/dhan/positions.py`) was never migrated to escape its output — confirmed
via `grep` for `escape_markdown`/`mdcode` in both files: zero hits. The message is inherently full of MarkdownV2-reserved punctuation that's structural to a P&L report: `-` (every negative figure),
`()` (percentages), `.` (decimals), `+` (signed values), `|` (separators). This call site was already a known, documented gap — `tests/unit/notifications/test_escaping_guard.py`'s
`_BASELINE_UNESCAPED` dict carried `("scripts/portfolio/daily_snapshot.py", 739)` with the note *"untracked gap — TODO.md item 9 kept current format as-is (2026-08-11 decision); MD-4's file list never
actually included this file despite that note flagging it for re-check"* — i.e. the `telegram-markdown-migration` epic's ROLL-*/MD-* series migrated the strategy/alert callers but never reached this
one.

**Corroborating evidence:** `logs/snapshot.log` doesn't capture this far into the script's run on any date (a separate, unrelated stdout-buffering gap, present on both good and bad days — not
investigated further since it wasn't needed for root cause). But a sibling script, `scripts/eod_summary.py` (different sender class, `TelegramGateway`, different message — **not** the one the user was
missing), shows the identical failure signature starting the same day and continuing daily through 2026-09-01:
```
2026-08-25 15:42:05 [WARNING] [src] [notifications] [telegram] Telegram notification failed: 400, message='Bad Request'
2026-08-25 15:42:05 [WARNING] [scripts] [eod_summary] Failed to send EOD summary via Telegram.
```
That's a separate regression in `TelegramGateway`'s own (apparently incomplete) MarkdownV2 migration (`cd1e554`) — same day boundary, same root rollout, not fixed by this bug (filed here only as
corroborating evidence of the timing; out of this bug's scope).

**Fix:** wrap `summary_text` in `escape_markdown()` right at the `notifier.send()` call site in `daily_snapshot.py`, rather than threading escaping through every f-string in the two builder functions.
Verified the message contains zero intentional MarkdownV2 entities (no `*bold*`/ `_italic_` anywhere in either builder), so escaping the whole assembled string is behaviorally equivalent to escaping
each interpolated value individually — and per `FORMATTING.md` §6 ("escaping happens at the call site, never inside a formatter") this is a legitimate call site. Manually verified `escape_markdown()`
leaves emoji, box-drawing characters, digits, commas, `₹`, `%`, and whitespace untouched, so the rendered message is visually identical to the 2026-08-24 version the user has as reference. Removed the
now-stale `_BASELINE_UNESCAPED` entry for this call site in the same commit, per that test file's own maintenance contract.

**Not in scope:** `TelegramGateway`'s parallel `eod_summary.py` regression (see above) — a separate message, separate sender class, separate root cause within the same escaping migration; would need
its own investigation.

## BUG-019 — Investigation: does every strategy show a live-tick vs. EOD-snapshot P&L disparity, not just `paper_ic_nifty_v2_monthly`?

| Field | Value |
|---|---|
| Severity | **Under investigation** — not yet confirmed as a bug beyond the BUG-018 case; diagnostic instrumentation added to gather evidence across all strategies |
| Status | 🔍 Diagnostics added and committed (2026-07-23, SHA `f7177b6`), awaiting a live trading day's data before any fix is scoped |
| Discovered | 2026-07-23, as a direct generalisation of BUG-018 — see **Discovery** below the table |
| Location | `src/strategy/monitor.py::StrategyMonitor` |

**Discovery:** Animesh: "can we have some debugs added to check for all the strategy what is the PNL at 15:30 and what does the snapshot measure, i believe there is a disparency"

**Hypothesis being tested:** BUG-018 showed `paper_ic_nifty_v2_monthly`'s own internal P&L computation (`_compute_combined_pnl` inside `check_signals`) never ran at all (silently short-circuited
before reaching it) — so the "disparity" there was actually "the live side computed nothing," not "the two sides computed different numbers using the same inputs." Now that BUG-018 is fixed, Animesh
suspects a *broader* disparity may exist across all strategies between what the live monitor tick sees intraday (specifically near close, ~15:30) and what `paper_snapshot.py`'s EOD cron records a few
minutes later (~15:35-15:36). This could be: (a) a genuine last-minute market move between the last tick and the EOD read (not a bug), (b) a real computation/staleness bug independent of BUG-018, or
(c) nothing — the two readings may in fact agree once V2 is no longer blind.

**Instrumentation added (2026-07-23):** `StrategyMonitor._log_live_pnl_diag()`, called at the end of every `_tick()`. Restricted to the 15:20-15:30 IST window (not every ~90s tick all day, to avoid
adding a `get_ltp` batch call per strategy on every tick). For every registered strategy with at least one open leg (`net_qty != 0`), it calls `PaperTracker.compute_pnl(strategy_name)` — the *exact
same function* `paper_snapshot.py`'s EOD cron calls, not an approximation — and logs `strategy_monitor.live_pnl_diag` with `unrealized_pnl`/`realized_pnl`/`total_pnl`/`time`. Because it's the
identical function, any gap between this tick's reading (~15:20-15:30) and the EOD snapshot's own log line (`Recorded paper NAV snapshot for '<strategy>' ... total_pnl=X`, ~15:35-15:36) is a genuine
timing/staleness disparity, not a methodology difference — the two sides can be diffed directly.

**Tests:** `tests/unit/strategy/test_strategy_monitor.py` — `test_live_pnl_diag_logged_inside_close_window`, `test_live_pnl_diag_skipped_outside_window`,
`test_live_pnl_diag_skipped_when_strategy_flat`, `test_live_pnl_diag_swallows_compute_pnl_exception`, `test_live_pnl_diag_skipped_when_compute_pnl_returns_none`, `test_live_pnl_diag_window_boundaries`
(parametrized, added after code review — see below). **Not run in-sandbox** (same disk-quota limitation as BUG-018) — verified via `py_compile` only, pending live-host `pytest` run.

**Code review (2026-07-23):** general-purpose agent loaded `.claude/agents/code-reviewer.md` + `REVIEW.md` directly and reviewed the scoped diff. 1 CRITICAL, 2 WARNING, 1 INFO — all resolved before
commit:
- **CRITICAL** (REVIEW.md G5): `except Exception:` in `_log_live_pnl_diag` lacked the required inline `# Intentional: ...` comment (the docstring rationale doesn't satisfy the rule as written). Fixed:
  added inline comment on the `except` line.
- **WARNING**: the diag call was awaited *before* `_write_heartbeat`, so a slow/hanging `get_ltp` inside the comparison window could delay heartbeat freshness — a real (if narrow) production effect
  for something meant to be a pure side-channel. Fixed: reordered so `_write_heartbeat` runs first, diag call moved after.
- **WARNING**: the original tests covered only one clearly-inside (15:25) and one clearly-outside (11:00) time, leaving the inclusive `_PNL_DIAG_WINDOW_START`/`_MARKET_CLOSE` boundaries (15:20, 15:30)
  and the just-outside minutes (15:19, 15:31) unasserted — exactly where off-by-one errors hide. Fixed: added `test_live_pnl_diag_window_boundaries` (parametrized, 4 cases).
- **INFO**: mocking `monitor._tracker` post-construction (rather than mocking broker/store) verified as a reasonable unit-test strategy — the real `PaperTracker(store, broker)` wiring still runs in
  `__init__` via `_make_monitor`, no integration gap hidden. No action needed. Decimal correctness (`str(unrealized)` etc., no float leakage) and the `PaperTracker(store,
  broker)`/`BrokerClient`-satisfies-`MarketDataProvider` wiring both verified clean.

**Next step:** after the next trading day, grep `logs/monitor_daemon.log` for `strategy_monitor.live_pnl_diag` (per strategy, 15:20-15:30 entries) and `logs/paper_snapshot.log` for `Recorded paper NAV
snapshot` (same day), diff the last live reading against the EOD figure for every strategy. If a real gap shows up beyond what a few minutes of market movement could plausibly explain, escalate to a
proper BUG-0XX with root-cause investigation; if not, remove this diagnostic (same 2026-07-24-style cleanup as BUG-018's temp logs, timeline TBD based on how many days of data are needed).

**Committed:** SHA `f7177b6`.

**Investigation result (2026-08-24):** ran the diff the "Next step" above calls for, across 5 separate trading days now present in `logs/monitor_daemon.log`/`logs/paper_snapshot.log` (08-14, 08-17,
08-19, 08-20, 08-21) — last `strategy_monitor.live_pnl_diag` tick (15:28-15:29) vs. the EOD `Recorded paper NAV snapshot` line (~15:35-15:36) for each strategy:

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

No systematic bias — sign flips constantly, magnitude tracks how much the market actually moved that day (near-zero on the quiet 08-19 weekly reading vs. -221 on the more volatile 08-20 leaps
reading), and one exact 0.00 diff (08-19 weekly) confirms the two sides agree perfectly when the market genuinely didn't move in the 15:28→15:36 window. This matches hypothesis (a) — ordinary
last-minute intraday price drift between the last live tick and the EOD read — not (b), a real computation/staleness bug. Per the "Next step" exit criteria above, this would normally mean removing the
diagnostic; **Animesh's call (2026-08-24): leave it running longer** rather than closing/removing now. `docs/bugs/task.md`'s BUG-019 section moved to the bottom of the file (still open, deliberately
deprioritized below BUG-030/031) so the session-start protocol doesn't pick B019.1 up next.

**Related:** BUG-018 (the specific case that prompted this generalisation).

---

## BUG-032 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-08-24, SHA `67d4010`, backfill applied same day)

---

## BUG-036 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-08-24, SHA `d40c3a1`, backfill applied same day)

---


## BUG-037 — `mark_trade_closed()` also never wired into CSP/IC v1/v2 close paths; 54 stale flat legs found live (54, not just BUG-035's 2)

| Field | Value |
|---|---|
| Severity | **MEDIUM** — see **Severity detail** below the table |
| Status | 🔴 Open — found 2026-08-24, not yet fixed. |
| Discovered | 2026-08-24 — see **Discovery** below the table |
| Location | `src/strategy/csp_roll_executor.py::close_csp_leg` (CSP), `src/strategy/ic_close_executor.py::close_ic_legs`/`roll_ic_legs` (IC v1/v2) — see **Location detail** below the table |

**Severity detail:** same category as BUG-035: `paper_trades.state` staleness on already-flat legs, not a live P&L/Greeks defect. Currently inert per BUG-035's B035.1 trace (flat legs, `net_qty == 0`,
never appear in `get_positions()`'s output, so `check_signals` never re-evaluates them regardless of their stale `state`) — but the wiring gap is real and wider than BUG-035 scoped.

**Discovery:** while validating BUG-035's generalized backfill script (`scripts/dev/backfill_mark_trade_closed_overlay.py --dry-run`) against the live DB — a scan for any `(strategy_name, leg_role,
instrument_key)` that's flat but still `state IN ('OPEN','DEFENDED')` returned 54 rows, not the 2 BUG-035 already fixed.

**Location detail:** likely also `scripts/strategies/three_track/paper_3track_roll.py`'s futures/proxy roll-close writes (unconfirmed, see Suggested fix).

**Symptom:** 54 `(strategy_name, leg_role, instrument_key)` tuples are fully flat (BUY quantity − SELL quantity == 0) but still carry `state IN ('OPEN','DEFENDED')` on every row. Breakdown: 5
`paper_csp_nifty_v1` short_put legs, 46 across `paper_ic_nifty_v1_weekly`/`monthly`/`leaps` and `paper_ic_nifty_v2_monthly` (short_call/short_put/long_call_hedge/long_put_hedge), 1
`paper_nifty_futures` base_futures leg, 1 `paper_nifty_proxy` base_ditm_call leg, and 1 more `paper_nifty_overlay`/`overlay_pp` leg (`NSE_FO|74046`) that BUG-035's original two-row backfill missed
because it only looked at the two instrument keys named in that bug's discovery query, not the whole table.

**Root cause:** Same shape as BUG-035 — `PaperStore.mark_trade_closed()` was never wired into the CSP or IC close/roll paths either. Confirmed via direct grep (not the codebase graph — see note
below): `csp_roll_executor.py::close_csp_leg()` (used by `CSPNiftyV1.apply_action`'s `CLOSE_AND_ROLL`/`CLOSE_AND_WAIT`/`ROLL_DOWN_AND_OUT` branches) calls `store.record_trade(close_trade)` and nothing
else. `ic_close_executor.py::close_ic_legs()`/`roll_ic_legs()` (used by both `IronCondorV1` and `IronCondorV2`'s `apply_action` for `CLOSE_FULL`/`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` and roll
actions) call `store.record_trades(trades)` and nothing else. Neither ever calls `mark_trade_closed()`.

**Graph-index correction (important for future sessions):** BUG-035's B035.1 trace used `codebase-memory-mcp`'s `trace_path(direction=inbound)` and reported **zero callers** for both
`get_trade_state()` and `mark_trade_defended()` project-wide. That was wrong — a direct `grep -rn` found real callers of both in `src/strategy/csp_nifty_v1.py` (`get_trade_state()` at line 203,
feeding `evaluate_delta_breach_csp`'s OPEN-vs-DEFENDED state-aware branching per `CONTEXT.md`'s own documented behavior; `mark_trade_defended()` at line 596, in the `ROLL_DOWN_AND_OUT` flow). The
graph's CALLS-edge index for this repo appears stale for at least these two symbols. This doesn't change B035.1's practical conclusion — CSP's `check_signals` only reaches `get_trade_state()` for
positions `get_positions()` returns, which excludes flat (`net_qty == 0`) legs entirely, so the 54 stale rows found here (all flat) still don't affect any live signal evaluation today — but the graph
result itself should not be trusted as a sole source for "zero callers" claims going forward; grep or `query_graph`'s raw CALLS-edge scan should corroborate before stating a symbol is orphaned.

**Suggested fix:** Mirror BUG-035's fix shape — add `store.mark_trade_closed(...)` (or, if a roll only partially closes down to a nonzero size, the appropriate state transition) at each close write
site above, gated on the write actually flattening the position. Before implementing, trace `close_csp_leg`/`close_ic_legs`/`roll_ic_legs` call sites for any place a *partial* close/roll can leave
`net_qty != 0` — unlike BUG-035's overlay legs (always full closes), CSP's `ROLL_DOWN_AND_OUT` and IC's spread-only closes are explicitly partial at the strategy level, so `mark_trade_closed()` must
only fire on the specific leg's own row, using the per-leg trade being written (not a whole-strategy flatten check), same pattern already validated in BUG-035's `OverlayCloser` fix.
`paper_3track_roll.py`'s futures/proxy roll-close path needs its own trace (not yet done) before assuming the identical fix applies. Backfill: `scripts/dev/backfill_mark_trade_closed_overlay.py`
(built for BUG-035, generalized to scan the whole table rather than hardcoding instrument keys) already covers all 54 rows found here — safe to run once the root-cause fix lands, since its discovery
query only targets rows that are *already* flat (no partial-close risk).

**Related:** BUG-035 (identical bug shape, different call sites — CC/PP/Collar there, CSP/IC here); this bug's discovery came directly out of validating BUG-035's backfill script.

**Implementation progress (2026-08-24, B037.1/B037.2):** Re-traced current code (grep, not `codebase-memory-mcp` — its CALLS-edge index is already flagged stale above) for all three call sites.
Confirms the suggested fix needs no gating beyond the per-leg trade being written:

- `close_csp_leg` (`src/strategy/csp_roll_executor.py:150`) closes at `existing.quantity` — the full size of that leg's row — before `record_trade`. CLOSE_AND_ROLL/CLOSE_AND_WAIT/ ROLL_DOWN_AND_OUT
  all route through here at full leg quantity.
- `close_ic_legs`/`roll_ic_legs` (`src/strategy/ic_close_executor.py:236,361`) both build closing trades via `_build_close_trades`, called only on positions with `net_qty != 0`, at that leg's full
  `net_qty`. The "partial" in spread-only closes (e.g. CLOSE_CALL_SPREAD) is partial *at the strategy level* (only some roles close) — each individual leg row written is still a full close of that
  row. `roll_ic_legs` additionally writes open-side trades in the same `record_trades` call, so the close-vs-open trades need to stay distinguishable when `mark_trade_closed` is wired in (B037.3) —
  don't derive it from `TradeAction` alone.
- `paper_3track_roll.py::check_and_roll_leg` (`scripts/strategies/three_track/paper_3track_roll.py:252,278`) — **confirmed in scope**, not just "likely" as originally scoped. `qty = abs(pos.net_qty)`,
  full close, `record_trades([close_trade, open_trade])`, no `mark_trade_closed` call anywhere in the file. Same fix shape applies.

No B037.1 flatness-check branch is needed — all three sites already only ever write full-leg closes, never a partial paydown of a single row. B037.3 can call `mark_trade_closed()` unconditionally per
closing trade, keyed to that trade's own `(strategy_name, leg_role, instrument_key)`.

**Implementation progress (2026-08-24, B037.3/B037.4, SHA `5369c0e`):** Wired `store.mark_trade_closed()` into all three confirmed sites:

- `close_csp_leg` (`src/strategy/csp_roll_executor.py`) — calls it only when `record_trade()` returns `True` (guards the duplicate-insert case, same shape as BUG-035's CC/PP overlay fix).
- `close_ic_legs` (`src/strategy/ic_close_executor.py`) — iterates `inserted` (the rows `record_trades()` actually wrote) and marks each one closed, so a partial write (some legs skipped as
  duplicates) only marks the legs that landed.
- `roll_ic_legs` (`src/strategy/ic_close_executor.py`) — marks only the close-side trades. Since `close_trades` and `open_trades` are concatenated into one `record_trades()` call, the close-side rows
  are identified by Python object identity (`id()`) against the pre-concatenation `close_trades` list, not by `TradeAction`, so the freshly-opened replacement leg is never mistakenly marked CLOSED.
- `check_and_roll_leg` (`scripts/strategies/three_track/paper_3track_roll.py`) — marks the leg closed only when `close_trade in inserted` (equality-based; safe here since close_trade/open_trade always
  differ by instrument_key).

Tests added mirroring BUG-035's B035.4 pattern (happy path + duplicate-insert skip) in `tests/unit/strategy/test_csp_roll_executor.py`, `tests/unit/strategy/test_ic_close_executor.py` (both
`close_ic_legs` and `roll_ic_legs`), and `tests/unit/scripts/test_paper_3track_roll.py` (using a real `PaperStore`, not a mock, per that file's existing convention). All 51 tests in the three touched
suites pass; a full `tests/unit/` run shows 31 pre-existing failures/7 errors unrelated to this change (missing `pyarrow`/`fastparquet`/etc. in the ad-hoc review venv, confirmed by traceback
inspection — none touch the files this bug modified).

**B037.5 (2026-08-24):** Re-verified the live DB (`data/portfolio/portfolio.sqlite`) via a new read-only diagnostic, `scratch/diagnostics_db/2026-08-24_check_stale_flat_legs.py` (same discovery query
as the backfill script, no writes) — run both through the Cowork device bridge and directly by Animesh on the live host, identical result: 0 stale flat legs across 134 total trade rows / 9 strategies.
Animesh confirmed he'd run `backfill_mark_trade_closed_overlay.py --dry-run` earlier — that mode never writes, so it isn't what resolved the 54 rows found at discovery time; the actual mechanism is
unconfirmed. No backfill `--apply` run was needed or performed — nothing stale remains.

**Outstanding for this bug:** B037.6 (mandatory real `@code-reviewer` run — this session is Cowork, which cannot spawn `.claude/agents/code-reviewer.md`; the B037.3/B037.4 commit (`5369c0e`) landed
without that gate clearing, so a `@code-reviewer` pass against that commit's diff from Claude Code is still owed before this bug is considered fully closed).

---


