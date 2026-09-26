# Signals Paper Track — Execution Layer: Module Boundary, Trade Rules, Cadence, Go-Live Gate

## System Context

The `signals/` epic (shipped 2026-09-09) runs a daily multi-LLM directional call on Nifty: at
~09:30 three models (GPT-4o / Grok / Gemini, via OpenRouter) vote, `SignalAggregator` produces
a consensus `DailySignal` (`trade_action` ∈ {BUY_CALL, BUY_PUT, NO_TRADE}, a
`recommended_strike`, a confidence), and `scripts/record_signal_outcome.py --auto` records at
16:00 what a trade *would* have returned — premium-at-close vs the entry-band premium. There is
no position, no intraday management, no fill. It is a backtest-by-hand.

The `signals-paper-track` story (SPT-1..SPT-8, `docs/plan/signals-paper-track/`) turns this into
a live paper-traded strategy: auto-enter the consensus each day it fires as a **1-lot long
monthly Nifty option**, manage it intraday against a stop-loss / target, exit on a hit or
square off by 15:00, persist every entry and exit, push both to Telegram, and after ~6 months
evaluate the realised paper P&L against a go-live gate. SPT-1 is a planning-phase council
checkpoint — no code — whose ruling rewrites SPT-2..SPT-8.

**Already decided by the operator, NOT for the council to reopen** (recorded in
`docs/plan/signals-paper-track/council-question.md` and `prompt.md`):

| Parameter | Decision |
|---|---|
| Expiry | Monthly, near-month; roll to next month at **≤ 7 DTE**, uniform via a ≤ 7-DTE roll added to `src/signals/option_resolver.py::resolve_monthly_option` (shared by the paper track and `record_signal_outcome.py`; `get_expiry_candidates` and its `dte >= 14` floor untouched — those are shared by the finideas overlays / IC / chain pipelines). |
| Position size | Fixed 1 lot (Nifty lot 65, DECISIONS.md 2026-08-10). |
| Time exit | Hard 15:00 square-off, no overnight hold. Intraday-only ⇒ theta is a minor cost, bid/ask the dominant one. |
| SL / target basis | % of entry premium (levels are open — see Q2). |
| Entry timing | Immediately on the aggregated `DailySignal`. |
| Intraday fill model | Reuse `PaperFillSimulator` (`src/strategy/executor.py`) unchanged — `mid ± s`, VIX-banded `s` (₹1.5 default), BUY at `mid + s`, SELL at `mid − s`, `mid` = real `(bid + ask) / 2`. Consistent with the CC / CSP / IC paper strategies; defers to the 2026-04-30 slippage-model ruling. OI multiplier n/a (ATM strike ⇒ 1.0×). SL 1.5× exit multiplier deferred to the N = 30 review. **Not a council question.** |

**Relevant existing machinery** (for Q1):

- `src/strategy/monitor.py::StrategyMonitor` — one-instance daemon (`scripts/monitor_daemon.py`),
  registered strategies polled every `poll_interval_s` tick (default **90 s**); WARN dedup;
  auto-execute dispatch.
- `src/strategy/executor.py::PaperExecutor` / `PaperFillSimulator` — `LegSpec` → synthetic fill
  → `PaperStore` row.
- `src/strategy/exit_signals.py`, `ExitSignalEngine`, `ProfitLockEngine` — exit evaluators built
  for short-premium / delta-neutral structures (`DELTA_STOP`, `LOSS_STOP`, IVR-tiered rolls,
  the IC-V2 25/50/75 % capture-zone profit lock).
- `src/paper/` — `PaperStore` (`paper_trades`, `paper_leg_snapshots`, `paper_exit_events`,
  `TradeState`), `PaperTracker`, selectors. `src/reporting/eod_pt_summary.py` reads
  `PaperStore.get_positions()`.
- Prior ruling: `signals/` was decoupled **from `src/backtest/`** (2026-09-07, DECISIONS.md
  line 642) — "own SQLite tables, no `src/backtest/` import". It said nothing about `src/paper/`
  or `src/strategy/`. The paper-track roadmap already carries a planned "PT-S2 Signal Pipeline"
  slot (DECISIONS.md line 84).

## The decisions to resolve

### Decision 1 — Module boundary (data-architecture)

