#!/usr/bin/env bash
# Submit the BUG-032 ambiguous-match aggregation-vs-hard-fail council question.
# Run from the project root: bash tmp/bug032.sh
#
# Prerequisites:
#   cd tools/llm-council && ./start.sh   (in a separate terminal)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/bug032_ambiguous_match_aggregation.md"

cd "${PROJECT_ROOT}"

"${PROJECT_ROOT}/.venv/bin/python" -m scripts.council.ask_council \
    --topic bug032-ambiguous-match-aggregation-vs-hard-fail \
    --template data_architecture \
    --context src/paper/store.py \
    --context scripts/strategies/three_track/paper_3track_snapshot.py \
    --context docs/bugs/bugs.md \
    --context DECISIONS.md \
    --timeout 900 \
    --question "$(cat "${QUESTION_FILE}")"
