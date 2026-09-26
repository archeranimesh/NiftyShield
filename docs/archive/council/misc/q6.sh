#!/usr/bin/env python3
"""Q6 — Multi-Strategy Concurrent Portfolio Risk Allocation Framework
Phase gate: Phase 3 (src/risk/ design)
Recommended submission order: 8th (when 2 strategies are live or nearly live)
"""
import os, pathlib, subprocess, sys

os.chdir(pathlib.Path(__file__).parent.parent)

question = """\
By Phase 3, NiftyShield plans to run the following strategies concurrently on Nifty 50 options: \
(A) CSP v2 — 1 lot short Nifty monthly put at ~20–25 delta; (B) NiftyShield Integrated — 1 lot \
CSP + 4 lots protective put spread (long 8%–15% OTM put, short 20% OTM put) + 2 lots quarterly \
tail puts; (C) Swing strategies (Donchian or ORB) — 1–2 lots directional credit spreads at \
15-delta, 30–45 DTE; (D) Covered call overlay — 1 lot short Nifty monthly call at 15-delta on \
the pledged NiftyBees position. The collateral pool is ~₹1.2cr (₹75L MF + ₹30L bonds + ₹15.5L \
NiftyBees). The combined SPAN + exposure margin for all strategies running simultaneously is \
approximately ₹6L–₹10L (rough estimate — depends on SPAN offsets from protective puts). Three \
unresolved design questions: (1) CORRELATED TAIL RISK: During a Nifty selloff of ≥10%, CSP (A) \
hits its delta stop, the swing strategy's bearish spread profits but the bullish spread in a \
prior cycle may still be open, and Integrated (B) provides protection only above the Leg 2 \
threshold. The strategies are NOT independent in a correlated market event. What is the correct \
portfolio-level net-delta constraint that prevents a single 10% Nifty decline from triggering \
kill criteria simultaneously across 3 strategies? (2) MARGIN INTERACTION: SPAN margin offsets \
exist when a short put and long put are in the same expiry cycle (the protective put spread in \
Integrated reduces SPAN for the CSP leg). Does this margin offset change the effective capital \
efficiency of running Integrated + CSP together vs. separately? And does it create a false sense \
of safety if the protective put's strike is far enough OTM that SPAN hasn't credited the full \
offset? (3) VARIANCE CHECK DISTORTION: If a portfolio-level delta cap causes some swing strategy \
entries to be skipped (because the cap is already reached by CSP + Integrated), the paper trade \
log will systematically underperform the per-strategy backtest (which assumes every signal is \
executed). How should the variance check at the portfolio level account for signal-skipping due \
to the risk cap? Should each strategy be validated independently (ignoring the portfolio cap) \
and the cap only applied live, or should the paper trading phase simulate the cap and validate \
against a cap-aware backtest?\
"""

subprocess.run(
    [
        sys.executable, "scripts/ask_council.py",
        "--topic", "multi-strategy-portfolio-risk-allocation",
        "--template", "strategy_parameters",
        "--context", "docs/strategies/niftyshield_integrated_v1.md",
        "--timeout", "900",
        "--question", question,
    ],
    check=True,
)
