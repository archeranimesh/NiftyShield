#!/usr/bin/env python3
"""Q2 — NiftyShield Integrated: Leg 2 Protective Put Spread Strike Methodology
Phase gate: Phase 1 (task 1.9 synthetic pricer)
Recommended submission order: 5th
"""
import os, pathlib, subprocess, sys

os.chdir(pathlib.Path(__file__).parent.parent)

question = """\
The NiftyShield Integrated strategy (see context file) uses Leg 2 (protective put spread) with \
strikes defined as fixed percentages of spot: long put at 8% below spot (activation threshold), \
short put at 20% below spot (tail cap). The 4-lot sizing is calibrated to hedge 65% of ₹100L \
effective Nifty exposure. The open question for v2 is whether strike selection should switch to \
delta-based (long put at 15-delta, short put at 5-delta). The competing considerations: \
(1) REGIME SENSITIVITY: %OTM selects a fixed nominal price zone regardless of vol; delta-based \
selects the same probability-of-breach zone. In a pre-crash buildup (VIX rising from 14 to 22), \
the 15-delta put shifts inward from 10% OTM to 7% OTM — protection activates earlier precisely \
when it is most needed. (2) COST VARIANCE: In a high-IVR environment, %OTM strikes are cheaper \
per unit (further out on the smile); delta-based strikes are more expensive (closer in). The \
annual budget is 3–5% of MF portfolio value (₹2.4L–₹4L). Under %OTM, cost is more predictable; \
under delta-based, cost spikes in high-IV regimes that are also the highest-risk periods. \
(3) SYNTHETIC PRICER FIDELITY: The Phase 1 task 1.9 synthetic pricer uses BS with a parametric \
skew model. At 8% OTM (ATM−38 to ATM−48 strikes), BS systematically underprices by 10–20% \
(smile not captured). At 15-delta (ATM−12 to ATM−20 in low-vol, ATM−8 to ATM−14 in high-vol), \
BS is more accurate. (4) DEAD ZONE SENSITIVITY: Both methods leave a dead zone (5–8% Nifty \
decline where CSP is losing but protection hasn't activated). Does delta-based selection narrow \
or widen this dead zone in practice? (5) LIQUIDITY: 15-delta Nifty monthly put at 30–45 DTE \
typically has OI of 5,000–15,000 contracts; 8% OTM has OI of 500–2,000. For 4 lots (260 units), \
execution quality matters. Question: Which strike selection methodology produces more reliable \
hedge payoff in moderate (8–15%) corrections given NSE's specific vol skew structure, and which \
methodology is more consistent with the strategy's primary mandate of protecting the ₹80L+ MF \
portfolio during moderate corrections?\
"""

subprocess.run(
    [
        sys.executable, "scripts/ask_council.py",
        "--topic", "integrated-leg2-strike-methodology",
        "--template", "strategy_parameters",
        "--context", "docs/strategies/niftyshield_integrated_v1.md",
        "--timeout", "900",
        "--question", question,
    ],
    check=True,
)