- **A — signals becomes a `PaperStrategy`, reusing `src/strategy/` + `src/paper/`.** Reuses the
  `StrategyMonitor` tick loop, `PaperExecutor` / `PaperFillSimulator`, `PaperStore` /
  `paper_trades` / `TradeState` / `paper_exit_events`. `eod_pt_summary` picks the track up for
  free. A single long option is the degenerate-simplest case for these abstractions (built for
  multi-leg delta-neutral structures). Costs: (i) an adapter `DailySignal` → `SignalEvent` /
  `ApprovedAction` / `LegSpec`; (ii) **a new exit evaluator is needed regardless** —
  `ExitSignalEngine`'s vocabulary does not map to a naked long with %-premium SL / target;
  (iii) the signal position's model rides `PaperTrade` / `PaperPosition` evolution.
- **B — self-contained monitor + exit loop in `src/signals/`, own table.** Purpose-built for
  one shape. Costs: reimplements tick-loop mechanics that exist and are tested; a second daemon
  to supervise.

Operator's current lean: **A**, on the grounds that B's usual justification (the independence
ruling) was scoped to `src/backtest/` only, and folding the signal into the paper engine was
always the intended direction ("PT-S2").

### Decision 2 — SL / target launch levels (strategy-parameters)

Basis is fixed (% of entry premium `E`); `sl_price = E·(1 − sl_pct)`, `tgt_price = E·(1 + tgt_pct)`.
No live data exists (pipeline shipped 2026-09-09). Operator's starting proposal:
**SL −30 % / target +50 %, flat (not confidence-scaled), both fixed** — provisional, with
SPT-4 logging intraday MFE / MAE from day one and a scheduled recalibration after **N = 30**
closed paper trades.

### Decision 3 — Phase 1 fixed exit vs dynamic exit now (strategy-parameters)

Operator's position: **Phase 1 ships `TARGET` / `STOP_LOSS` / `TIME_EXIT` / `HOLD` only — no
breakeven bump, no trailing.** Rationale: ratcheting the stop up while the target stays at
+50 % is incoherent (machinery added, winner still capped); a dynamic exit must move SL *and*
target together (or a capture-zone ratchet replaces both) and needs the MFE / MAE distribution
to design honestly. Precedent: `IronCondorV2` shipped Phase 1 with **no** `profit_target_fraction`
(`src/strategy/ic_expiry_config_v2.py:133`) and added the `ProfitLockEngine` as a separate
later story under its own council ruling (`docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md`).
The exit-reason enum reserves a `TRAILING_STOP` member now so `schema.md` does not churn.

### Decision 4 — Monitor cadence (strategy-parameters)

Operator's position: run the 6-month paper phase at `StrategyMonitor`'s inherited **90 s tick**
— no new loop under A — and log the full mark path (`ts`, `ltp`, `bid`, `ask`, `unrealised_pct`,
running `mfe_pct` / `mae_pct`) at every tick. After 6 months, use that logged path to check
whether a tighter cadence (30 s / 15 s) would have changed any fill materially, and tighten
only if the data says so.

### Decision 5 — Go-live gate metrics (risk)

SPT-7 builds a pass/fail report over a `--from` / `--to` window. No prior exists for this
track. Adjacent reference: the Phase 0.8 Variance Gate tiers (DECISIONS.md 2026-05-02) gate the
*IC* strategy on N ≥ 12 cycles, regime-matched |Z| ≤ 1.5, all exit paths validated. The signal
track is a different animal — one intraday long per day, ~120 trading days in 6 months.

---

## Q1 — Module boundary: is A correct, and does the naked-long exit logic justify any carve-out?

Given the independence ruling was `src/backtest/`-scoped only and a new exit evaluator is needed
under either option, is **A** (signals as a `PaperStrategy` on the shared engine) the right
call? If yes: should the new %-premium SL / target / time-exit evaluator live as a distinct
module (e.g. `src/signals/paper_exit.py`) invoked from the `PaperStrategy`, or be added to
`ExitSignalEngine` as another signal family? And is a distinct `paper_trades.strategy_name`
namespace (`signal_track_v1`) plus the reserved `TRAILING_STOP` enum member sufficient
isolation, or does the single-leg-long shape need its own table after all? If the council
prefers **B**, what specifically about the shared engine fails for this vehicle that outweighs
running and supervising a second monitor process?

## Q2 — Are SL −30 % / target +50 % flat reasonable launch values, and is "recalibrate at N = 30" the right path?

