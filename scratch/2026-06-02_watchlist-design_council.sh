#!/usr/bin/env bash
# Submit the strategy-monitor watchlist design council question.
# Run from the project root: bash scratch/2026-06-02_watchlist-design_council.sh
#
# Prerequisites:
#   cd tools/llm-council && ./start.sh   (in a separate terminal)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/2026-06-02_watchlist-design_question.md"

cd "${PROJECT_ROOT}"

python scripts/council/ask_council.py \
    --topic strategy-monitor-watchlist-design \
    --template data_architecture \
    --context src/strategy/protocol.py \
    --context src/strategy/monitor.py \
    --context src/strategy/csp_nifty_v1.py \
    --question "$(cat "${QUESTION_FILE}")"
