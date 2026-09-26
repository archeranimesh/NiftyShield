#!/usr/bin/env bash
# Submit the PP CRASH_MONETIZE profit-extraction council question.
# Run from the project root: bash tmp/q15.sh
#
# Prerequisites:
#   cd tools/llm-council && ./start.sh   (in a separate terminal)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/q15_pp_crash_monetize_profit_extraction.md"

cd "${PROJECT_ROOT}"

"${PROJECT_ROOT}/.venv/bin/python" -m scripts.council.ask_council \
    --topic pp-crash-monetize-profit-extraction \
    --template strategy_parameters \
    --context src/strategy/exit_signals.py \
    --context src/strategy/pp_overlay_v1.py \
    --context src/strategy/executor.py \
    --context docs/plan/3track-consolidation/stories.md \
    --context DECISIONS.md \
    --question "$(cat "${QUESTION_FILE}")"
