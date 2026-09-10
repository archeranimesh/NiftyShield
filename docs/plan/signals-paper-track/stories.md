# Signals Paper Track — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary in `docs/plan/README.md`, add one line to `TODOS.md`.

> DDL note: every task that touches the DB uses the exact schema in `schema.md` — the sole DDL source, fixed by the SPT-1 ruling. Do not inline DDL in a spec below.

---

## SPT-1 — Council checkpoint  *(COMPLETE — ruled 2026-09-09)*

**Ruling:** `docs/archive/council/strategy/2026-09-09_signals-paper-track-execution-layer.md` (council q17). Absorbed into `DECISIONS.md` §"Signals Paper Track — Execution Layer (2026-09-09, council
q17)". SPT-2..SPT-8 below are rewritten from it.

**One-paragraph summary.** Module boundary **A** — the track is a `PaperStrategy` named `paper_signal_track_v1` on the shared `StrategyMonitor` / `PaperExecutor` / `PaperFillSimulator` / `PaperStore`.
A new **pure** evaluator `src/strategy/signal_exit.py` (*not* `ExitSignalEngine`, *not* `src/signals/`) returns `TARGET | STOP_LOSS | TIME_EXIT | HOLD`. Fixed SL **−30 %** / target **+50 %** of the
entry fill, provisional. Phase 1 fixed-only — no breakeven, no trailing; `TRAILING_STOP` enum member reserved. Monitor cadence **30 s** for this strategy (per-strategy scheduling inside the one shared
monitor; credit spreads stay 90 s). Full mark-path telemetry from day one (`paper_signal_marks`). Two-tier recalibration: N=30 = gross-miscalibration fuse, full redesign at the 6-month gate (N≈50),
any change ships as a prospectively-versioned v2 cohort. Go-live gate G1–G9, all-pass. First live pilot: 1 lot, auto-execute entries, 8 weeks / 20 closed trades.

**Commit:** `docs(signals-paper-track): council ruling on execution layer + rule set` (docs-only — no `code-reviewer`).

---

## SPT-2 — Signal paper models + Store

**Intent:** `schema.md` is done. Build the frozen models and the store layer for the two new tables plus the entry-metadata freeze. The position itself is an ordinary `PaperTrade` row
(`strategy_name='paper_signal_track_v1'`, `leg_role='signal_long'`, `quantity=paper.constants.LOT_SIZE`) — reuse `PaperStore.record_trade`, the existing close path, and `paper_exit_events`. Import
`LOT_SIZE`; never write the literal `65`. New:

- **`SignalPaperEntry`** (frozen Pydantic) — mirrors `paper_signal_entries`: `trade_id`, `signal_date`, `trade_action`, `instrument_key`, `expiry`, `entry_dte`, `entry_ts`, `entry_premium`,
  `entry_bid` / `entry_ask` / `entry_slippage`, `entry_vix`, `entry_underlying`, `signal_confidence`, `sl_pct`, `tgt_pct`, `sl_price`, `tgt_price`, `ruleset_version='v1'`. `Decimal` for money,
  persisted `TEXT`.
- **`SignalMark`** (frozen) — mirrors `paper_signal_marks`.
- Store methods (extend `PaperStore` or a `SignalPaperStore` composed over `src/db.py`): `open_signal_entry(entry)`, `get_open_signal_entry() -> SignalPaperEntry | None` (one position at a time),
  `record_mark(mark)`, `get_marks(trade_id)`, `close_signal_entry(trade_id, exit_event)`, `get_entries(from_, to)`, and `cumulative_pnl() -> (total: Decimal, n: int, wins: int, losses: int)` over
  closed `paper_signal_track_v1` rows (SQL `SUM` / `COUNT`; precedent `get_cumulative_realized_pnl`, the Rule-1 aggregation reference).

