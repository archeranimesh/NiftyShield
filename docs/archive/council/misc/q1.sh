#!/usr/bin/env python3
"""Q1 — CSP v2 Entry Delta: 20-delta vs 25-delta
Phase gate: Phase 0 → 1 (task 1.7 config)
Recommended submission order: 2nd (after Q3)
"""
import os, pathlib, subprocess, sys

os.chdir(pathlib.Path(__file__).parent.parent)

question = """\
CSP v1 targets 25-delta monthly Nifty puts (65-unit lot, 30–45 DTE, 21-day hold, R2 delta-stop \
at -0.45, R7 slippage model). After 6+ paper cycles, the exit-type frequency will reveal \
stop-firing rates. The v2 question is whether 20-delta is structurally superior for this \
specific setup. The design dimensions that change at 20-delta vs 25-delta: (a) credit collected \
(~30–35% less at 20-delta in a 30–35 IVR environment); (b) delta-stop firing frequency \
(roughly halves — 20-delta sits at a lower gamma region throughout the 21-day hold); \
(c) theta-to-gamma ratio at 21 DTE (20-delta is more favourable — lower gamma acceleration \
during the peak-theta window); (d) bid-ask spread as % of premium (widens at 20-delta, \
degrading slippage economics). The 21-day hold period is the key differentiator from a \
standard 50%-profit-target CSP: the system holds into peak gamma intentionally, making the \
choice of starting delta load-bearing for tail risk. The R2 delta gate at -0.45 fires when \
the put is already deep ITM; at 20-delta entry, the journey from -0.20 to -0.45 requires a \
larger Nifty decline, reducing stop frequency but also reducing the early-warning function of \
the gate. Question: What is the theoretically optimal entry delta for a monthly Nifty CSP with \
a fixed 21-day hold period, a -0.45 delta-stop, and a 50%-profit-target, when validated over \
the Indian market's specific skew structure and FII-flow-driven trend regime? Should the v2 \
decision wait for paper trade exit-type data (is N=6-8 sufficient?) or can the answer be \
derived analytically from the known Nifty vol surface properties?\
"""

subprocess.run(
    [
        sys.executable, "scripts/ask_council.py",
        "--topic", "csp-entry-delta-v2",
        "--template", "strategy_parameters",
        "--context", "docs/strategies/csp_nifty_v1.md",
        "--timeout", "900",
        "--question", question,
    ],
    check=True,
)
