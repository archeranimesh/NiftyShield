#!/usr/bin/env python3
"""Q5 — Iron Condor v1: Core Design on Nifty Given the Put-Call Skew
Phase gate: Phase 2 (task 2.3 IC spec)
Recommended submission order: 7th
"""
import os, pathlib, subprocess, sys

os.chdir(pathlib.Path(__file__).parent.parent)

question = """\
The Iron Condor (IC) is the planned Phase 2 strategy in NiftyShield. Its specification (task \
2.3) has not been written. The system uses Nifty 50 monthly options, same collateral \
infrastructure as CSP (csp_nifty_v1.md, see context file), 1 lot at Phase 2 entry (currently \
65 units but verify against NSE lot schedule). Three core design decisions need council input \
before writing the spec: (1) SYMMETRIC vs ASYMMETRIC DELTA TARGETS: Nifty has a persistent \
put skew — at 30 DTE, the 15-delta put typically carries 3–6 IV points more than the 15-delta \
call. A symmetric IC (e.g., -0.15 put / +0.15 call both sides) collects equal credit from both \
wings despite structurally different risk (Nifty's tail risk is asymmetric — sharp declines \
more frequent than sharp rallies of the same magnitude). An asymmetric IC (-0.20 put wing / \
-0.10 call wing) charges the put side more aggressively, matching credit collection to the \
premium richness of the skew, while keeping the call side tighter to reduce false stop-outs \
from occasional strong rallies. Which approach is appropriate for Nifty given its skew \
structure and FII-driven trend character? (2) ADJUSTMENT RULE: CSP v1 has no adjustments (by \
design — simplicity and backtestability). Should IC v1 also have no adjustments? The risk: a \
trending Nifty (55–60% of years) drives one IC wing deep ITM without an adjustment mechanism, \
producing 100% max loss on the breached spread far more often than a range-bound index would. \
The alternative: a defined delta-gate adjustment (roll the breached spread when the net IC \
delta exceeds ±0.15) — but this requires a defined roll strike, adds execution complexity, and \
makes the backtest significantly harder to implement. Without adjustment, the IC may fail the \
OOS Calmar threshold in trending regimes simply by design. (3) PORTFOLIO INTERACTION WITH CSP: \
When CSP (short put) and IC (short put spread) are running concurrently, the combined net delta \
has double put exposure. Should the IC's put spread be sized to net the portfolio to \
approximately delta-neutral after accounting for the CSP short put, or should each strategy be \
sized independently with the SPAN margin system managing the combined exposure? Specify the IC \
v1 design that produces the highest probability of passing the walk-forward Calmar ≥ 0.7 \
threshold on 8 years of Nifty monthly options history, while remaining operationally manageable \
for a single retail operator.\
"""

subprocess.run(
    [
        sys.executable, "scripts/ask_council.py",
        "--topic", "iron-condor-v1-core-design",
        "--template", "strategy_parameters",
        "--context", "docs/strategies/csp_nifty_v1.md",
        "--timeout", "900",
        "--question", question,
    ],
    check=True,
)