**Before any code:** `get_code_snippet("PaperStore")`, `get_code_snippet("PaperTrade")` (the `paper_` prefix validator + required fields), `get_code_snippet("record_trade")`,
`get_code_snippet("PaperExitEvent")`, `search_graph("TradeState")`, `get_code_snippet("get_cumulative_realized_pnl")`. Do not write a `_make_*` model helper from memory — pull the field lists first.

**Tests:** round-trip `open_signal_entry` → `record_mark` ×N → `close_signal_entry`; reject a second `open` while one is open; `Decimal`/`TEXT` boundary on every money column; `cumulative_pnl()` over
an empty table and a win/loss mix; `gap_event` / `stale` persist as written.

**Commit:** `feat(signals-paper-track): SPT-2 signal paper models + store`

---

## SPT-2a — `resolve_monthly_option` ≤ 7-DTE roll — ✅ CLOSED 2026-09-10, no-op

**Outcome:** not implemented. `get_expiry_candidates(preference=["monthly"])` already enforces a `dte >= 14` floor, so `resolve_monthly_option` never returns a `≤ 13-DTE` contract — the next-month
roll the spec asked for already happens at 14 DTE, consistent with `src/signals/snapshot.py` and every overlay / IC caller. Holding the near-month to 7 DTE would need a floor bypass plus a
`snapshot.py` realignment; operator kept the 14-DTE roll. See `DECISIONS.md` §"Signals Paper Track — Execution Layer" 2026-09-10 follow-up. Original spec below, retained for history.

**Intent:** add the ≤ 7-DTE roll to `src/signals/option_resolver.py::resolve_monthly_option` so the paper track **and** `record_signal_outcome.py` both trade the next-month contract inside the current
month's final week. `get_expiry_candidates` and its `dte >= 14` floor are **not** touched — shared by the finideas overlays / IC / chain pipelines.

**Mechanics:** after `resolve_monthly_option` picks `candidates[0]` (nearest monthly), compute its calendar DTE from `signal.trade_date`; if `dte <= 7`, resolve the strike against the **next** month's
last-Tuesday expiry instead (advance via `get_expiry_candidates` with a `min_expiry` past `candidates[0]`, or the next `last_of_month` — whichever the existing helper exposes cleanly). Log
`option_resolver.monthly_roll` with both expiries + the DTE when it fires. Return `None` (no crash) if no next-month contract is listed.

**Before any code:** `get_code_snippet("resolve_monthly_option")`, `get_code_snippet("get_expiry_candidates")`, `search_graph("last_of_month")`, `get_code_snippet("search_options")`.

**Tests:** near-month at 8 DTE → stays; at 7 DTE → rolls to next month; at 7 DTE with no next-month contract → `None`; DTE > 7 path unchanged (regression for `record_signal_outcome`). `greeks-analyst`
review (DTE / expiry logic).

**Commit:** `feat(signals): <=7-DTE roll in resolve_monthly_option`

---

## SPT-3 — Entry executor + `signal_track_v1` strategy

**Intent:** the `DailySignal` → paper entry path.

- **`src/strategy/signal_exit.py`** (created here, as the constants half) — the single owner of the exit-policy numbers: `SL_PCT = Decimal("0.30")`, `TGT_PCT = Decimal("0.50")`, `RULESET_VERSION =
  "v1"`, and `derive_levels(entry_premium: Decimal) -> tuple[Decimal, Decimal]` returning `(sl_price, tgt_price)`. SPT-5 adds `evaluate()` + `SignalExitReason` to this same file. No level literal
  (`0.70` / `1.50`) appears in `signal_track_v1.py` — it calls `derive_levels`. The per-row `sl_pct` / `tgt_pct` / `sl_price` / `tgt_price` on `paper_signal_entries` stay the source of truth for a
  live position; the module constants are just "current default cohort" so a v2 recalibration touches one place and v1 rows are untouched.
