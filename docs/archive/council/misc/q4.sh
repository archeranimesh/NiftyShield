#!/usr/bin/env python3
"""Q4 — Gap Fade VIX-IVP Filter: 75th Percentile vs Alternatives
Phase gate: Phase 2 (swing signal generator)
Recommended submission order: 6th
"""
import os, pathlib, subprocess, sys

os.chdir(pathlib.Path(__file__).parent.parent)

question = """\
Strategy 3 (Mean-Reversion Overnight Gap Fade) in the swing strategy pipeline uses a VIX-IVP \
filter: skip the signal when India VIX's 63-day trailing percentile rank (IVP) is ≥ 75th \
percentile. Strategy 2 (ORB) uses 90th percentile for its VIX structural exclusion \
(council-reviewed 2026-05-01). The asymmetry — 75th for Gap Fade vs 90th for ORB — was never \
council-reviewed. It reflects the intuition that gap fades degrade more continuously with \
rising IV (because correlated gaps increasingly carry real information at moderate IV levels), \
while ORB only degrades at the extreme tail (where pre-event positioning dominates the OR). \
The question has three parts: (1) THEORETICAL BASIS: Is the 75th/90th asymmetry well-grounded? \
The Gap Fade hypothesis (GIFT Nifty → NSE open gap is correlation-driven, not \
information-driven, for gaps 0.3%–1.0%) degrades in high-IV regimes because those regimes \
correlate with genuine information-flow (global risk-off, EM capital flight, RBI surprises). \
At what VIX-IVP level does the GIFT→NSE correlation cease to be the dominant driver of the \
gap? Is this at the 75th percentile (~IVP 63-day rank ≥ 75%) or at a different level? \
(2) STATISTICAL IMPACT: Gap Fade targets 60–100 trades/year after the gap-size filter \
(0.3%–1.0%). With a 75th percentile VIX filter excluding ~25% of days vs 90th excluding ~10%, \
expected qualifying trades fall from ~60–100 to ~45–75. The walk-forward minimum is 10 trades \
per 252-day window. Is there a risk that the 75th threshold makes some rolling windows \
insufficient (fewer than 10 trades), triggering the >25% insufficient-window kill condition \
even if the strategy has genuine edge? (3) UNIFIED FILTER: Should ORB and Gap Fade use the \
same VIX-IVP threshold (for implementation simplicity and shared regime classification), or \
does each strategy's distinct failure mode justify different thresholds? If different thresholds \
are used, what should each be?\
"""

subprocess.run(
    [
        sys.executable, "scripts/ask_council.py",
        "--topic", "gap-fade-vix-filter-threshold",
        "--template", "strategy_parameters",
        "--context", "docs/plan/SWING_STRATEGY_RESEARCH.md",
        "--timeout", "900",
        "--question", question,
    ],
    check=True,
)
