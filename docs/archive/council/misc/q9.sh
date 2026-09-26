#!/usr/bin/env python3
"""Q9 — Gamma Acceleration + BS Mispricing Option Buying: Signal Hierarchy + Forward Test Protocol
Phase gate: Phase 0 (data schema) → Phase 3 (strategy spec)
Recommended submission order: 9th (last — Phase 3 planning horizon)
"""
import os, pathlib, subprocess, sys

os.chdir(pathlib.Path(__file__).parent.parent)

question = """\
This question validates or refutes a reframed hypothesis for a near-expiry Nifty options buying \
strategy targeting rapid premium expansion events (the '1 to 20' class: options that go from ₹1 \
to ₹20+ in a single session). The operator's original hypothesis attributes these events to \
simultaneous Vega + Gamma spikes plus OI divergence. The reframed hypothesis, submitted here \
for council validation or refutation, is that near 0-2 DTE, Gamma is the correct primary \
signal and Vega is only a regime filter, because: (1) near expiry, Gamma peaks while Vega \
approaches zero — Vega has almost nothing to act on when time value has decayed; (2) a 20x \
premium move from pure IV expansion requires IV to go from 15% to 300% which does not happen \
on NSE index options; (3) the causal mechanism is a Gamma convexity event — the underlying \
moves toward the strike and the option's delta goes from 0.03 to 0.45, driving the premium \
explosion. The reframed signal hierarchy is: PRIMARY = Gamma acceleration (color/speed — rate \
of Gamma change vs time or price), CONFIRMATION = BS mispricing (market ask < Black '76 + \
quadratic smile theoretical premium by a meaningful threshold), FLOW SIGNAL = OI velocity \
(rate of OI change at the strike over 15-30 min), REGIME FILTER = Vega/IV percentile (exclude \
entries when IV is already at its floor). The established Black '76 + quadratic smile + stepped \
repo pricer (council decision 2026-04-30) is the theoretical pricer. Exit is fixed 1:5 R:R. \
Win rate expectation: low (20-35%), compensated by asymmetric payoff. Data collection starts \
now (Phase 0); forward test design + execution is Phase 3. FOUR QUESTIONS: (1) SIGNAL \
HIERARCHY VALIDATION: Is the reframing correct that Vega is irrelevant at 0-2 DTE and Gamma \
acceleration is the only meaningful entry signal? Under what specific conditions (event \
catalysts, 2-3 DTE monthly expiry, VIX circuit conditions) does Vega re-emerge as a primary \
or co-primary signal? What is the correct mathematical measure of Gamma acceleration for a \
5-minute snapshot — color (dGamma/dt), speed (dGamma/dS), or Gamma/premium ratio (convexity \
per rupee of cost)? Is OI velocity an anticipatory signal or a coincident/lagging one relative \
to the premium explosion? (2) MISPRICING THRESHOLD: For a buy signal using ask < Black '76 \
theoretical, what is the minimum absolute INR divergence that is statistically distinguishable \
from smile-fit calibration noise and bid-ask spread noise on a sub-₹5 option? Should \
mispricing be used as the primary signal or as a quality filter applied after Gamma \
acceleration has already triggered? On extreme OTM strikes where the quadratic smile \
extrapolation degrades, is the BS theoretical price reliable enough to serve as a mispricing \
signal at all, or should it be replaced with a simpler measure (e.g., IV percentile rank at \
the strike vs its own 20-day history)? (3) OI SIGNAL CONSTRUCTION: Of three candidates — \
absolute OI concentration (wall strike detection), OI velocity (rapid buildup in 15-30 min = \
positioning), strike-level PCR (put-call OI ratio imbalance at the specific strike) — which \
has the strongest causal link to the near-expiry premium explosion mechanism? Is there a \
combined signal that reduces false positives? Is 5-minute OI delta too noisy for OI velocity, \
and what lookback window handles the mix of new position opens vs expiry-driven closeouts near \
0 DTE? Should the OI signal be directional (call-side OI velocity signals call buy) or \
direction-agnostic (any large OI move signals underlying volatility)? (4) FORWARD TEST \
VIABILITY: At 1:5 theoretical R:R, slippage on a ₹1 option (entry at ask ₹1.40, exit at bid \
₹4.00) reduces realised R:R to approximately 1:1.86, raising the break-even win rate from \
16.7% to ~35%. Is execution via limit orders (entry at mid or below) a practical solution on \
NSE near-expiry options, or does illiquidity at OTM strikes make limit-only execution \
structurally unreliable (orders simply do not fill before the move is over)? Given 2-5 \
qualifying signals per expiry cycle and an expected 20-35% win rate, what is the minimum \
forward test window (number of observed trades) for 95% confidence in positive EV vs a \
binomial null at break-even? For the data schema: beyond the obvious fields (strike, bid, ask, \
OI, delta, gamma, vega, iv, theoretical_price, futures_price, timestamp, expiry), are there \
fields that are cheap to capture at snapshot time but impossible to reconstruct later (order \
book depth, total bid/ask qty) that should be added to the schema now even if not immediately \
used?\
"""

subprocess.run(
    [
        sys.executable, "scripts/ask_council.py",
        "--topic", "gamma-acceleration-mispricing-option-buying",
        "--template", "strategy_parameters",
        "--context", "docs/strategies/csp_nifty_v1.md",
        "--context", "BACKTEST_PLAN.md",
        "--context", "MISSION.md",
        "--timeout", "900",
        "--question", question,
    ],
    check=True,
)