- **`src/strategy/signal_track_v1.py`** — the `PaperStrategy`, `strategy_name = 'paper_signal_track_v1'`. The entry path is a plain module-level callable `open_signal_paper_entry(signal, snapshot,
  broker, store) -> SignalPaperEntry | None` so both the SPT-6 `morning_signal` tail-call and the manual `signal_paper_entry.py` invoke the identical hook. Logic: if `DailySignal.trade_action ==
  NO_TRADE` or a position is already open (`store.get_open_signal_entry()`) → return `None` with a logged reason. Otherwise resolve the instrument via `resolve_monthly_option` (carries the SPT-2a
  roll), fetch a real bid/ask quote (`morning_signal` only holds an LTP, so the hook does its own quote fetch), build one `LegSpec` (BUY, `LOT_SIZE`, resolved key), hand to `PaperExecutor` for the
  simulated entry fill (`PaperFillSimulator` BUY at `mid + s`, `mid = (bid + ask) / 2`), freeze the `SignalPaperEntry` (`E`, `(sl_price, tgt_price) = derive_levels(E)`, `sl_pct=SL_PCT`,
  `tgt_pct=TGT_PCT`, VIX, DTE, confidence, `ruleset_version=RULESET_VERSION`), persist via the SPT-2 store, send the Telegram entry message.
- **Shared table builder** — extract `src/reporting/eod_pt_summary.py::_render_table` to `src/notifications/formatting.py::build_position_table(...)` (public); `eod_pt_summary` now calls it. One
  builder, not a copy.

**Telegram entry message** (option A — same 7 columns as the exit and the EOD PT summary; `Exit` / `P&L` / `Chg` blank at entry; SL / target below; since-inception footer from `cumulative_pnl()`;
formatter owns its escaping, `FORMATTING.md` per-type rules, blank line after the bold header):

```
*✅ SIGNAL ENTRY · 29 Sep*

Strategy  Instrument                Qty     Avg    Exit    P&L    Chg
--------  ------------------------  ---  ------  ------  -----  -----
Signal    NIFTY 23000 29 SEP 26 PE   65   39.52       —      —      —
--------  ------------------------  ---  ------  ------  -----  -----
          TOTAL

🛑 SL 27.66   🎯 Target 59.28
🕘 09:32  ·  Nifty 23,041
Σ Inception  +12,480.50  ·  37 trades  ·  24W / 13L
```

**Before any code:** `get_code_snippet("PaperStrategy")`, `get_code_snippet("PaperExecutor")`, `get_code_snippet("LegSpec")`, `get_code_snippet("resolve_monthly_option")`,
`get_code_snippet("_render_table")`, `search_graph("LOT_SIZE")` (`src/paper/constants.py`), `trace_path("build_notifier")`, `get_code_snippet("assemble_market_snapshot")` (VIX source); the bid/ask
quote method on `src/client/upstox_market.py` (~line 376); the SPT-2 models.

**Tests:** BUY_CALL and BUY_PUT each resolve + open exactly one `paper_trades` row + one `SignalPaperEntry` with the frozen levels; NO_TRADE and already-open are no-ops with the logged reason; entry
message renders (no network) for both directions; footer at zero prior trades and at N; `build_position_table` still renders the EOD PT summary unchanged after the extraction.

**Commit:** `feat(signals-paper-track): SPT-3 entry executor + signal_track_v1`

---

## SPT-4 — Monitor registration (30 s) + mark-path logging

**Intent:** register `paper_signal_track_v1` with the shared `StrategyMonitor` at a **30 s** per-strategy cadence (credit spreads stay 90 s — no second daemon). Per due tick, while a position is open:
fetch the option quote (bid / ask / ltp + quote timestamp), compute `mark = (bid + ask) / 2`, update running `mfe_pct` / `mae_pct`, set `stale = 1` when the quote timestamp is > 30 s behind now, set
`gap_event = 1` when `|mark − prev_mark| / E > 0.20`, write a `paper_signal_marks` row, then hand `(entry, mark, now)` to `signal_exit.evaluate` (SPT-5). Holiday / outside-market-hours /
no-open-position → no-op. Dedup so one exit fires once.

