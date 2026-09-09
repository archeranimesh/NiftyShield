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

**Open.** Basis is fixed (% of entry premium). Still to decide: the actual −X% / +Y% numbers,
symmetric vs asymmetric, and judgment vs empirical calibration.

**Runtime flow (settled 2026-09-09).**

At entry the two levels are pure arithmetic off the entry fill `E`, frozen into the position
row alongside `E`, qty (1 lot = 65) and the trailing snapshot:

```
sl_price  = E * (1 − sl_pct)      # sl_pct 0.30 → SL at 0.70·E
tgt_price = E * (1 + tgt_pct)     # tgt_pct 0.50 → target at 1.50·E
```

Anchored to premium, not the underlying — the monitor needs only the option LTP per tick, and
the levels self-scale with IV.

Monitor tick (09:35→15:00): fetch LTP `M`, update `mark` and `peak = max(peak, M)`, hand
`(position, M, now)` to the exit engine.

Exit engine — pure eval, priority order:

```
1. M ≤ sl_price                        → STOP_LOSS
2. trail armed and M ≤ trail_stop      → TRAILING_STOP     (open point 3)
3. M ≥ tgt_price  (if target active)   → TARGET
4. now ≥ 15:00                         → TIME_EXIT
5. otherwise                           → HOLD
```

On non-HOLD: exit fill `X` (observed mark, **not** the level), realised P&L `= (X − E) × 65`,
close row, Telegram exit. Gap-through is real — a tick at `0.60·E` against a `0.70·E` SL books
−40%, not −30%. This is why monitor cadence (point 5) and the exit-fill assumption (point 4)
matter.

**Setting `sl_pct` / `tgt_pct` — two routes.**

- _Judgment._ An ATM monthly Nifty option carries ~1–1.5% of spot in premium; a typical 0.5%
  intraday spot move is a ~15–25% premium swing (delta ~0.5 plus gamma). So SL −25/−35% and
  target +40/+60% ≈ "stopped on a ~0.7% adverse move, target on a ~1.2% favourable move."
  Asymmetric favouring the upside fits a directional-conviction entry. Available today.
- _Empirical._ `record_signal_outcome` logs premium-at-close vs entry — it does **not** capture
  intraday MFE / MAE. Proper calibration needs SPT-4 logging peak-favourable and peak-adverse
  excursion per day, then after ~30 closed trades set SL just beyond the median MAE of the
  eventual winners and target near the 60th-percentile MFE. Zero data today (pipeline shipped
  2026-09-09).

**Recommendation into the council:** launch with judgment values — starting proposal
**SL −30% / target +50%, flat (not conviction-scaled)** — explicitly provisional; SPT-4 logs
intraday MFE / MAE from day one; scheduled recalibration after **N = 30** closed paper trades.
A mid-course level adjustment inside the 6-month window is expected, not a failure.

**Question for the council:** are −30% / +50% asymmetric-flat reasonable launch values for a
1-lot intraday long monthly Nifty option off a multi-LLM directional consensus, and is
"judgment now, recalibrate on MFE/MAE at N=30" the right calibration path — or does the
asymmetry / magnitude need rethinking before any paper trade fires?

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
