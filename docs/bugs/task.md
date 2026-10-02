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

> BUG-043 closed 2026-10-02 (SHA `0366fe5` + `94017b7`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-066 closed 2026-10-02 (SHA `1bc9d29`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

> BUG-067 closed 2026-10-02 (SHA `c408c1e` + `d3ba54d`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

## BUG-068 — IC v1/v2 load the BOD instrument file synchronously on every monitor tick

Detail: `docs/bugs/bugs.md` BUG-068.

- [ ] **B068.1** — Load the BOD lookup once per strategy instance (or inject the daemon's lookup) for `_parse_expiry`; no per-tick file read. Tests: lookup loaded once across ticks; numeric-key DTE
  still resolves.
- [ ] **B068.2** — Real `code-reviewer`; commit; close + archive.

## BUG-069 — IC entry "BLOCKED" Telegram alert can be lost: fire-and-forget send then `sys.exit(1)`

Detail: `docs/bugs/bugs.md` BUG-069.

- [ ] **B069.1** — `_gate_alert` awaits the send (bounded timeout) before every pre-leg `sys.exit` in `paper_ic_entry.py` and `_v2.py`. Tests: alert awaited before exit; send failure still exits 1.
- [ ] **B069.2** — Real `code-reviewer`; commit; close + archive.

## BUG-070 — Closing-trade insert and `mark_trade_closed` run in separate transactions

Detail: `docs/bugs/bugs.md` BUG-070.

- [ ] **B070.1** — Decide: single-connection close (store API taking both) vs accept + rely on the backfill script. Record in `DECISIONS.md`. Pending Animesh.
- [ ] **B070.2** — Implement per B070.1 across the wired close paths; tests: a failure between insert and flip leaves no half-state (or documented recovery).

## BUG-071 — `test-runner` agent cannot run the full suite: blocked by the `inline_full_suite` hook

Detail: `docs/bugs/bugs.md` BUG-071.

- [ ] **B071.1** — Make `.claude/agents/test-runner.md`'s command pass `inline_full_suite.sh` (or exempt the agent context in the hook). Test: the agent returns a verbatim pytest summary line for
  `tests/unit/`.

## BUG-060 — Expired paper overlay legs are never settled or closed

Detail: `docs/bugs/bugs.md` BUG-060. Settle-price source decision comes first.

- [x] **B060.1** — Decide the settlement price source (NSE final settle vs last recorded mark) and record it in `DECISIONS.md`. | SHA `6c76abf`
- [x] **B060.2** — Expiry-settlement step: every `OPEN`/`DEFENDED` leg with expiry < today gets a closing trade at intrinsic value and `mark_trade_closed`. Tests: expired leg ends flat and `CLOSED`; a
  leg expiring today or later is untouched. | SHA `1937469`
- [x] **B060.3** — Daily settlement runs at monitor-daemon startup (no separate cron); live dry-run 2026-10-02 found nothing to settle. | SHA `bd687ac`
- [x] **B060.4** — Trade 405 re-settled by hand at intrinsic 783.80 (was 784.15), operator sign-off 2026-10-02; DB-only change.
- [ ] **B060.5** — Verify on the next daemon start (Mon 2026-10-05 09:15): `grep expiry_settlement logs/monitor_daemon.log | tail -2` shows `expiry_settlement_done`. Pending live host.

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

## BUG-042 — `721daf9` MarkdownV2 switch broke every unmigrated `TelegramNotifier` cron caller — silent 400 since 2026-08-25

- [x] **B042.1** — Grep `logs/` + callers of `TelegramNotifier.send` to enumerate every entrypoint still emitting unescaped MarkdownV2; list them in `bugs.md`.
- [x] **B042.2** — Decide fix approach at Step 2b (per-caller call-site escaping vs. defensive auto-escape in `send()` with a `raw=` opt-out); record in `DECISIONS.md` if option 2. | SHA `6c76abf`
- [x] **B042.3** — Implement the chosen fix; audit already-migrated callers for regression to literal backslashes. | SHA `3b5947b` + `88578b4`
- [x] **B042.4** — Surface the swallowed Telegram response body: log the 400 payload (entity-parse offset) in `send()`'s except block. | SHA `84980a3`
- [x] **B042.5** — Tests: one 400/entity-parse regression test per fixed caller (or one for `send()`'s default-escape path); no network. | SHA `3b5947b` + `88578b4`
- [ ] **B042.6** — Suite green + real `@code-reviewer` clean; one manual live send per fixed entrypoint (or user-confirmed next cron run lands).
- [ ] **B042.7** — Flip `bugs.md` BUG-042 status to ✅ Fixed + SHA; move both sections to `docs/archive/bugs/{bugs,task}.md`.

## BUG-019 — Investigation: does every strategy show a live-tick vs. EOD-snapshot P&L disparity?

> Moved to the bottom of this file deliberately (2026-08-24, Animesh) — the 08-14/17/19/20/21 diff (see `bugs.md` BUG-019) found no systematic staleness bug, just ordinary intraday movement, so this
> is low-priority relative to BUG-030/031. Diagnostics are being left running longer rather than removed now. Keep this section last so the session-start protocol picks up BUG-030/031 first.

- [ ] **B019.1** — Diagnostics committed (SHA `f7177b6`) and now diffed against 5 live trading days (08-14, 08-17, 08-19, 08-20, 08-21) — no systematic bias found, gaps flip sign and scale with
  intraday movement (one exact 0.00 diff on a low-movement day confirms the mechanism itself is sound). Leaving diagnostics running per Animesh's call (2026-08-24) rather than closing/removing yet.
  Full context: `docs/bugs/bugs.md` BUG-019.

## Session handoff 2026-10-02 — non-bug items (not `BUG-ID` work; operator / protocol)

- [ ] Run `roll-validator` on `d3ba54d` (BUG-067 B067.5 changed `NiftyTrackComparisonV1._persist_roll`; only `code-reviewer` ran — protocol gap).
- [ ] Add a `CONTEXT.md` "What Exists" line for `src/strategy/expiry_settlement.py` + `scripts/strategies/three_track/paper_expiry_settle.py` (BUG-060; Step 5a gap).
- [ ] Decide whether to commit the session-close audit edits: `suggestions.md`, `session_audit.jsonl`, `docs/plan/technical-debt/stories.md` (DEBT-14 note). Pending Animesh.
- [ ] Push `main` (31 commits ahead of origin as of 2026-10-02). Pending Animesh.