**Per-strategy cadence:** add a `due_interval_s` to the monitor registration so a strategy is evaluated only on ticks where it is due; the base tick stays fast enough to service 30 s; quote / chain
fetch happens only for strategies due that tick. If chain-fetch latency makes 30 s impractical, fall back to 90 s **and** keep the `gap_event` flagging — at ≥ 5 gap events within 30 trades, raise
`signal_track.cadence_review` and notify (per the ruling's fallback).

**Before any code:** `get_code_snippet("StrategyMonitor")`, `get_code_snippet("_tick")`, `search_graph("poll_interval_s")`, the quote / bid-ask method on `src/client/upstox_market.py` (~line 376), the
SPT-2 store.

**Tests:** a due tick with `mark ≤ sl_price` routes to `STOP_LOSS`; a dead-band tick is `HOLD` and still writes a mark row; a second tick after an exit does not re-fire; `stale` set on an old quote
timestamp; `gap_event` set on a > 20 % inter-tick jump; `mfe_pct` / `mae_pct` monotonic. `greeks-analyst` review (option-chain / mark handling).

**Commit:** `feat(signals-paper-track): SPT-4 30s monitor registration + mark-path logging`

---

## SPT-5 — Exit engine `signal_exit.py`

**Intent:** extend **`src/strategy/signal_exit.py`** (SPT-3 created it as the SL/target constants module — `SL_PCT` / `TGT_PCT` / `RULESET_VERSION` / `derive_levels`; add the evaluator to that same
file, do not create a second module) with a pure function `evaluate(entry: SignalPaperEntry, mark: Decimal, now: datetime) -> SignalExitDecision`. Priority, no state machine:

```
1. mark >= entry.tgt_price          -> TARGET
2. mark <= entry.sl_price           -> STOP_LOSS
3. now  >= 15:00 IST                -> TIME_EXIT
4. otherwise                        -> HOLD
```

`SignalExitReason` enum: `TARGET`, `STOP_LOSS`, `TIME_EXIT` — **plus a reserved `TRAILING_STOP`** member (unused in Phase 1, present so the Phase 2 dynamic exit needs no migration). The function stays
pure — no I/O, no fill, no persistence.

On a non-HOLD the SPT-4 caller: takes the exit fill via `PaperFillSimulator` SELL at `mid − s` **on the observed tick's mark, not the threshold price** (gap-through is booked — a `0.60·E` mark against
a `0.70·E` SL realises −40 %), closes the `paper_trades` row + writes `paper_exit_events` with the reason, computes realised P&L `= (X − E) × LOT_SIZE` (`Decimal` throughout), sends the Telegram exit
message.

**Telegram exit message** — shared `build_position_table`; bold header carries the reason (`TARGET` / `STOP_LOSS` / `TIME_EXIT`); footer from `cumulative_pnl()` updated with this trade. Replaces
`signals/` S5.5a once live (S5.5a ships first as the stopgap):

```
*🎯 SIGNAL EXIT · 29 Sep*  ·  TARGET

Strategy  Instrument                Qty     Avg    Exit       P&L      Chg
--------  ------------------------  ---  ------  ------  --------  -------
Signal    NIFTY 23000 29 SEP 26 PE   65   39.52   55.25  1,022.12  +39.78%
--------  ------------------------  ---  ------  ------  --------  -------
          TOTAL                                          1,022.12

🕒 13:42  ·  Nifty close 23,088
Σ Inception  +12,480.50  ·  37 trades  ·  24W / 13L
```

**Before any code:** `get_code_snippet("PaperFillSimulator")`, `get_code_snippet("FillResult")`, `get_code_snippet("PaperExitEvent")`, `get_code_snippet("pnl_emoji")` / `format_money`; the SPT-2
models + `cumulative_pnl`.

**Tests:** `TARGET` fires at `mark == tgt_price` and above; `STOP_LOSS` at `mark == sl_price` and below; `TIME_EXIT` at exactly 15:00:00 IST and after; `HOLD` in the dead band and at 14:59; `TARGET`
wins when a tick satisfies target and time together; P&L math for a win (`X > E`), a loss (`X < E`), and the gap-through case; message renders for a win and a loss; `SignalExitReason.TRAILING_STOP`
exists but `evaluate` never returns it. `greeks-analyst` review (theta / gamma near the roll).

