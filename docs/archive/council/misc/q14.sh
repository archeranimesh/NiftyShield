#!/usr/bin/env bash
# Submit the B002.4 paper delta source architecture council question.
# Run from the project root: bash tmp/q14.sh
#
# Prerequisites:
#   cd tools/llm-council && ./start.sh   (in a separate terminal)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/q14_paper_delta_source_architecture.md"

cd "${PROJECT_ROOT}"

python scripts/council/ask_council.py \
    --topic paper-delta-source-architecture \
    --template data_architecture \
    --context src/risk/delta_tracker.py \
    --context src/paper/models.py \
    --context src/paper/store.py \
    --context src/backtest/chain_reader.py \
    --context docs/bugs/bugs.md \
    --context docs/archive/council/risk/2026-05-02_multi-strategy-portfolio-risk-allocation.md \
    --question "$(cat "${QUESTION_FILE}")"