For a 1-lot intraday long monthly Nifty option (delta ~0.5, ~15–35 DTE after the ≤ 7-DTE roll)
entered off a 3-model directional consensus and squared off by 15:00: are −30 % / +50 %
asymmetric-flat sensible provisional levels, or does the asymmetry / magnitude need changing
before any paper trade fires? Should the levels instead be a function of the underlying's
recent realised range (e.g. a fraction of the 20-day ATR expressed through option delta), or of
the signal's own confidence score? Is N = 30 closed trades enough to recalibrate against the
MFE / MAE distribution, or is the right trigger a fixed calendar point (e.g. 3 months) or a
statistical-power threshold?

## Q3 — Confirm Phase 1 ships fixed-exit-only, with the dynamic exit as a separate post-data story?

Is the operator's fixed-only Phase 1 correct — i.e. no breakeven bump and no trailing until the
MFE / MAE data exists — mirroring how IC-V2 deferred its profit lock? Or is there a specific,
low-regret dynamic element (e.g. a pure breakeven stop after +X % unrealised, which never
*worsens* an outcome) that should ship from day one? When the Phase 2 dynamic exit is designed,
which shape is more appropriate for a naked long: a two-stage trail that *also* lifts the target
as the position trends, or an IC-V2-style discrete capture-zone ratchet?

## Q4 — Is a 90 s evaluate cadence acceptable for this vehicle during the paper phase?

The 90 s `StrategyMonitor` default was set for credit-spread strategies with far less intraday
gamma exposure. A naked long option can move sharply on an event (RBI, a data print, a gap),
and 90 s between ticks is 90 s of unobserved gap-through risk on the stop. For a **paper** phase
whose explicit purpose is to gather the movement data (full path logged every tick), is 90 s an
acceptable evaluate cadence with the cadence question revisited from data before any live
promotion — or must the paper track evaluate exits on a tighter cadence from the start to
produce a faithful P&L series? If tighter: what value, and does it warrant a dedicated sub-loop
rather than the shared 90 s tick?

## Q5 — Propose the 6-month go-live gate metrics

There is no prior for promoting this track to live. Propose the gate SPT-7 should test against,
covering at minimum: the evaluation window (assume 6 months / ~120 signal days), minimum closed
trade count, the P&L / expectancy threshold (net of the modelled slippage), a win-rate or
profit-factor floor, a maximum-drawdown ceiling, and whether promotion requires *all* criteria
to pass or a composite score. Should the gate also require regime coverage (at least one
elevated-VIX stretch inside the window), a minimum number of stop-loss exits actually
experienced, or agreement between the paper track's realised P&L and the parallel
`record_signal_outcome` advisory series? What is the right live-pilot constraint on first
promotion (size, manual approval per entry, duration)?

---

## Required Council Output Format

```
## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Module boundary — A (PaperStrategy on shared engine) vs B (self-contained loop) | |
| If A: home for the %-premium SL/target/time-exit evaluator | |
| If A: isolation sufficient (namespace + reserved enum) or own table | |
| SL / target launch levels (sl_pct / tgt_pct, flat vs scaled) | |
| Recalibration trigger (N=30 / calendar / statistical power) | |
| Phase 1 fixed-only vs a low-regret dynamic element from day one | |
| Phase 2 dynamic-exit shape (two-stage trail+target vs capture-zone ratchet) | |
| Monitor evaluate cadence for the paper phase (90 s vs tighter) | |
| Go-live gate — window, min N, P&L/expectancy, win-rate/PF, max DD, all-pass vs composite | |
| Go-live gate — regime coverage / min stop-loss count / advisory agreement required? | |
| First live-pilot constraint (size / approval / duration) | |

## Design Rationale
[Why the recommended module boundary is correct given the src/backtest-scoped independence
ruling, the "PT-S2" roadmap intent, and the fact that a new exit evaluator is needed either
way. Why the recommended SL/target levels and calibration path fit a 1-lot intraday long
monthly Nifty option off a multi-LLM consensus.]

## Exit-Design Detail
[Explicit position on whether any dynamic exit element should ship in Phase 1, and the
preferred Phase 2 shape, with the reasoning tied to a naked long's unbounded-upside /
capped-downside payoff versus IC-V2's defined-risk credit structure.]

## Go-Live Gate Specification
[The concrete gate: every threshold with a number or a formula, the pass rule, and what data
SPT-7 must compute. Name any metric that cannot be reliably estimated from ~120 signal days
and what to do about it.]

## Dissenting Notes
[Panel disagreements — particularly on module boundary (reuse vs independence) and on whether
90 s cadence materially distorts the paper P&L for a naked long.]
```