**Commit:** `feat(signals-paper-track): SPT-5 signal_exit evaluator + exit message`

---

## SPT-6 — Entrypoint wiring (no new cron)

**Intent:** wire the paper entry + monitor without adding a timed cron. `morning_signal` already builds the broker client, assembles the snapshot (VIX / spot), calls `resolve_monthly_option`, branches
on `trade_action is not NO_TRADE`, and persists the `DailySignal` — a separate 09:35 cron would re-do all of that plus a second broker auth and a DB reload, with a race against the `record_signal`
write. The story's scope guard already sanctions the seam: "`scripts/morning_signal.py` — unchanged **except where SPT hands the `DailySignal` to the new entry step**."

- **`scripts/morning_signal.py` — the tail-call.** After `await asyncio.to_thread(store.record_signal, signal)` (currently the last write in `run()`), call `await
  asyncio.to_thread(open_signal_paper_entry, signal, snapshot, broker, store)`, wrapped in `try/except … logger.warning("morning_signal.paper_entry_failed", …)` at the cron boundary — the identical
  isolation pattern already used around the entry-premium capture just above it, so a paper-entry failure never crashes the advisory pipeline or suppresses the 09:30 Telegram. This is the only change
  to `morning_signal.py`; the signal pipeline itself is untouched.
- **`scripts/monitor_daemon.py` — the monitor registration.** Register `paper_signal_track_v1` inside the existing daemon (already up 09:15–15:30, no new daemon) with `due_interval_s=30`; confirm
  `monitor_daemon` picks it up. The per-strategy due-scheduling on `StrategyMonitor` is SPT-4's work — SPT-6 only wires the registration entry + interval.
- **`scripts/signal_paper_entry.py` — a manual backfill tool, not a cron.** `argparse --date`; loads the persisted `DailySignal` + `MarketSnapshot` for that date and calls the same idempotent
  `open_signal_paper_entry` hook (NO_TRADE / already-open / holiday → logged no-op). Operators run it only if the tail-call logged a failure; the SPT-2 one-open-position guard makes a re-run safe.
  Trading-days-only via `is_trading_day(market_today())`, phase from the env, logging per `LOGGING.md` with an explicit `_SCRIPT_NAME`.

No unit tests (integration-only, matching `morning_signal.py`).

**Deliver:** the updated runbook crontab comment block (the crontab does **not** grow — the `09:30 morning_signal` line now also opens `paper_signal_track_v1`) + the `signal_paper_entry.py` and
`monitor_daemon` log paths.

**Commit:** `feat(signals-paper-track): SPT-6 entrypoint wiring — morning_signal tail-call + monitor registration`

---

## SPT-7 — 6-month evaluation report + go-live gate

**Intent:** a **PAPER TRACK** section (extend `scripts/signal_report.py`, or a sibling `scripts/signal_paper_report.py`) over a `--from` / `--to` window (default: first paper entry → +6 calendar
months), grouped by `ruleset_version` (v1 / v2 **never** pooled). Computes the metrics, then evaluates the gate. This is a **manual / periodic** report — invoked by hand like `signal_report` is today,
**not** a scheduled entrypoint; no crontab line.

**Metrics** (all net of the modelled `mid ± s` slippage — do not haircut again): cumulative net P&L; expectancy per trade; profit factor; win rate (overall + by BUY_CALL / BUY_PUT); average win /
average loss; max drawdown of the cumulative-P&L equity curve; longest losing streak; exit-reason histogram; MFE / MAE distributions (histograms vs the −30 / +50 lines, from `paper_signal_marks`);
results bucketed by exit reason / direction / VIX bucket / DTE / confidence; inter-tick jump percentiles; quote-staleness + missed-tick counts; an advisory-vs-paper disagreement table (sign-match
rate + the days `record_signal_outcome` was green while the paper trade stopped out).

