# docs/bugs/ — Task Checklist

> Find the first unchecked `- [ ]` line **that belongs to a `BUG-ID` checklist** (see `docs/bugs/prompt.md` for the full session-start protocol). Tick the box and append `| SHA <commit_sha>` when
> done. Add one line to `TODOS.md` session log. Full bug detail for each item — symptom, root cause, suggested fix — lives in `docs/bugs/bugs.md`, never here. **Format contract:** every line in this
> file is `- [ ]`/`- [x]` **`**Bnnn.x**` — one short task sentence.` — optionally followed by `| SHA <sha>` once committed. Do not append implementation narrative, test lists, or review findings
> inline here — that detail belongs in the matching `docs/bugs/bugs.md` entry (add an "Implementation progress" note there instead). This file is a checklist, not a log. **Once every `Bnnn.x` line
> under a `BUG-ID` is checked** and the bug's `bugs.md` Status is ✅ Fixed: move the whole section to `docs/archive/bugs/task.md` (and the matching `bugs.md` entry to `docs/archive/bugs/bugs.md`) in
> the closing commit. Do not leave fully-checked sections in this file — an unchecked line here should always mean real open work.

---

> BUG-033 closed 2026-08-24 (SHA `ef1c341`) — section moved to `docs/archive/bugs/{bugs,task}.md`. BUG-034 closed 2026-08-24 (SHA `88df26e`) — section moved to `docs/archive/bugs/{bugs,task}.md`.
> BUG-032 closed 2026-08-24 (SHA `67d4010`, backfill applied same day) — section moved to `docs/archive/bugs/{bugs,task}.md`. BUG-036 closed 2026-08-24 (SHA `d40c3a1`, backfill applied same day) —
> section moved to `docs/archive/bugs/{bugs,task}.md`. BUG-035 closed 2026-08-24 (SHA `0ecd86b`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-041 closed 2026-09-08 — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-045 closed 2026-09-10 (SHA `aa44820`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-046 closed 2026-09-10 (SHA `35d464d`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-044 closed 2026-09-15 (SHA `7c255fd`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-049 closed 2026-09-24 (SHA `a874876`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-053 closed 2026-09-24 (SHA `1042312`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-061 closed 2026-09-30 (SHA `7b671db`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-062 closed 2026-09-30 (SHA `ac4d163`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-058 closed 2026-09-30 (SHA `17501ec`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-052 closed 2026-09-30 (SHA `d8205a6`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-038 closed 2026-09-30 (SHA `acd8181`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-040 closed 2026-09-30 (SHA `50a5ce4` + `680778b`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

## BUG-060 — Expired paper overlay legs are never settled or closed

Detail: `docs/bugs/bugs.md` BUG-060. Settle-price source decision comes first.

- [ ] **B060.1** — Decide the settlement price source (NSE final settle vs last recorded mark) and record it in `DECISIONS.md`.
- [ ] **B060.2** — Expiry-settlement step: every `OPEN`/`DEFENDED` leg with expiry < today gets a closing trade at intrinsic value and `mark_trade_closed`. Tests: expired leg ends flat and `CLOSED`; a
  leg expiring today or later is untouched.

## BUG-057 — IC entry races the monitor: half-built basket scored against stale `original_entry_credit`

Detail: `docs/bugs/bugs.md` BUG-057 (root cause, recommended fix, alternatives rejected).

- [ ] **B057.1** — Repro test: strategy with a stale `original_entry_credit` and only one open leg emits `LOSS_STOP`; same state with the credit cleared does not. (`tests/unit/strategy/`)
- [ ] **B057.2** — `paper_ic_entry.py` and `paper_ic_entry_v2.py` clear `original_entry_credit` before the leg subprocesses run; new credit still written after. Tests: cleared before first leg,
  restored after success, left NULL on failure.

## BUG-059 — IC v1 close card: `DTE: 0` and float price formatting

Detail: `docs/bugs/bugs.md` BUG-059. Repro-test the DTE hypothesis first.

- [ ] **B059.1** — Failing test: close card DTE for a closed 27-DTE leg (confirms or kills the empty-`positions` hypothesis).
- [ ] **B059.2** — Carry `Decimal` through `CloseLegRow`; quantize explicitly when formatting; derive DTE from the closed trades' keys. Tests: 72.55 renders per the formatter's rounding rule, DTE
  correct.

## BUG-054 — MVP tracker has no stock-split/corporate-action adjustment for entry/target/SL prices

Design ruled by council 2026-09-25 (`docs/council/2026-09-25_mvp-corporate-actions.md`, unanimous): read-time `mvp_corporate_actions` event ledger, not in-place rebase. Full detail:
`docs/bugs/bugs.md` BUG-054 "Fix Design" section; architecture summary: `DECISIONS.md` "MVP — corporate-action (stock split) adjustment" (2026-09-25).

- [x] **B054.1** — Schema + CLI: add `mvp_corporate_actions` table (`src/mvp/store.py` init) and `Pick`-adjacent model; `scripts/mvp.py corporate-action add|list` (reject bare `--ratio` strings,
  enforce the `symbol, ex_date, action_type` unique constraint as the idempotency guard). Tests: add/list round-trip, duplicate insert rejected, invalid `new_shares`/`old_shares` rejected. | SHA
  `ba73df5`
- [x] **B054.2** — Pure adjustment function: `cumulative_multiplier(actions, from_date, as_of)` in `src/mvp/` (no I/O, `Decimal` throughout). Tests: no actions → `1`; single/compounding actions;
  `from_date < ex_date <= as_of` boundary; the `price_old / M == price_new` and `qty_old * M == qty_new` invariant. | SHA `0de1c1e`
- [x] **B054.3** — Wire into live tracking: `tracker.check_prices` loads actions per pick's symbol and compares LTP against `target_price / M` / `stop_loss / M` (not raw stored levels). Tests: breach
  detection identical to today when no actions exist; correct post-split breach when one does. | SHA `1f186b8`
- [x] **B054.4** — Wire into the historical walk: `enter_backfill_pick` and `run_backfill` (`src/mvp/backfill.py`) compare each day's raw close against levels adjusted by `M(pick_date, D)` for that
  day `D`. Tests: a split mid-PENDING does not false-enter; a split mid-OPEN does not false-fire SL/target on the wrong side of the ex-date (BECTORFOOD-shaped case). | SHA `872c1aa`
- [x] **B054.5** — Detection interlock: once-daily ratio-match check in `scripts/mvp_watch.py`, first tick of the day, before `check_prices` — suppress SL/target eval + Telegram-warn on an overnight
  gap within ~3% of a standard split/bonus factor; never auto-inserts an action row. Tests: gap matching a factor suppresses + warns; a non-matching (organic) drop does not suppress. | SHA `87394e7`
- [x] **B054.6** — Update display/aggregation call sites to read the adjusted view (not raw `Pick` fields): `format_holdings_row`/`format_hourly_summary` (`src/mvp/tracker.py`), `get_category_stats`
  (`src/mvp/store.py`). Tranche recompute: `avg_cost` as `sum(adjusted_fill_price × adjusted_qty) / sum(adjusted_qty)`, never a blanket scale of the aggregate;
  `deployed_capital`/`idle_cash`/`realized_pnl`/`benchmark_entry` untouched. Tests: P&L/`avg_cost` render correctly pre- and post-split for a pick with tranches on both sides of an ex-date. | SHA
  `55b603d`
- [x] **B054.7** — Retrofit: one-time audit script scanning `data/offline/equity_ohlcv/` day-over-day for every `OPEN`/`PENDING` pick for gaps matching a standard factor (candidates only, not
  auto-applied). Manually confirm and insert action rows for real splits found (BECTORFOOD `e30d0a11` 1:5 pending confirmation of exact ex-date; UCOBANK is a candidate only, per council ruling — do
  not insert its action row without external confirmation of an actual split). | SHA `2881db1`

## BUG-043 — "Net P&L" in close notifications is inception-cumulative for IC v1/v2, cycle-only for collar, absent for CSP — no stable per-strategy contract

- [x] **B043.1** — Add `reconstruct_cycles()` + `get_last_cycle_realized_pnl()` to `src/paper/` (all-legs-flat cycle boundaries from `paper_trades`); happy-path + open-trailing-cycle +
  single-leg-overlay tests. Also shipped `scripts/dev/cycle_pnl_report.py`. | SHA `74bf1c4`
- [ ] **B043.2** — Standardise the five close paths (`ic_nifty_v1`, `ic_nifty_v2`, `collar_overlay_v1`, `auto_close.py`, `csp_nifty_v1`) to fixed labels `Cycle P&L` + `Since inception`; add both to
  the CSP close message.
- [ ] **B043.3** — Tests: one per close path asserting both figures render with the standard labels; no network.
- [ ] **B043.4** — Suite green + real `@code-reviewer` clean (financial-logic notification path).
- [ ] **B043.5** — Flip `bugs.md` BUG-043 status to ✅ Fixed + SHA; move both sections to `docs/archive/bugs/{bugs,task}.md`; `TODOS.md` session-log line.

## BUG-042 — `721daf9` MarkdownV2 switch broke every unmigrated `TelegramNotifier` cron caller — silent 400 since 2026-08-25

- [x] **B042.1** — Grep `logs/` + callers of `TelegramNotifier.send` to enumerate every entrypoint still emitting unescaped MarkdownV2; list them in `bugs.md`.
- [ ] **B042.2** — Decide fix approach at Step 2b (per-caller call-site escaping vs. defensive auto-escape in `send()` with a `raw=` opt-out); record in `DECISIONS.md` if option 2.
- [ ] **B042.3** — Implement the chosen fix; audit already-migrated callers for regression to literal backslashes.
- [x] **B042.4** — Surface the swallowed Telegram response body: log the 400 payload (entity-parse offset) in `send()`'s except block. | SHA `84980a3`
- [ ] **B042.5** — Tests: one 400/entity-parse regression test per fixed caller (or one for `send()`'s default-escape path); no network.
- [ ] **B042.6** — Suite green + real `@code-reviewer` clean; one manual live send per fixed entrypoint (or user-confirmed next cron run lands).
- [ ] **B042.7** — Flip `bugs.md` BUG-042 status to ✅ Fixed + SHA; move both sections to `docs/archive/bugs/{bugs,task}.md`.

## BUG-037 — `mark_trade_closed()` also never wired into CSP/IC v1/v2 close paths (54 stale flat legs)

- [x] **B037.1** — Trace `close_csp_leg`/`close_ic_legs`/`roll_ic_legs` (and `roll_down_and_out`) call sites for any partial-close/roll scenario that can leave `net_qty != 0` on the leg being written
  — CSP's `ROLL_DOWN_AND_OUT` and IC's spread-only closes are partial at the strategy level, unlike BUG-035's overlay legs. Confirms whether `mark_trade_closed()` can be called unconditionally per
  closing trade or needs a flatness check first. See `docs/bugs/bugs.md` BUG-037. | SHA `b399a3e`
- [x] **B037.2** — Trace `scripts/strategies/three_track/paper_3track_roll.py`'s futures/proxy roll-close write path for the same gap — the `base_futures` and `base_ditm_call` stale rows found may or
  may not share this root cause; not yet confirmed (unlike CSP/IC, which are confirmed via grep). | SHA `b399a3e`
- [x] **B037.3** — Add `store.mark_trade_closed(...)` (or the appropriate partial-close-safe equivalent per B037.1) to `close_csp_leg`, `close_ic_legs`, `roll_ic_legs`, and the futures/proxy
  roll-close path (per B037.2, if confirmed in scope). | SHA `5369c0e`
- [x] **B037.4** — Tests: regression coverage per call site mirroring BUG-035's B035.4 pattern (mark_trade_closed called on full close, not called on partial close/duplicate insert). | SHA `5369c0e`
- [x] **B037.5** — Re-run `scripts/dev/backfill_mark_trade_closed_overlay.py` (already generalized, built for BUG-035) against the live DB once B037.3 lands — it already covers all 54 rows found in
  this bug's discovery scan. Verified 2026-08-24 via `scratch/diagnostics_db/2026-08-24_check_stale_flat_legs.py` (identical read-only query) run both through the device bridge and directly by Animesh
  on the live host — same file, same result: 0 stale flat legs, 134 total trade rows. Animesh confirms he ran the backfill script with `--dry-run` earlier — note `--dry-run` never writes, so it cannot
  be the mechanism that resolved the 54 rows found at discovery; the actual cause is unconfirmed (possibly a prior `--apply` run, or the discovery-time count reflected DB state that's since moved on).
  No open action either way — nothing stale remains to backfill.
- [ ] **B037.6** — Review: real `code-reviewer` or `general-purpose` + `REVIEW.md` substitute (mandatory — touches live paper-trading state transitions across CSP/IC, the two highest-volume strategy
  families).
- [ ] **B037.7** — Commit, update `bugs.md` BUG-037 status to ✅ Fixed + SHA, update `TODOS.md`.

## BUG-019 — Investigation: does every strategy show a live-tick vs. EOD-snapshot P&L disparity?

> Moved to the bottom of this file deliberately (2026-08-24, Animesh) — the 08-14/17/19/20/21 diff (see `bugs.md` BUG-019) found no systematic staleness bug, just ordinary intraday movement, so this
> is low-priority relative to BUG-030/031. Diagnostics are being left running longer rather than removed now. Keep this section last so the session-start protocol picks up BUG-030/031 first.

- [ ] **B019.1** — Diagnostics committed (SHA `f7177b6`) and now diffed against 5 live trading days (08-14, 08-17, 08-19, 08-20, 08-21) — no systematic bias found, gaps flip sign and scale with
  intraday movement (one exact 0.00 diff on a low-movement day confirms the mechanism itself is sound). Leaving diagnostics running per Animesh's call (2026-08-24) rather than closing/removing yet.
  Full context: `docs/bugs/bugs.md` BUG-019.
