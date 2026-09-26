#!/usr/bin/env python3
"""Q8 — Nifty Long Instrument Comparison: ETF vs Futures vs ITM Option + Protection Overlay
Phase gate: Phase 0–1 (paper trading framework design)
Recommended submission order: 3rd (concurrent with Q1, before paper_nifty_* strategies registered)
"""
import os, pathlib, subprocess, sys

os.chdir(pathlib.Path(__file__).parent.parent)

question = """\
This question designs a 3-track paper trading and backtesting comparison framework for Nifty \
long exposure combined with protection strategies. The operator already holds NiftyBees ETF \
(~5,725 units, ₹15.5L, pledgeable as margin collateral), and runs CSP paper trading on Nifty \
monthly puts. The new framework runs 3 separate tracks simultaneously in paper trading: Track A \
= Long NiftyBees ETF (1 lot equivalent, ~₹15.5L physical holding), Track B = Long Nifty \
Futures (1 lot, near-month, rolled monthly), Track C = Long Nifty via ITM option (structure \
TBD by council). On top of each track: protective puts (buy OTM Nifty put), covered calls \
(sell OTM Nifty call), CSP (short Nifty put at ~25 delta in correlation with existing paper \
strategy), and any additional structures the council recommends. FOUR QUESTIONS FOR THE \
COUNCIL: (1) ITM OPTION STRUCTURE FOR TRACK C: The operator wants to simulate Nifty futures \
exposure via an option. Three candidates: (a) Deep ITM call at ~2000-2500 points ITM, delta \
~0.90, premium ~₹2-3L, single leg — has theta decay but no roll cost; (b) Synthetic long \
(buy ATM call + sell ATM put at same strike, near-zero net premium, delta ~1.0, margins like \
futures) — true futures proxy but the short put leg creates overlap with the CSP overlay \
strategy (CSP + synthetic long = 2 short puts at different strikes); (c) Near-ATM call at \
~1000-1500 points ITM, delta ~0.70, premium ~₹1-1.5L — cheaper but more theta drag and lower \
delta fidelity. Which structure is most cost-effective for a 12-month paper trading comparison \
where the purpose is to overlay protection strategies (protective put, covered call, CSP) and \
compare with Track A/B? Cost-effectiveness must account for: total cost of carry including \
theta decay, margin capital locked, interaction with the CSP overlay (avoid creating unintended \
double short-put positions), and how cleanly the protective strategies work on each structure. \
(2) OVERLAY STRATEGY INTERACTION MATRIX: For each of the 3 base instruments, describe how \
each overlay strategy changes the combined portfolio Greeks and P&L characteristics: (a) Long \
NiftyBees + protective put: standard protective put, delta decreases as Nifty falls below \
strike — textbook. (b) Long NiftyBees + covered call: standard covered call, upside capped — \
textbook. (c) Long Nifty Futures + protective put: same delta profile as (a), but futures P&L \
is linear (no intrinsic value, no theta on the base position) — the combination is a synthetic \
long call. (d) Long Nifty Futures + covered call: futures + short call = synthetic short put — \
creates significant downside risk without the protective put present. (e) Long deep-ITM call \
(delta 0.90) + protective put: effectively a bull call spread (long high-delta call + long \
low-delta put is equivalent to long call spread after Greek decomposition). The combined Vega \
and theta change dramatically. (f) Long deep-ITM call + covered call (short OTM call): \
calendar diagonal spread or vertical spread depending on expiry. Are there any combinations in \
this matrix that are structurally dangerous (e.g., create unlimited downside) or that are \
redundant (e.g., the combination of overlay + base instrument is equivalent to a simpler \
structure that can be entered directly at lower cost)? (3) ADDITIONAL PROTECTION STRUCTURES: \
Beyond protective puts, covered calls, and CSP, what other structures are worth paper-trading \
and backtesting in this framework, given the operator's profile (retail, single operator, \
Nifty 50 index options, 1-lot scale, ₹1.2cr collateral pool)? Specifically evaluate: collars \
(protective put + covered call simultaneously — net cost lower than protective put alone), \
ratio spreads (buy 1 ATM put, sell 2 OTM puts — zero cost but creates a net short put below \
the lower strike), and any structure that benefits from Nifty's well-documented negative skew \
(IV premium on puts vs calls) while providing defined downside protection. (4) DAILY P&L \
REPORT DESIGN: For a daily mark-to-market report covering all 3 tracks + their overlays, what \
metrics are essential for the comparison to be meaningful? Specifically: (a) should base \
position P&L and overlay strategy P&L be reported separately within each track (so you can see \
'NiftyBees lost ₹8,500 today, protective put gained ₹12,000, net ₹3,500') or as a combined \
single-track P&L? (b) Should the report include a cross-track comparison (which track is ahead \
on total P&L, which has the lowest drawdown) and if so, how should the capital basis be \
normalised across tracks (NiftyBees requires ₹15.5L capital, futures requires only ₹1.5L \
margin — the raw P&L comparison is misleading without capital normalisation)? (c) What is the \
minimum set of Greeks (delta, theta, vega at portfolio level per track) that should be reported \
daily to make the comparison actionable rather than just historical?\
"""

subprocess.run(
    [
        sys.executable, "scripts/ask_council.py",
        "--topic", "nifty-long-instrument-comparison-protection",
        "--template", "strategy_parameters",
        "--context", "docs/strategies/niftyshield_integrated_v1.md",
        "--context", "docs/strategies/csp_nifty_v1.md",
        "--context", "docs/plan/INVESTMENT_STRATEGY_RESEARCH.md",
        "--context", "MISSION.md",
        "--context", "REFERENCES.md",
        "--timeout", "900",
        "--question", question,
    ],
    check=True,
)