**Gate — all-pass, no composite score:**

| Gate | Rule |
|---|---|
| G1 window | ≥ 6 calendar months **and** ≥ 50 closed trades (`NO_TRADE` days excluded). If fire-rate yields < 50 in 6 months, extend the calendar; hard floor N ≥ 40. |
| G2 exit-path | ≥ 5 each of `STOP_LOSS`, `TARGET`, `TIME_EXIT` fills (deterministic replay acceptable for the rarest if live observation is structurally unlikely). |
| G3 regime | ≥ 1 stretch with India VIX > 18 while a position was open; else extend. |
| G4 net P&L | cumulative net realised P&L > ₹0. |
| G5 expectancy | mean P&L per closed trade > 0. |
| G6 profit factor | gross wins / gross losses ≥ 1.20. |
| G7 win rate | **not gated** — reported only (expected 35–45 %). |
| G8 drawdown | peak-to-trough of cumulative P&L ≤ 8 × mean losing trade (detail below). |
| G9 cost sanity | median round-trip slippage `2s / E` < 8 %; above → halt and re-council. |
| Operational | see the operational list below the table. |

**G8 detail:** also report the longest losing streak. Any single trade losing > 1.5 × the expected SL loss gets an incident classification (gap-through / stale quote / monitor failure) — a genuine
market gap does not fail the gate; an unexplained monitor or stale-data failure does.

**Operational (all must hold):** zero unresolved overnight positions; no duplicate entries or exits; ≥ 95 % action/date/instrument reconciliation with `record_signal_outcome`; every fill reproducible
from persisted bid / ask / VIX band / slippage; all exit paths covered by SPT-5 unit tests.

**Not gates (report, don't block):** advisory-P&L agreement; confidence-/ATR-scaled counterfactuals; crash / gap-tail quantiles; seasonal / per-provider attribution.

**Before any code:** `get_code_snippet("signal_report")` / its `main`, the SPT-2 store reads (`get_marks`, `get_entries`, `cumulative_pnl`), `get_code_snippet("SignalStore")` for the advisory series.

**Tests:** each gate's pass and fail branch over a fixture set of closed `SignalPaperEntry` + `paper_signal_marks` rows; empty-window guard; v1 / v2 rows never pooled; profit factor with zero losses
(pass) and zero wins (fail).

**Commit:** `feat(signals-paper-track): SPT-7 evaluation report + go-live gate`

---

## SPT-8 — Docs close

`CONTEXT.md` "What Exists" — `src/strategy/signal_track_v1.py` + `signal_exit.py`, `scripts/signal_paper_entry.py` (manual tool), the two new tables, and the note that the 09:30 `morning_signal` cron
now also opens the paper entry via a tail-call (no new cron). `DECISIONS.md` — an as-built note under the SPT-1 entry: final module names; the `morning_signal` tail-call seam; `signal_exit.py` as the
combined SL/target-constants + evaluator home; `signal_paper_entry.py` = manual backfill only; 30 s cadence as-shipped, or the 90 s fallback if taken. `DB_REGISTRY.md` — `paper_signal_entries` +
`paper_signal_marks` rows. `TODOS.md` session log + delete the backlog pointer. `docs/plan/README.md` status → ✅ Shipped and the epic-row pointer. `src/strategy/CLAUDE.md` (create if absent) — the
`paper_signal_track_v1` invariants (one position at a time; levels frozen at entry from `derive_levels`; `signal_exit` stays pure; `TRAILING_STOP` reserved). Mark `signals/` S5.5a `won't-do` and point
it here. Note the deferred consolidation work now lives in `docs/plan/signals-entrypoint-consolidation/`. Then archive `docs/plan/signals-paper-track/` → `docs/archive/plan/` per `docs/plan/README.md`
§Conventions *Completion → archive*.

**Commit:** `docs(signals-paper-track): close — <one line>`.
