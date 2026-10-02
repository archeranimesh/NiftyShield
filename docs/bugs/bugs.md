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

## BUG-067 — `PaperExecutor.apply` and `CollarOverlayV1._close_both_legs` record closing trades but never call `mark_trade_closed`; closed legs stay `OPEN`

| Field | Value |
|---|---|
| Severity | **Low** — `paper_trades.state` staleness on flat legs, same category as BUG-035 / BUG-037 / BUG-066 |
| Status | 🟡 Fix in progress — `c408c1e` (B067.1–2) landed 2026-10-02; third path B067.5 + live-host backfill B067.3 pending |
| Discovered | 2026-10-02 — B037.6 `code-reviewer` pass on `5369c0e` (focus: close paths still missing the call) |
| Location | `src/strategy/executor.py::PaperExecutor.apply` (~L250, close-leg loop); `src/strategy/collar_overlay_v1.py::CollarOverlayV1._close_both_legs` (~L508, `record_trades`) |

**Symptom / root cause:** BUG-037 (`5369c0e`) wired `mark_trade_closed` into `close_csp_leg`, `close_ic_legs`, `roll_ic_legs` and the 3track roll, but two production close paths write the closing
trade with `record_trade(s)` and never flip the opening rows. `PaperExecutor.apply` persists every manual / Telegram-approved IC and CSP close (`ic_nifty_v1.py` ~L748 comment); `_close_both_legs` is
the collar's `CLOSE_AND_REENTER_COLLAR` path (`OverlayCloser.close_collar_all` already calls it). Not yet counted on the live DB — B067.3's dry-run gives the number.

**Fix:** after each insert, call `store.mark_trade_closed(strategy_name, leg_role, instrument_key)` only for rows actually inserted, mirroring `5369c0e`. Out of scope, noted by the same review:
`scripts/strategies/cc_calibration/paper_cc_roll.py` (calibration only) and the separate-transaction gap between insert and state flip.


**Implementation progress (2026-10-02):** `PaperExecutor.apply` calls `mark_trade_closed` only when `record_trade` returns True; `_close_both_legs` flips only the rows `record_trades(...)[0]` reports
inserted (index, not unpack — 17 collar tests use a bare `MagicMock` store). Neither path can partial-close (both close `abs(net_qty)`), so no flatness guard is needed; the executor's close loop runs
before its open loop, so a same-`apply` re-open stays `OPEN`. Tests on a real temp `PaperStore`: full close flips, duplicate insert does not, same-role other contract untouched
(`tests/unit/strategy/test_executor.py`, new `test_collar_overlay_v1_mark_closed.py`). Real `code-reviewer`: 0 CRITICAL / ERROR / WARNING. The 3-line shift broke the escaping guard's line pins —
re-pinned in `aa84424`. Third unwired path found: `NiftyTrackComparisonV1._persist_roll` (B067.5). Confirmed fine: `overlay_closer.py`, `auto_close.py` (writes no trades), entry-only scripts.
---

## BUG-066 — `signal_track_v1` exit leaves its closing SELL leg `OPEN`; only the entry BUY row is flipped to `CLOSED`

| Field | Value |
|---|---|
| Severity | **Low** — `paper_trades.state` staleness on flat legs, same category as BUG-035 / BUG-037; no live signal or P&L reads the SELL row's state today |
| Status | 🟡 Fix in progress — fix `1bc9d29` (B066.1–2) landed 2026-10-02; live-host backfill (B066.3) pending |
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


**Implementation progress (2026-10-02):** `PaperStore.close_signal_entry` now runs a second `UPDATE` in the same transaction, after the by-id flip and its not-found raise: every `OPEN` row matching
the entry row's `(strategy_name, leg_role, instrument_key)` (row-value subquery) goes to `CLOSED`. `mark_trade_closed` was not reused — it opens its own connection and would break the single
transaction. Tests (`tests/unit/paper/test_signal_store.py`): SELL row flipped too; other open legs untouched; bad `trade_id` raises and writes nothing. B066.2 real `code-reviewer`: 0 CRITICAL / ERROR
— one-at-a-time entry guard rules out closing a re-entry; all signal-track `state` readers unaffected. Deferred: WARNING on the `_states_by_key_action` test helper (last-writer-wins dict), INFO on a
different-`strategy_name` isolation case and a two-cycle stale-row test.
---

## BUG-060 — Expired paper overlay legs are never settled or closed; they stay `OPEN` in `paper_trades` after expiry and block the next bootstrap entry

