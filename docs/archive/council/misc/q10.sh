#!/usr/bin/env bash
# Submit the IronCondorV2 core design council question.
# Run from the project root: bash tmp/q10.sh
#
# Prerequisites:
#   cd tools/llm-council && ./start.sh   (in a separate terminal)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/q10_ic_v2_core_design.md"

cd "${PROJECT_ROOT}"

python scripts/council/ask_council.py \
    --topic ic-v2-core-design \
    --template strategy_parameters \
    --context src/strategy/ic_expiry_config.py \
    --context src/strategy/ic_nifty_v1.py \
    --question "$(cat "${QUESTION_FILE}")"
