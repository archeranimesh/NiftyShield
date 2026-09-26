#!/usr/bin/env bash
# Submit the signals-paper-track execution-layer council question (SPT-1):
# module boundary (reuse src/strategy+src/paper vs self-contained loop), SL/target
# launch levels, Phase-1 fixed vs dynamic exit, monitor cadence, and the 6-month
# go-live gate metrics.
# Run from the project root: bash tmp/q17.sh
#
# Prerequisites:
#   cd tools/llm-council && ./start.sh   (in a separate terminal)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/q17_signals_paper_track_execution_layer.md"

cd "${PROJECT_ROOT}"

"${PROJECT_ROOT}/.venv/bin/python" -m scripts.council.ask_council \
    --topic signals-paper-track-execution-layer \
    --template strategy_parameters \
    --context docs/plan/signals-paper-track/prompt.md \
    --context docs/plan/signals-paper-track/stories.md \
    --context docs/plan/signals-paper-track/council-question.md \
    --context src/signals/models.py \
    --context src/signals/option_resolver.py \
    --context src/paper/CLAUDE.md \
    --context src/strategy/executor.py \
    --context src/strategy/monitor.py \
    --context DECISIONS.md \
    --context BACKTEST_PLAN.md \
    --question "$(cat "${QUESTION_FILE}")"
