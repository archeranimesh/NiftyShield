# IC Time-Stop DTE: Entry-Scaled Tiers vs. Uniform Terminal Window

## System Context

`IronCondorV1` (`src/strategy/ic_nifty_v1.py::check_signals`) evaluates `TIME_STOP` (ACTION,
auto-executes via `_auto_select_action`, priority CLOSE_FULL > partial spread close) when
`dte <= config.time_stop_dte`, and `DTE_WARN` (INFO only) when `dte <= config.dte_warn`. Both
thresholds are per-expiry-bucket, defined in `ICExpiryConfig`/`CONFIGS`
(`src/strategy/ic_expiry_config.py`):

| Bucket | Entry DTE window (`dte_warn_lo`–`dte_warn_hi`) | `time_stop_dte` | `dte_warn` | Wing width | Short deltas (P/C) |
|---|---|---|---|---|---|
| weekly | 5–8 | 2 | 4 | 200 pts | 0.10 / 0.08 |
| monthly | 30–45 | 14 | 21 | 500 pts | 0.15 / 0.10 |
| leaps (quarterly) | 60–90 | 45 | 60 | 1000 pts | 0.15 / 0.10 |
| yearly | 180–270 | 60 | 90 | 1500 pts | 0.12 / 0.08 |

These numbers were introduced in `docs/archive/ic-multi-expiry/stories/IC-M1.md` on the
stated assumption that "Leaps and yearly ICs need substantially wider time buffers" — no
backtest, empirical theta-decay curve, or NSE liquidity data backs the specific values; they
were linearly scaled up from the monthly preset (14/45 → time_stop/entry ratio ≈0.31) without
re-deriving the ratio per bucket. `time_stop_dte < dte_warn` is enforced as a structural
invariant (`test_ic_expiry_config.py::test_time_stop_lt_dte_warn`) but nothing else constrains
the values.

Separately, `src/strategy/exit_signals.py`'s `evaluate_cc`/`evaluate_pp` (single-leg NiftyBees
overlays — Covered Call, Protective Put, Collar) use one **fixed DTE_REVIEW ≤ 5** threshold
regardless of entry tenor, per council ruling `docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md`
(Stage 3, Q1c): "Time-stops mathematically supersede percentage targets near expiry because
gamma-risk outweighs residual theta... Implement DTE_REVIEW (DTE ≤ 5) for CCs." That ruling
was ratified for CC/PP/Collar, not for IC.

## The disagreement to resolve

**Position A (entry-scaled tiers, current IC design):** longer-dated contracts warrant wider
absolute buffers because more DTE was originally on the table, and/or because far-tenor NSE
Nifty option strikes (quarterly/yearly) carry materially thinner open interest than
weekly/monthly even at comparable DTE, so exiting earlier avoids a liquidity cliff unique to
those buckets.

**Position B (uniform terminal window, operator's proposed revision):** gamma/pin risk is a
property of *the specific contract's own remaining DTE*, not of how much DTE existed at entry —
a quarterly leaps contract 5 days from its own expiry faces the same terminal dynamics as a
monthly contract 5 days from its own expiry. Under this view, IC should mirror the CC/PP/Collar
DTE_REVIEW ≤ 5 design: exit ~5 DTE (weekly's Tuesday-expiry calendar makes its current
`time_stop_dte=2` already behave as a 1-DTE/Monday exit in practice, since DTE 2–3 never lands
on a trading day) for monthly/leaps/yearly alike, if PROFIT_TARGET/LOSS_STOP/DELTA_STOP haven't
already closed the position first.

**Operator's additional objection to Position A specifically:** for the monthly bucket, actual
paper-trading practice holds the position roughly 10–15 days before `time_stop_dte=14` (or an
earlier signal) closes it — i.e., held duration is already short relative to the theoretical
30–45 DTE entry window. If monthly's realized behavior is "hardly in trade" for most of its
nominal DTE life, the operator argues the premise that longer-dated buckets need proportionally
*more* buffer (leaps: 45, yearly: 60) is unsupported — the same short-hold pattern could apply
across buckets, and the wider buffers may just be truncating theta capture on leaps/yearly
without a compensating risk benefit, exactly as monthly's own behavior fails to demonstrate the
benefit for itself.

## Q1 — Is DTE-proportional buffer scaling justified, or is a uniform terminal-DTE rule correct?

Should `time_stop_dte` remain scaled to each bucket's entry DTE window (current: 2/14/45/60),
or should IC adopt a single terminal-DTE rule close to expiry (e.g., 5 DTE, or some other fixed
value) uniformly across monthly/leaps/yearly, mirroring the CC/PP/Collar DTE_REVIEW ruling? If
scaling is justified, what should actually drive the scale factor — NSE liquidity data by
tenor, gamma/theta curve shape, capital velocity (ROI per day of margin deployed), or something
else — rather than the linear extrapolation IC-M1 currently uses?

## Q2 — Does IC's defined-risk structure change the CC/PP/Collar precedent's applicability?

The 2026-06-26 ruling's "gamma-risk outweighs residual theta" logic was derived for CC/CSP —
undefined or stock-hedged risk profiles where near-expiry gamma/pin exposure is a genuine tail
risk. IC is a defined-risk spread (long wings cap max loss to `wing_width − net_credit`
regardless of DTE). Does that structural difference mean IC can safely hold closer to expiry
than CC ever could, making 5 DTE conservative rather than necessary for IC — or does pin risk
against the *short* strike (not the capped tail) still justify an early exit independent of the
defined-risk ceiling?

## Q3 — Does far-tenor NSE liquidity actually degrade faster near expiry than near-tenor liquidity?

Is there a real NSE microstructure basis for believing quarterly/yearly Nifty strikes have worse
bid-ask spreads/depth in their final ~5–14 DTE than monthly strikes do in theirs — which would
support keeping leaps/yearly's wider buffer specifically for execution-quality reasons, separate
from the gamma argument — or is this an untested assumption that should be checked against
actual NSE option-chain spread data (by DTE bucket, split by tenor) before being used to justify
a wider buffer?

## Q4 — Is the operator's "monthly is already short-held" observation evidence for or against scaling?

If monthly IC positions are typically closed well before `time_stop_dte=14` (via PROFIT_TARGET,
DELTA_STOP, or ROLL_WING/LOSS_STOP) such that the time-stop rarely binds, does that observation
say anything reliable about whether leaps/yearly's wider buffers are correctly or incorrectly
sized — or is it a sample-selection artifact (time-stops binding rarely by design, precisely
because other signals are supposed to fire first) that doesn't actually bear on the DTE-tiering
question either way?

## Required Council Output Format

```
## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Entry-scaled tiers vs. uniform terminal-DTE rule | |
| If uniform: recommended DTE value | |
| If scaled: recommended basis for the scale factor | |
| IC defined-risk structure — does it change the CC/PP/Collar precedent? | |
| Liquidity-by-tenor claim — supported or unverified assumption? | |
| Weight given to operator's monthly short-hold observation | |
| Recommended validation approach (data / backtest / neither) | |

## Design Rationale
[Why the recommended time-stop design is correct given IC's defined-risk structure, the
CC/PP/Collar precedent, and the entry-DTE-scaling assumption in IC-M1]

## Liquidity/Execution Detail
[Explicit assessment of whether far-tenor (quarterly/yearly) Nifty strikes need wider exit
buffers than near-tenor strikes for execution-quality reasons, and what data would confirm it]

## Dissenting Notes
[Panel disagreements, particularly on whether IC's defined-risk profile meaningfully changes
the near-expiry gamma-risk calculus relative to CC/PP/Collar]
```
