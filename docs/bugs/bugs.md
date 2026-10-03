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

## BUG-067 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-10-02, SHA `c408c1e` + `d3ba54d`)

---

## BUG-068 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-10-03, SHA `5e79fc5`)

---

## BUG-070 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-10-03, SHA `a006ebd`)

---

## BUG-071 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-10-03)

---

## BUG-066 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-10-02, SHA `1bc9d29`)

---

## BUG-072 — `gamma_daily_watch.py` has no trading-day guard: on an exchange holiday or weekend it would persist a stale duplicate of the last session's chain

| Field | Value |
|---|---|
| Severity | **Medium now, High once the cron is enabled** — latent today (no cron line, nothing persisted); once live it corrupts the history that decisions D3 and D5 read |
| Status | 🔴 Open |
| Discovered | 2026-10-03 — first manual `--dry-run`, run on a Saturday night, processed both expiries normally |
| Location | `scripts/pipeline/gamma_daily_watch.py::main` (no check on `today`); the only `is_trading_day` use is inside `resolve_expiries` |

**Symptom:** `python -m scripts.pipeline.gamma_daily_watch --dry-run` on Saturday 2026-10-03 resolved expiries 2026-10-06 and 2026-10-13, got HTTP 200 from the Upstox option-chain endpoint for both,
and derived 180 rows per expiry. Nothing in the log says the market was closed.

**Root cause:** Upstox serves the last session's chain on non-trading days instead of an empty response, so the empty-chain branch in `_fetch_chain` (which returns `None` with a WARNING) never fires.
`main()` never asks whether `today` is a trading day, and the planned cron (`1-5`) includes exchange holidays.

**Impact if enabled unfixed:** a holiday run inserts a second copy of the previous day's rows under a new `snapshot_date`. `oi_change_1d` is then 0 for every strike, "2 consecutive days" removal rules
count a repeated day as a distinct one, and the distinct-day percentile gate (D5) reaches 20 days earlier than it should.

**Fix (not yet implemented):** at the top of `main()`, when `not is_trading_day(today)`: a real run logs `gamma_daily_watch.non_trading_day` at INFO and exits 0 before any fetch; a `--dry-run` logs
the same event as a WARNING and continues, so off-hours testing (as on 2026-10-03) still works. Repro tests: a holiday date with `dry_run=False` makes no client or store call and exits 0; a trading
day is unchanged; a holiday with `--dry-run` still derives rows.

**Related, not yet confirmed as defects (do not log as bugs):** (a) the `>= 3.0` gearing floor in strategy §5b looks non-binding at the implemented scale of `gamma × spot² / ask` (the derive test
fixture gives 62,500), which would also affect Phase B Layer 2 — verify from live values, then settle with council Q2 before GS-2; (b) one WARNING per zero-ask row floods the log (hundreds of lines
per run) — a per-expiry summary count would be quieter. Both are noted in `TODOS.md`.

---

## BUG-060 — Expired paper overlay legs are never settled or closed; they stay `OPEN` in `paper_trades` after expiry and block the next bootstrap entry

| Field | Value |
|---|---|
| Severity | **High** — an expired leg silently poisons P&L (BUG-061) and blocks collar re-entry; PP and CC will hit the same path at their own expiries |
| Status | 🟡 Fix in progress — B060.2 `1937469` landed 2026-10-02; B060.3 `bd687ac` (daemon-startup settlement); trade-405 re-settle (B060.4) pending |
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

**B060.3 (2026-10-02, `bd687ac`):** operator rejected the separate 09:20 cron — the monitor daemon (started 09:15 daily, before the 10:30 overlay-entry crons) now awaits
`settle_expired_legs_at_startup` before its first tick: skipped with a WARNING when the BOD lookup is missing, settle bounded at 60 s and notify at 15 s, each failure logged with its own event, never
blocks the daemon. `paper_expiry_settle` remains the manual tool (dry-run, `--contract`). Live dry-run 2026-10-02: `settled=0 left_open=0` (trade 405 had already flattened the only expired leg). Takes
effect on the next daemon start.

**B060.4 (2026-10-02, DB-only, no SHA):** trade 405 corrected by one hand `UPDATE` (operator sign-off, option 1 of 3): price 784.15 → 783.80 = strike 23500 − NIFTY 50 close 22716.20 (29-Sep). Delta
₹22.75 (0.35 × 65), so collar inception P&L 45,001.13 → 44,978.38 on the next snapshot. A correction CLI was rejected as disproportionate. Pre-edit DB copy kept in the session scratchpad only.
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

## BUG-043 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-10-02, SHA `0366fe5` + `94017b7`)

---

## BUG-042 — `721daf9` MarkdownV2 switch broke every unmigrated `TelegramNotifier` cron caller (CC/PP entry, paper snapshot, monitor daemon, pre-market brief) — silent 400 since 2026-08-25

| Field | Value |
|---|---|
| Severity | **High** — see failing callers below |
| Status | 🟡 Fix in progress — B042.3/B042.5 landed 2026-10-02 (`3b5947b`, `88578b4`); B042.6 live sends pending |
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

**Implementation progress (2026-10-02):** `TelegramNotifier.send()` (`3b5947b`): POST moved into `_post()` returning `(ok, body)`; on a 400 whose body contains "can't parse entities" it resends the
same text once with no `parse_mode` and logs ERROR `telegram.entity_parse_plain_text_fallback`; no retry on other errors, at most one, no extra budget slot, still never raises. Call sites (`88578b4`)
escaped with `escape_markdown`: `paper_3track_snapshot.py` EXIT SIGNAL action + EXIT WARN batch (`compute_and_record_exit_signals`), BUG-032 recovery + streak alerts
(`_check_overlay_multi_instrument_alert`), missing-LTP alert (`_compute_overlay_leg_totals`); `paper_3track_overlay_entry.py::_alert_bootstrap_failure`. `mvp_watch.py` EOD left as is —
`format_eod_summary` already escapes inside the builder (since `71bca0a`); its `_BASELINE_UNESCAPED` entry reclassified as a scanner heuristic limitation. Six baseline entries removed.
`TelegramGateway.send_plain_message` routes through `send()` (gets the retry); `send_notification` / `send_approval_request` post directly (no retry). `eod_summary.py` now uses `TelegramNotifier`. 18
tests (7 `send()`, 11 call-site MarkdownV2-safety via new `tests/helpers/mdv2.py`). Real `code-reviewer`: 0 CRITICAL / ERROR; deferred: pre-existing %-style log lines in `_post()`, and
`test_send_returns_false_on_telegram_entity_parse_error`'s stale docstring (now exercises the generic-400 path). **B042.6 (operator):** live-verify the 15:35 snapshot on an ACTION/WARN day, an overlay
bootstrap-failure alert, `mvp_watch --eod`, one deliberately unescaped test send (expect plain-text delivery + the ERROR line), and grep the cc_entry / pp_entry / monitor_daemon / pre_market_brief
logs for the fallback event.
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
