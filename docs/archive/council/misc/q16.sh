#!/usr/bin/env bash
# Submit the IC time-stop DTE tiering (entry-scaled vs uniform terminal window) council question.
# Run from the project root: bash tmp/q16.sh
#
# Prerequisites:
#   cd tools/llm-council && ./start.sh   (in a separate terminal)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/q16_ic_time_stop_dte_tiering.md"

cd "${PROJECT_ROOT}"

"${PROJECT_ROOT}/.venv/bin/python" -m scripts.council.ask_council \
    --topic ic-time-stop-dte-tiering \
    --template strategy_parameters \
    --context src/strategy/ic_expiry_config.py \
    --context src/strategy/ic_nifty_v1.py \
    --context src/strategy/exit_signals.py \
    --context docs/archive/ic-multi-expiry/stories/IC-M1.md \
    --context docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md \
    --context DECISIONS.md \
    --question "$(cat "${QUESTION_FILE}")"
