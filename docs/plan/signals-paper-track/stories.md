# Signals Paper Track — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, update the story status
> summary in `docs/plan/README.md`, add one line to `TODOS.md`.

> DDL note: SPT-2 onward that touch DB use the exact schema in `schema.md` (added by SPT-1's
> rewrite once the storage decision is fixed). Do not inline DDL in a spec below — `schema.md`
> is the sole source once it exists.

---

## SPT-1 — Council checkpoint (no code)

**Files to change / create:** none this task. Output is a `docs/council/` prompt (or a saved
prompt under `docs/council/pending/` if the council server is offline), a `DECISIONS.md`
entry once the ruling lands, and a rewrite of SPT-2..SPT-8 in `tasks.md` + every spec below
this one in `stories.md`.

**Before any council draft — read:**
- `docs/council/README.md` §"When to Trigger" and the template list.
- `src/strategy/CLAUDE.md`, `src/paper/CLAUDE.md` — the `StrategyMonitor` tick loop,
  `PaperExecutor`, `ExitSignalEngine`, `ProfitLockEngine`, `PaperStore`, `TradeState` contracts.
- `src/signals/` in full — models, aggregator, store, `scripts/morning_signal.py`,
  `scripts/record_signal_outcome.py` (its `--auto` monthly-option resolution via
  `src/signals/option_resolver.py::resolve_monthly_option`).
- `DECISIONS.md` 2026-07-02 paper-delta-source council and the §Paper & Reporting entries
  (the track-independence decision, 2026-08-10 council).

**The two decisions to put to the council:**

1. **Module boundary (`data_architecture`).**
   - **A — reuse `src/strategy/` + `src/paper/`.** Signals becomes a `PaperStrategy`; the
     monitor daemon, exit engines and profit-lock (trailing) logic already exist and are
     tested; the position persists in `PaperStore`. Cost: couples the deliberately-independent
     signals track to the paper engine's model evolution; the signal is a naked long monthly
     option, structurally unlike the delta-neutral strategies that engine was built around;
     the 2026-08-10 council explicitly ruled the signals track independent.
   - **B — self-contained loop in `src/signals/`.** A small monitor and exit evaluator built
     for exactly one shape: one long option, SL / target / trailing, square off by 15:00; own
     table. Cost: reimplements trailing-stop and tick-loop mechanics that already exist;
     a second monitor process to run and supervise.

