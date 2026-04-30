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

## Archived Decisions (pre-integration — submitted manually)

| Date | Topic | Outcome |
|---|---|---|
| 2026-04-30 | IV Reconstruction | Black '76 + futures forward + stepped repo rate + quadratic smile fit |
| 2026-04-30 | Slippage Model | Absolute INR, VIX-regime-aware, OI liquidity multiplier |
