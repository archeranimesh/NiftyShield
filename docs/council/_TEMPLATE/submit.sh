#!/usr/bin/env bash
# Submit the <topic> council question: <one-line summary of the decision>.
# Run from the project root: bash tmp/q<N>.sh
#
# Prerequisites:
#   cd tools/llm-council && ./start.sh   (in a separate terminal)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/q<N>_<topic-slug>.md"

cd "${PROJECT_ROOT}"

"${PROJECT_ROOT}/.venv/bin/python" -m scripts.council.ask_council \
    --topic <topic-slug> \
    --template <strategy_parameters|backtest_methodology|data_architecture> \
    --context <path/to/relevant/doc/or/src/file.py> \
    --question "$(cat "${QUESTION_FILE}")"
