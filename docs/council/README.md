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