2. **Trade rules (`strategy_parameters`).** Several parameters are **pre-decided (2026-09-09,
   Animesh) and not reopened by the council:**
   - Expiry: monthly, near-month, roll to next month at ≤ 7 DTE — uniform via
     `src/signals/option_resolver.py::resolve_monthly_option` (a ≤ 7-DTE roll added to it;
     `get_expiry_candidates` untouched), so the paper track and `record_signal_outcome.py`
     trade the identical instrument.
   - Position size: fixed 1 lot.
   - Time exit: hard 15:00 square-off, no overnight hold. Intraday-only, so theta is a minor
     cost — spread is the real one; the ≤ 7-DTE roll keeps entries in the liquid near-month.
   - Stop-loss and target: expressed as a % of entry premium (levels are the council's to set).
   - Entry timing: immediately on the aggregated signal.

   **Open for the council:**
   - Stop-loss / target *levels* (the −X% / +Y% numbers).
   - Trailing stop: activation threshold (after +X% unrealised), trail distance (Y% of peak
     mark, or a fixed rupee give-back), and whether it replaces or coexists with the fixed
     target.
   - Intraday fill model: mid, last, or a spread-aware mark; the exit-fill assumption at a
     stop or a square-off.

**Recommended template:** `strategy_parameters` as the primary frame (the SL/target/trailing
design is the larger surface), with an explicit `data_architecture` section for decision 1.
Name `options-strategist` and `greeks-analyst` perspectives in the draft.

**What to produce:**
1. The council prompt, saved per `docs/council/README.md`.
2. On ruling: a `DECISIONS.md` entry (module boundary + the full rule set, with the rejected
   option and why).
3. A rewrite of `tasks.md` SPT-2..SPT-8 and every spec below, concrete to the chosen design —
   real file paths, real model names, per-task tests and commit messages. Add `schema.md`.
   Add a dedicated task for the `resolve_monthly_option` ≤ 7-DTE roll (tests: near-month at
   8 DTE stays, at 7 DTE rolls to next month), landing before SPT-3.

**Commit:** `docs(signals-paper-track): council ruling on execution layer + rule set`
(docs-only — no `code-reviewer`).

---

## SPT-2 — Paper-position model + Store *(provisional — SPT-1 rewrites this)*

**Intent:** a frozen model for one signals paper position (entry date, option key, direction,
entry premium + fill ts, size, SL / target / trailing params snapshot, state, exit premium +
ts + reason, realised P&L per lot and total) stored as `TEXT` monetary values per house rules,
plus a Store with write (`open`, `close`, `update_mark`) and read (`get_open`, `get_by_date`,
`get_window`, and `cumulative_pnl()` → `(total, n_trades, wins, losses)` since inception via a
SQL `SUM` — precedent `get_cumulative_realized_pnl`, the Rule-1 aggregation reference) methods.
`schema.md` is the DDL source. Reuses `src/db.py`.

**Before any code:** `get_code_snippet` for whichever base the ruling picks (`PaperTrade` /
`PaperPosition` if A, or a fresh model if B); `search_graph("TradeState")`;
`get_code_snippet("SignalOutcome")` for the P&L field conventions already in the track.

**Tests:** round-trip open→close persistence; reject double-open for a date; Decimal/TEXT
boundary on the money columns; `cumulative_pnl()` over an empty table and over a mix of
winning and losing closed rows.

---

## SPT-3 — Entry executor *(provisional)*

**Intent:** given today's `DailySignal` with `trade_action != NO_TRADE`, resolve the
recommended strike to a monthly option instrument key (reuse
`src/signals/option_resolver.py::resolve_monthly_option`, which carries the ≤ 7-DTE roll),
take a simulated entry fill at the agreed mark,
write the open position row, and send the Telegram entry message — the actual fill price, not
the advisory band. NO_TRADE / already-open days are a no-op with a logged reason.

**Telegram entry message** (shape to confirm at SPT-1; candidate — formatter owns its
escaping, `FORMATTING.md` per-type rules, blank line after the bold header.

**Option A** — the same 7-column table as the exit message and the EOD PT summary, with
`Exit` / `P&L` / `Chg` blank (`—`) at entry, SL / target on a line below, and a
since-inception footer. The table is rendered by a shared `build_position_table(...)` extracted
from `src/reporting/eod_pt_summary.py::_render_table` to `src/notifications/formatting.py`, so
reporting and the signal messages use one builder (not a copy):

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

**Before any code:** `get_code_snippet("resolve_monthly_option")`, `get_code_snippet("InstrumentLookup")`,
`get_code_snippet("_render_table")` (the builder to extract), `trace_path("build_notifier")`;
the SPT-2 model.

**Tests:** BUY_CALL and BUY_PUT resolve + open one row; NO_TRADE and already-open are no-ops;
the message renders (no network) for both directions; the since-inception footer renders with
zero prior trades and with N; `build_position_table` still renders the EOD PT summary
unchanged after the extraction.

---

## SPT-4 — Intraday monitor loop *(provisional)*

**Intent:** on a cadence during market hours (cadence set by SPT-1), fetch the open position's
option LTP, update the stored mark / peak, and pass the tick to the SPT-5 exit engine. Holiday
and outside-market-hours are no-ops. Dedup so one exit condition fires once. If the ruling is
A, this is a `StrategyMonitor` registration, not a new loop.

**Before any code:** `get_code_snippet("StrategyMonitor")`, `get_code_snippet("get_ltp")` on
the live market client; SPT-2 Store read methods.

**Tests:** a tick below SL routes to exit; a tick between SL and target is a hold; a second
tick after an exit does not re-fire.

---

## SPT-5 — Exit engine *(provisional)*

**Intent:** pure evaluator — given the position, its params and the current mark, return the
exit decision: `STOP_LOSS`, `TARGET`, `TRAILING_STOP`, `TIME_EXIT` (15:00), or `HOLD`.
Trailing logic per SPT-1. On a non-HOLD, take the exit fill, close the row with the reason and
realised P&L, and send the Telegram exit message. Long option → P&L is `(exit − entry) ×
lot_size`; `Decimal` throughout; `greeks-analyst` review because the exit interacts with
theta / gamma near expiry.

**Telegram exit message** — the same `build_position_table` as the entry message; the bold
header carries the exit reason (`TARGET` / `STOP_LOSS` / `TRAILING_STOP` / `TIME_EXIT`); the
since-inception footer is updated with this closed trade. Replaces `signals/` S5.5a's interim
outcome message once this engine is live; S5.5a ships first as the Phase-1 stopgap:

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

**Before any code:** `get_code_snippet("ProfitLockEngine")`, `get_code_snippet("ExitSignalEngine")`,
`get_code_snippet("pnl_emoji")` / `format_money`; the SPT-2 model and its cumulative-P&L read.

**Tests:** each of SL / target / trailing / time-exit fires on the right mark; HOLD in the
dead band; P&L math for a win and a loss; the message renders for a win and a loss; the
inception footer reflects the just-closed trade.

---

## SPT-6 — Cron / entrypoint wiring *(provisional)*

**Intent:** entry script (once, post-09:15) and monitor (cadence loop or daemon registration)
run on trading days only via `is_trading_day(market_today())`, phase from `SIGNAL_PHASE` /
key set, logging per `LOGGING.md` with an explicit `_SCRIPT_NAME`. No unit tests
(integration-only, matching `morning_signal.py`).

**Deliver:** the crontab lines + log paths for the runbook, mirroring `scripts/morning_signal.py`.

---

## SPT-7 — 6-month evaluation report *(provisional)*

**Intent:** extend `scripts/signal_report.py` (or a sibling) with a PAPER TRACK section over a
`--from` / `--to` window: realised P&L, win rate, average win / average loss, max drawdown,
exit-reason histogram, and an explicit pass/fail against the go-live gate metrics the SPT-1
ruling defines. Reuses the SPT-2 Store read methods.

**Tests:** the aggregation over a small fixture set of closed positions; empty-window guard.

---

## SPT-8 — Docs close *(provisional)*

`CONTEXT.md` "What Exists" (new module/scripts), `DECISIONS.md` (as-built note under the
SPT-1 entry), `TODOS.md` session log + backlog pointer, `docs/plan/README.md` status →
Shipped, `src/signals/CLAUDE.md` (or `src/strategy/CLAUDE.md`) invariants. Then archive per
§Conventions. Also note in `signals/` S5.5a that SPT-5's exit message now replaces its
Phase-1 interim outcome message.

**Commit:** `docs(signals-paper-track): close — <one line>`.
