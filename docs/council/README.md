# NiftyShield Council Decisions

Archived outputs from the LLM Council (tools/llm-council) on NiftyShield design decisions.

## File Naming

```
docs/council/
├── YYYY-MM-DD_<topic>.md        # completed council decisions
├── pending/
│   └── YYYY-MM-DD_<topic>_prompt.md   # prompts saved when council server was offline
└── README.md
```

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

## Archived Decisions (pre-integration — submitted manually)

| Date | Topic | Outcome |
|---|---|---|
| 2026-04-30 | IV Reconstruction | Black '76 + futures forward + stepped repo rate + quadratic smile fit |
| 2026-04-30 | Slippage Model | Absolute INR, VIX-regime-aware, OI liquidity multiplier |