| Field | Value |
|---|---|
| Severity | **High** — an expired leg silently poisons P&L (BUG-061) and blocks collar re-entry; PP and CC will hit the same path at their own expiries |
| Status | 🟡 Fix in progress — B060.2 `1937469` landed 2026-10-02; live-host run + cron (B060.3) and trade-405 re-settle (B060.4) pending |
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

**Implementation progress (2026-10-02, B060.2):** `src/strategy/expiry_settlement.py` — pure `intrinsic_value` / `build_settlement_trade`, I/O `resolve_contract` / `find_expired_legs` /
`fetch_index_close` / `settle_expired_legs`; entrypoint `scripts/strategies/three_track/paper_expiry_settle.py` (dry-run default, `--no-dry-run` to persist, repeatable `--contract
KEY=STRIKE:CE|PE:YYYY-MM-DD` override, escaped Telegram report). Separate 09:20 entrypoint, not the 15:35 snapshot: an expired marker leg blocks the 10:30 `--auto-collar` bootstrap, and settlement
covers every paper strategy. S = `BrokerClient.get_historical_candles` daily close for `NSE_INDEX|Nifty 50` dated exactly the expiry date; strike / type from one BOD lookup loaded per run.
Fail-closed: missing close or unresolvable contract leaves the leg `OPEN` and warns. Idempotent (a settled leg is flat; a duplicate-guarded close is reported, not marked). **Deviation:** an OTM leg
books ₹0.05, not 0 — `PaperTrade.price` must be > 0 (same as `ic_close_executor._OTM_EXPIRY_PRICE`; ₹3.25 per 65-lot). **Risk:** the Upstox master drops expired contracts, so a leg found only after
the host BOD refresh needs `--contract`. 22 tests. Real `code-reviewer`: 0 CRITICAL / ERROR; strike-through-float and send-delivery-logging warnings fixed; deferred two narrow `# type:
ignore[arg-type]` on the CE/PE `Literal` (runtime-guarded).
---

## BUG-061 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-30, SHA `7b671db`)

---

## BUG-062 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-30, SHA `ac4d163`)

---

## BUG-057 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-10-02, SHA `df8d7a3` + `77dfc51`)

---

## BUG-058 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-09-30, SHA `17501ec`)

---

## BUG-059 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-10-02, SHA `49ce5fa`)

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

**Implementation progress (2026-10-02):** B043.6 — `CloseLegRow.entry/exit` are `Decimal`; new `_price_1dp()` quantizes to 1 dp `ROUND_HALF_UP` and raises `TypeError` on a non-`Decimal` (mirrors
`format_money`). `float(...)` casts removed at every constructor (IC v1/v2, CSP, CC, PP, collar `_send_close_notification`, `auto_close`, `record_paper_trade` fallback → `Decimal("0")`). Tests: 72.55
→ 72.6, 10.25 → 10.3; float rejected. Real `code-reviewer`: 0 CRITICAL / ERROR; deferred WARNING — `auto_close` legs are `list[dict[str, Any]]`, so mypy cannot see the `Decimal` contract (a
`TypedDict` would). A non-`Decimal` reaching a card now drops that card with a logged warning rather than rendering. **B043.2 re-check:** all five paths already render through the shared
`format_exit_message` with a cycle figure (`🔁 *Cycle #N:*`) and an inception figure (`📈 *Inception:*`), CSP included — the inconsistency this bug describes was fixed by the UXM epic. Open: the
requested `Cycle P&L` / `Since inception` labels conflict with the later UXM spec (`docs/archive/plan/telegram-message-unification/unified-exit-message/stories.md` L115-116); the overlay-only `Overlay
P&L (total realized)` line still duplicates Inception; B043.3 test gap is real either way (no Cycle-line assertion anywhere; collar and `auto_close` assert no footer).
---

## BUG-042 — `721daf9` MarkdownV2 switch broke every unmigrated `TelegramNotifier` cron caller (CC/PP entry, paper snapshot, monitor daemon, pre-market brief) — silent 400 since 2026-08-25

| Field | Value |
|---|---|
| Severity | **High** — see failing callers below |
| Status | 🟡 Fix in progress — B042.1, B042.4 (`84980a3`) done 2026-09-30; B042.2 decided 2026-10-02: call-site escaping + plain-text retry in `send()`, no council (`DECISIONS.md`). |
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


## BUG-037 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-10-02, SHA `5369c0e`)
