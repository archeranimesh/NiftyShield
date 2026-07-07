# NiftyShield Council Decisions

Archived outputs from the LLM Council (tools/llm-council) on NiftyShield design decisions.

## File Naming

```
docs/council/
├── README.md
└── pending/
    └── YYYY-MM-DD_<topic>_prompt.md   # prompts saved when council server was offline

docs/archive/council/
├── strategy/           # entry/exit rules, instrument selection, strike methodology
├── risk/               # portfolio risk caps, monitoring regimes, deployment gates
├── research/           # Phase 3+ / option-buying / future strategy research
├── data_architecture/  # storage choices, API integration, module design
└── misc/               # ping tests, prompts, and uncategorized outputs
```

Active (unresolved) council decisions live directly under `docs/council/` as `YYYY-MM-DD_<topic>.md`. Once the decision is absorbed into `DECISIONS.md` and the relevant strategy/plan docs, it moves to the appropriate `docs/archive/council/` subfolder.

## When to Trigger the Council

**The council is a planning-phase tool. Never invoke it mid-implementation.**
The right moment is after scope is confirmed but before the implementation plan is finalised —
so the council output can gate the plan, not interrupt code already written.

Trigger when **all three conditions hold simultaneously:**

**1. The decision is load-bearing**
It will be embedded in the backtest engine, a strategy doc, or live execution logic, and
reversing it later costs significant rework. A wrong call on spread width formula is baked
into hundreds of parameter combinations; a wrong call on a variable name is a one-line rename.

**2. Two or more defensible approaches exist with materially different outcomes**
Not "I'm not sure which is cleaner" but "approach A and approach B produce meaningfully
different P&L outcomes or architectural constraints, and first principles alone don't resolve
the tradeoff." The Donchian always-in vs. signal-in-only question qualified — structural EV
difference of ₹800–2,160/lot per inter-signal period, not a stylistic preference.

**3. The question spans multiple disciplines simultaneously**
Options microstructure + quant modelling + backtest fidelity + NSE execution reality, all
bearing on the same decision. The council's value is cross-disciplinary stress-testing where
one domain's obvious answer breaks in another.

### Concrete NiftyShield triggers

| Topic | Template |
|-------|----------|
| Any new strategy's core entry/exit rule | `strategy_parameters` |
| IV reconstruction approach (BS vs. SVI vs. other) | `backtest_methodology` |
| Slippage model choice for Tier 2 backtest | `backtest_methodology` |
| Kill-switch / circuit-breaker criteria for live execution | `strategy_parameters` |
| Position sizing formula when it interacts with dynamic width + lot constraints | `strategy_parameters` |
| Storage or module boundary decisions with long-lived lock-in | `data_architecture` |

### Do NOT trigger the council for

- Implementation questions (class structure, async vs. sync, naming)
- Decisions already resolved in `DECISIONS.md` — re-litigating settled decisions is noise
- Anything resolvable by reading existing docs or running a quick quantitative check
- Parameter sweeps — the backtest resolves those empirically; council opinions on specific
  numbers (e.g., "should k be 0.8 or 0.9?") are weaker than observed Sharpe data
- Reversible decisions where the cost of being wrong is a small refactor

### Phase constraint

```
Planning phase  ✓  Confirm scope → identify council-worthy decisions → submit to council
                    → receive output → update DECISIONS.md + plan doc → THEN implement
Implementation  ✗  Do not stop mid-implementation to ask the council; finish the phase,
                    open a new planning session for any unresolved architectural questions
```

## Submitting a Question

```bash
# Council server must be running first
cd tools/llm-council && ./start.sh

# From project root — in a new terminal
python scripts/ask_council.py \
    --topic slippage-model \
    --template backtest_methodology \
    --question "Which slippage model is appropriate for NSE Bhavcopy backtesting?"

# Include an additional strategy spec as context
python scripts/ask_council.py \
    --topic csp-delta-selection \
    --template strategy_parameters \
    --context docs/strategies/csp_nifty_v1.md \
    --question "Should the CSP entry delta be 0.20 or 0.25 given the stress window data?"

# Preview the assembled prompt without submitting
python scripts/ask_council.py --topic foo --question "..." --dry-run
```

## Templates

| Template | Use for |
|---|---|
| `backtest_methodology` | IV reconstruction, slippage, cost model, data pipeline |
| `strategy_parameters` | Entry/exit rules, delta targets, sizing, kill criteria |
| `data_architecture` | Storage choices, API integration, module design |

## Workflow

1. I (Claude) draft the question + recommend a `--template` when a non-obvious design decision arises
2. You run `ask_council.py` (server must be up)
3. Decision is saved to `docs/council/YYYY-MM-DD_<topic>.md`
4. I read the decision file and update `DECISIONS.md` + relevant plan files

## Response File Structure

Every completed council file follows this layout:

```
# Council Decision: <topic>

Date: YYYY-MM-DD
Chairman: <model>
Council members: <model-A>, <model-B>, <model-C>

---

## Stage 3 — Chairman Synthesis          ← READ THIS FIRST — authoritative
  Summary Table                           ← canonical before/after for each decision
  Dissenting Notes                        ← minority positions; first post-validation targets
  Implementation Sequencing               ← which docs to update and in what order

## Stage 1 — Individual Responses        ← background context only
  ### <model-A>
  ### <model-B>
  ### <model-C>

## Aggregate Rankings (Stage 2 Peer Review)
  - <model>: avg rank N.NN (4 votes)     ← higher rank = peers judged it strongest

## Prompt Sent (first 3000 chars)        ← the context injected into the council
```

**Stage 3 is the only section that drives implementation.** Stage 1 is raw panel output —
informative but not directive. The Aggregate Rankings tell you which Stage 1 response the
chairman weighted most heavily.

## Archived Decisions

All decisions below have been absorbed into `DECISIONS.md` and the relevant strategy/plan docs.
Full council output files are in `archive/` subfolders.

### archive/strategy/

| Date | File | Key Decision |
|---|---|---|
| 2026-04-30 | `2026-04-30_donchian-roll-mechanics.md` | **Superseded** by 2026-05-01 version — preliminary roll mechanics analysis |
| 2026-05-01 | `2026-05-01_donchian-roll-mechanics.md` | Signal-in-only (flat between signals); uniform credit spreads; ATR-proportional width `min(round50(0.8×ATR_40d), 500)`, floor 150 |
| 2026-05-01 | `2026-05-01_orb-volatility-filter-design.md` | ATR primary filter + VIX-IVP ≥90th pct structural exclusion; event-day calendar exclusion mandatory; DTE ≤2 → skip to next weekly |
| 2026-05-02 | `2026-05-02_csp-entry-delta-v2.md` | 22-delta default (85% of 25Δ credit, ~half stop-out rate); 25-delta when IVR 25–40 |
| 2026-05-02 | `2026-05-02_gap-fade-vix-filter-threshold.md` | Gap Fade IVP threshold: 75th pct (vs ORB 90th); asymmetry is structural and binding |
| 2026-05-02 | `2026-05-02_integrated-leg2-strike-methodology.md` | %OTM over delta-based for Leg 2 (long 8% below spot, short 20% below spot); delta-based rejected on cost unpredictability at high VIX |
| 2026-05-02 | `2026-05-02_iron-condor-v1-core-design.md` | Mild put-side asymmetry: short put 16Δ / short call 14Δ normal; 18Δ/12Δ high-IVR; symmetric deltas rejected |
| 2026-05-02 | `2026-05-02_nifty-long-instrument-comparison-protection.md` | Track C = Deep ITM Call (delta ≈ 0.90); Futures + Covered Call / CSP programmatically blocked |
| 2026-05-28 | `2026-05-28_paper-trade-exit-philosophy.md` | **Superseded** by 2026-06-26 version |
| 2026-06-26 | `2026-06-26_ic-v2-core-design.md` | IronCondorV2 25Δ/22Δ entry, 10Δ wings, partial-roll, DTE exits |
| 2026-06-26 | `2026-06-26_paper-trade-exit-philosophy.md` | TIME_STOP/DTE_REVIEW priority fix in evaluate_cc; StrategyMonitor observability logs (q11/q12) |
| 2026-06-27 | `2026-06-27_ic-v2-profit-lock-adjustment.md` | IC V2 profit-lock Zone 1/2/3 rules |

### archive/risk/

| Date | File | Key Decision |
|---|---|---|
| 2026-05-02 | `2026-05-02_continuous-revalidation-statistical-power.md` | CUSUM lower-sided (k=0.50, h_warn=3.0, h_reduce=4.0, h_halt=5.0) replaces weekly Z-score; graduated regime by N; slippage/loss early guards |
| 2026-05-02 | `2026-05-02_multi-strategy-portfolio-risk-allocation.md` | 10 binding rules: delta caps (+1.0/+2.0 lots), ₹3–4L stress loss, ₹6L drawdown kill, shadow gross margin, 2 max short-put lots |
| 2026-05-02 | `2026-05-02_variance-gate-regime-completeness.md` | Phase 0.8 gate: 4 criteria A–D; Z-score is smoke test only; graduated deployment tiers 0→0.5→1→2→3 |

### archive/research/

| Date | File | Key Decision |
|---|---|---|
| 2026-05-02 | `2026-05-02_gamma-acceleration-mispricing-option-buying.md` | Near-expiry buy research (Phase 3): Gamma Gearing primary metric; Speed secondary; OI velocity confirmation only |

### archive/data_architecture/

| Date | File | Key Decision |
|---|---|---|
| 2026-06-02 | `2026-06-02_strategy-monitor-watchlist-design.md` | **Superseded** by 2026-06-26 version |
| 2026-06-26 | `2026-06-26_strategy-monitor-watchlist-design.md` | StrategyMonitor watchlist design and storage |
