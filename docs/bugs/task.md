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

> BUG-065 closed 2026-10-01 (SHA `6793e54`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-063 closed 2026-10-01 (SHA `7e72438`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-064 closed 2026-10-01 (SHA `5f15cc8`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-037 closed 2026-10-02 (SHA `5369c0e`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-057 closed 2026-10-02 (SHA `df8d7a3` + `77dfc51`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-059 closed 2026-10-02 (SHA `49ce5fa`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

## BUG-067 — `PaperExecutor.apply` and `CollarOverlayV1._close_both_legs` close legs without `mark_trade_closed`

Detail: `docs/bugs/bugs.md` BUG-067.

- [x] **B067.1** — Wire `mark_trade_closed` into both paths, guarded on the actual insert (same pattern as `5369c0e`). Tests per path: full close flips state, duplicate insert does not. | SHA
  `c408c1e` + `aa84424`
- [x] **B067.2** — Review: real `code-reviewer` (paper-trade state transitions). | SHA `c408c1e`
- [ ] **B067.5** — Same gap in `NiftyTrackComparisonV1._persist_roll` (`src/strategy/nifty_track_comparison_v1.py` ~L558-655): wire `mark_trade_closed` for inserted close trades. Tests: roll flips the
  closed legs, duplicate insert does not.
- [ ] **B067.3** — Dry-run `backfill_mark_trade_closed_overlay` to count stale legs from these paths; apply on the live host.
- [ ] **B067.4** — Commit, flip BUG-067 to ✅ Fixed + SHA, archive entry, update `TODOS.md`.

## BUG-066 — `signal_track_v1` exit leaves its closing SELL leg `OPEN`

Detail: `docs/bugs/bugs.md` BUG-066.

- [x] **B066.1** — `close_signal_entry` also flips the leg's remaining `OPEN` rows for that `(strategy_name, leg_role, instrument_key)` in the same transaction. Tests: after exit both BUY and SELL
  rows are `CLOSED`; a different open signal leg is untouched; bad `trade_id` still raises and writes nothing. (`tests/unit/paper/`) | SHA `1bc9d29`
- [x] **B066.2** — Review: real `code-reviewer` (touches paper-trade state transitions). | SHA `1bc9d29`
- [ ] **B066.3** — Run `python -m scripts.dev.backfill_mark_trade_closed_overlay` (dry-run first: expect 18 legs — 7 signal track + 11 pre-BUG-062 IC residue); confirm a re-run finds 0.
- [ ] **B066.4** — Commit, flip BUG-066 to ✅ Fixed + SHA, archive entry, update `TODOS.md`.

## BUG-060 — Expired paper overlay legs are never settled or closed

Detail: `docs/bugs/bugs.md` BUG-060. Settle-price source decision comes first.

- [x] **B060.1** — Decide the settlement price source (NSE final settle vs last recorded mark) and record it in `DECISIONS.md`. | SHA `6c76abf`
- [ ] **B060.2** — Expiry-settlement step: every `OPEN`/`DEFENDED` leg with expiry < today gets a closing trade at intrinsic value and `mark_trade_closed`. Tests: expired leg ends flat and `CLOSED`; a
  leg expiring today or later is untouched.

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
- [x] **B043.6** — Carry `Decimal` through `CloseLegRow` (`src/notifications/formatting.py`) and all its constructors; quantize explicitly when formatting. Tests: 72.55 renders per the formatter's
  rounding rule. (Moved from BUG-059 on 2026-10-02 — same close paths as B043.2.) | SHA `0366fe5`
- [ ] **B043.4** — Suite green + real `@code-reviewer` clean (financial-logic notification path).
- [ ] **B043.5** — Flip `bugs.md` BUG-043 status to ✅ Fixed + SHA; move both sections to `docs/archive/bugs/{bugs,task}.md`; `TODOS.md` session-log line.

## BUG-042 — `721daf9` MarkdownV2 switch broke every unmigrated `TelegramNotifier` cron caller — silent 400 since 2026-08-25

- [x] **B042.1** — Grep `logs/` + callers of `TelegramNotifier.send` to enumerate every entrypoint still emitting unescaped MarkdownV2; list them in `bugs.md`.
- [x] **B042.2** — Decide fix approach at Step 2b (per-caller call-site escaping vs. defensive auto-escape in `send()` with a `raw=` opt-out); record in `DECISIONS.md` if option 2. | SHA `6c76abf`
- [ ] **B042.3** — Implement the chosen fix; audit already-migrated callers for regression to literal backslashes.
- [x] **B042.4** — Surface the swallowed Telegram response body: log the 400 payload (entity-parse offset) in `send()`'s except block. | SHA `84980a3`
- [ ] **B042.5** — Tests: one 400/entity-parse regression test per fixed caller (or one for `send()`'s default-escape path); no network.
- [ ] **B042.6** — Suite green + real `@code-reviewer` clean; one manual live send per fixed entrypoint (or user-confirmed next cron run lands).
- [ ] **B042.7** — Flip `bugs.md` BUG-042 status to ✅ Fixed + SHA; move both sections to `docs/archive/bugs/{bugs,task}.md`.

## BUG-019 — Investigation: does every strategy show a live-tick vs. EOD-snapshot P&L disparity?

> Moved to the bottom of this file deliberately (2026-08-24, Animesh) — the 08-14/17/19/20/21 diff (see `bugs.md` BUG-019) found no systematic staleness bug, just ordinary intraday movement, so this
> is low-priority relative to BUG-030/031. Diagnostics are being left running longer rather than removed now. Keep this section last so the session-start protocol picks up BUG-030/031 first.

- [ ] **B019.1** — Diagnostics committed (SHA `f7177b6`) and now diffed against 5 live trading days (08-14, 08-17, 08-19, 08-20, 08-21) — no systematic bias found, gaps flip sign and scale with
  intraday movement (one exact 0.00 diff on a low-movement day confirms the mechanism itself is sound). Leaving diagnostics running per Animesh's call (2026-08-24) rather than closing/removing yet.
  Full context: `docs/bugs/bugs.md` BUG-019.
