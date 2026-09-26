#!/usr/bin/env python3
"""Q3 — Variance Gate: Exit-Type Completeness vs Regime Completeness
Phase gate: Phase 0.8 gate / task 1.11
Recommended submission order: 1st (current Phase 0.8 bottleneck)
"""
import os, pathlib, subprocess, sys

os.chdir(pathlib.Path(__file__).parent.parent)

question = """\
The CSP v1 variance gate (Phase 0.8 and task 1.11) requires: (a) ≥6 full monthly expiry cycles; \
(b) at least one profit-target exit, one time-stop exit, and one delta-stop exit triggered; \
(c) |Z| ≤ 1.5 between paper-trade monthly P&L distribution and backtest distribution \
(bias-adjusted). The exit-type completeness criterion (b) was designed to ensure all three exit \
mechanisms have been exercised at least once. The gap this question identifies: what if all 6 \
cycles occur in a benign, range-bound, moderate-IVR regime? The paper distribution would reflect \
one narrow regime slice, and the variance check against the backtest (which covers 8 years \
including COVID, IL&FS, and 2022 selloff) would pass only because both distributions happen to \
be well-behaved in calm markets — not because the strategy's behaviour under stress has been \
validated. Concretely: if the first 6 paper cycles all run May–October 2026, India VIX stays \
12–18 throughout (IVR 20–45), no month sees a ≥5% intraday Nifty decline, and the delta-stop \
never fires despite being a required exit type (just by market luck), the gate would require \
additional cycles. But if IVR stays low, the R3 filter would skip entry, meaning the strategy \
might not even produce 6 cycles in 6 calendar months. The question has two parts: (1) Should \
the gate replace or supplement exit-type completeness with regime completeness (minimum one \
cycle with IVR > 50, minimum one cycle with a ≥5% Nifty intraday drawdown, minimum one cycle \
where delta approaches -0.35 or closer before the profit target fires)? (2) At N=6 monthly \
cycles, what is the statistical power of the |Z| ≤ 1.5 variance check to detect a strategy \
with genuine drift (e.g., a 2-SD structural shift in mean return)? Is N=6 sufficient to trust \
a passing Z-score, or does the deployment decision need a secondary criterion (e.g., month-2 \
informal check + graduated deployment tiers) to compensate for the thin sample?\
"""

subprocess.run(
    [
        sys.executable, "scripts/ask_council.py",
        "--topic", "variance-gate-regime-completeness",
        "--template", "strategy_parameters",
        "--context", "docs/strategies/csp_nifty_v1.md",
        "--timeout", "900",
        "--question", question,
    ],
    check=True,
)
