#!/usr/bin/env bash
# Submit the IC V2 profit-lock adjustment design council question.
# Run from the project root: bash tmp/q13.sh
#
# Prerequisites:
#   cd tools/llm-council && ./start.sh   (in a separate terminal)
#
# Council models (edit tools/llm-council config before running):
#   openai/gpt-5.5        — structured reasoning baseline
#   openai/o3             — quantitative derivation depth (UNCOMMENT for Q2 math)
#   x-ai/grok-4.3         — adversarial stress-test
#   deepseek/deepseek-r1-0528 — step-by-step derivation cross-check
#
# Note: gemini-pro-latest swapped out in favour of o3 for this question —
# Q2 requires explicit numerical derivation; o3 is materially stronger here.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/q13_ic_v2_profit_lock_adjustment.md"

cd "${PROJECT_ROOT}"

python scripts/council/ask_council.py \
    --topic ic-v2-profit-lock-adjustment \
    --template strategy_parameters \
    --context src/strategy/ic_nifty_v1.py \
    --context src/strategy/ic_expiry_config.py \
    --context docs/plan/ic-nifty-v2/stories.md \
    --context docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md \
    --question "$(cat "${QUESTION_FILE}")"
