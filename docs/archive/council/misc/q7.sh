#!/usr/bin/env python3
"""Q7 — Continuous Re-Validation: Statistical Power at Low N and Early Deployment
Phase gate: Phase 2 (task 2.1 design)
Recommended submission order: 4th (parallel with Q1/Q8, before first live trade)
"""
import os, pathlib, subprocess, sys

os.chdir(pathlib.Path(__file__).parent.parent)

question = """\
Task 2.1 in BACKTEST_PLAN.md specifies weekly Z-score monitoring for live strategy \
re-validation: compute rolling Z-score = (live_mean_monthly_pnl − backtest_mean) / \
backtest_std, with alert thresholds at |Z| 1.5–2.0 for 3 consecutive weeks (reduce to \
paper-only) and |Z| > 2.0 single week (halt all live trading). The problem: the CSP strategy \
completes ~1 trade per month, which is ~12 data points per year and ~6 by the time live \
deployment starts. At N=6, a Z-score computed against a backtest distribution of 96 monthly \
observations (8 years × 12 months) has extremely low statistical power. Concretely: a strategy \
that has genuinely drifted 1.5 sigma from its backtest mean will only be detected with ~40–50% \
probability at N=6 (standard power analysis). Conversely, a correctly functioning strategy will \
produce |Z| > 1.5 by pure variance approximately 13% of the time at any given monthly check. \
At weekly Z-score monitoring frequency (about 4 checks per month), the false-positive \
probability over the first 3 months of live trading is substantial. Three specific questions: \
(1) MONITORING METHOD: Is a standard rolling Z-score the right method for a strategy with ~12 \
observations per year, or should a CUSUM (Cumulative Sum Control Chart) or Shiryaev-Roberts \
sequential test be used instead? CUSUM is specifically designed for small-N sequential \
monitoring and has a lower false-alarm rate at equivalent detection delay. If CUSUM is \
appropriate, what are the recommended h (threshold) and k (reference value) parameters for \
the CSP's expected return and standard deviation profile? (2) MINIMUM N BEFORE Z-SCORE IS \
INFORMATIVE: At what N does the Z-score first achieve sufficient statistical power (β ≥ 0.80 \
at the 1.5-sigma alternative) to be decision-relevant? Should the halt/reduce protocol from \
the PM review apply from day one, or only after this minimum N is reached? (3) EARLY \
DEPLOYMENT GUARD: During the period before minimum N is reached, what alternative monitoring \
metric should serve as the primary safety signal? The CSP spec already has per-cycle kill \
criterion R6 (single cycle loss > 3× trailing-12-cycle average credit → automatic pause). Is \
R6 sufficient as the sole guard during early deployment, or does it need to be supplemented \
with a rolling drawdown check or regime-divergence flag?\
"""

subprocess.run(
    [
        sys.executable, "scripts/ask_council.py",
        "--topic", "continuous-revalidation-statistical-power",
        "--template", "backtest_methodology",
        "--context", "docs/strategies/csp_nifty_v1.md",
        "--timeout", "900",
        "--question", question,
    ],
    check=True,
)
