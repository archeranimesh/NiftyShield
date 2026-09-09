# SPT-1 — Council question (working draft)

> Living doc. We refine this during discussion; when our own understanding is settled the
> "Question to submit" block below goes to `scripts/ask_council.py`. Not yet submitted.
>
> Template: `strategy_parameters` (primary) with a `data_architecture` section for the module
> boundary. Context files to attach: this folder's `prompt.md`, `stories.md`, and
> `src/strategy/CLAUDE.md` + `src/paper/CLAUDE.md`.
> Perspectives to name in the draft: `options-strategist`, `greeks-analyst`.

_Last updated: 2026-09-09._

---

## Locked before the council — do NOT reopen

Decided by Animesh during the 2026-09-09 planning discussion. Listed here so the council
frames its answers around them rather than relitigating.

- **Expiry** — monthly, near-month; roll to next month at **≤ 7 DTE**. Uniform via
  `src/signals/option_resolver.py::resolve_monthly_option` (a ≤ 7-DTE roll is added to it;
  `get_expiry_candidates` and its `dte >= 14` floor are untouched — they are shared by the
  finideas overlays / IC / chain pipelines). Paper track and `record_signal_outcome.py`
  therefore trade the identical instrument.
- **Position size** — fixed 1 lot. Nifty lot size resolved from BOD, fallback constant
  **65** (`DECISIONS.md` 2026-08-10).
- **Time exit** — hard 15:00 square-off, no overnight hold. Positions are intraday-only, so
  theta is a minor cost and bid/ask is the dominant one; the ≤ 7-DTE roll keeps entries in
  the liquid near-month.
- **SL / target basis** — expressed as a % of entry premium. (Levels are still open — see
  below.)
- **Entry timing** — immediately on the aggregated `DailySignal`.
- **Messages** — entry + exit both use one shared `build_position_table` (7-col:
  Strategy/Instrument/Qty/Avg/Exit/P&L/Chg) + a since-inception P&L footer. Option A: entry
  leaves Exit/P&L/Chg blank, SL/target on a line below.

---

## Open points

### 1. Module boundary  (`data_architecture`)

**Current leaning: A.** Reframe the question as "A with what adapter surface", not "A vs B".

- **A — signals becomes a `PaperStrategy`, reusing `src/strategy/` + `src/paper/`.**
  Reuses: `StrategyMonitor` (tick-loop daemon, already `monitor_daemon.py`), `PaperExecutor`
  (`LegSpec` → `PaperFillSimulator` → `PaperStore` row), `PaperStore` / `paper_trades` /
  `TradeState` / `paper_exit_events`, `ProfitLockEngine` (trailing). Free bonus:
  `eod_pt_summary` reads `PaperStore.get_positions()`, so the track appears in the EOD summary
  automatically. A single long option is the degenerate-simplest case for these abstractions
  (built for multi-leg delta-neutral structures).
- **B — self-contained monitor + exit loop in `src/signals/`, own table.**
  Rejected unless the council surfaces a reason A can't carry: reimplements tick-loop +
  trailing mechanics that already exist and are tested; a second daemon to supervise.

**Why B's usual justification fails:** the 2026-09-07 independence ruling (`DECISIONS.md`
line 642) decoupled `signals/` **from `src/backtest/`** ("no `src/backtest/` import") — it
says nothing about `src/paper/` or `src/strategy/`. The paper-track roadmap already carries a
planned **"PT-S2 Signal Pipeline"** slot (`DECISIONS.md` line 84), blocked only on the signals
story shipping — folding the signal into the paper engine was always the intended direction.

**Real costs of A the council should still name (none are blockers):**

1. An adapter `DailySignal` → `SignalEvent` / `ApprovedAction` / `LegSpec` — ~one small module.
2. **A new exit evaluator is needed either way.** `ExitSignalEngine`'s vocabulary
   (`DELTA_STOP`, `LOSS_STOP` tuned to short-premium spreads, IVR-tiered rolls) does not map
   to a naked long with %-premium SL / target. `ProfitLockEngine` covers trailing; the fixed
   SL / target need a small new pure function. "Reuse the exit engine" is only partial.
3. The signal position's model rides `PaperTrade` / `PaperPosition` evolution — mitigated by
   the single-leg simplicity.
4. The monitor inherits `StrategyMonitor`'s tick cadence — see open point 5.

**Question for the council:** given the above, is A correct, and does the naked-long exit
logic (point 2) justify any carve-out — a separate evaluator module, or a separate strategy
namespace — from the shared engines?

---

### 2. Stop-loss / target levels  (`strategy_parameters`)

**Open.** Basis is fixed (% of entry premium). Still to decide:

- The actual −X% / +Y% numbers.
- Symmetric vs asymmetric.
- Whether the numbers are derived from the historical `signal_outcomes` distribution (how far
  the not-taken trades actually ran intraday) or set by judgment.

_Discussion notes: (add here)_

---

### 3. Trailing stop  (`strategy_parameters`)

**Open.**

- Activation threshold — arm the trail only after +X% unrealised.
- Trail distance — Y% give-back from the peak mark, or a fixed rupee give-back.
- Interaction with the fixed target — does the trail *replace* the target once armed, or
  *coexist* (whichever fires first)?

_Discussion notes: (add here)_

---

### 4. Intraday fill model  (`strategy_parameters` / `backtest_methodology`)

**Open.**

- Entry fill: mid / last / spread-aware mark.
- Exit fill at a stop: fill at the level, or at the next observed mark after the level is
  breached (gap-through risk)?
- Exit fill at the 15:00 square-off: same question.
- Note: `PaperFillSimulator` already exists (used by the CC/CSP/IC paper strategies) — the
  question is which of its modes / assumptions apply to a naked long weekly-ish option.

_Discussion notes: (add here)_

---

### 5. Monitor cadence  (`strategy_parameters`)

**Open.** How often the loop polls the open position's option LTP during market hours.
Trade-off: tighter cadence catches stops closer to the level but burns more API calls, and
under model A has to fit `StrategyMonitor`'s existing tick interval (or justify changing it).

_Discussion notes: (add here)_

---

### 6. Go-live gate metrics  (`risk` / `strategy_parameters`)

**Open.** SPT-7 builds a pass/fail report against criteria this ruling defines.

- Evaluation window (6 months assumed).
- Minimum trade count.
- Minimum win rate or expectancy.
- Minimum realised P&L.
- Maximum drawdown.
- All-must-pass vs a composite score.

_Discussion notes: (add here)_

---

## Question to submit  (fill in once the above is settled)

```
topic:    signals-paper-track-execution-layer
template: strategy_parameters
context:  docs/plan/signals-paper-track/prompt.md
          docs/plan/signals-paper-track/stories.md
question: |
  (final wording — TBD after discussion)
```
