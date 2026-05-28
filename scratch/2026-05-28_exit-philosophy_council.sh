#!/usr/bin/env bash
# Submit the exit-philosophy council question.
# Run from the project root: bash scratch/2026-05-28_exit-philosophy_council.sh
#
# Prerequisites:
#   cd tools/llm-council && ./start.sh   (in a separate terminal)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/2026-05-28_exit-philosophy_question.md"

cd "${PROJECT_ROOT}"

python scripts/ask_council.py \
    --topic paper-trade-exit-philosophy \
    --template strategy_parameters \
    --context docs/strategies/csp_nifty_v1.md \
    --context docs/strategies/niftyshield_integrated_v1.md \
    --context docs/strategies/nifty_track_comparison_v1.md \
    --question "$(cat "${QUESTION_FILE}")"
