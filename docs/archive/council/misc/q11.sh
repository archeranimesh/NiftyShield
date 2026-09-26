#!/usr/bin/env bash
# Submit the exit-philosophy council question.
# Run from the project root: bash tmp/q11.sh
#
# Prerequisites:
#   cd tools/llm-council && ./start.sh   (in a separate terminal)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/q11_exit_philosophy.md"

cd "${PROJECT_ROOT}"

python scripts/council/ask_council.py \
    --topic paper-trade-exit-philosophy \
    --template strategy_parameters \
    --context docs/strategies/niftyshield_integrated_v1.md \
    --context src/strategy/exit_signals.py \
    --question "$(cat "${QUESTION_FILE}")"
