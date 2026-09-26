#!/usr/bin/env bash
# Submit the MVP corporate-action (stock split) adjustment council question:
# manual ratio-rebase vs a corporate-actions table, tranche-field scope,
# historical mvp_snapshots handling, detection model, and retrofit scope.
# Run from the project root: bash tmp/q18.sh
#
# Prerequisites:
#   cd tools/llm-council && ./start.sh   (in a separate terminal)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/q18_mvp_corporate_actions.md"

cd "${PROJECT_ROOT}"

"${PROJECT_ROOT}/.venv/bin/python" -m scripts.council.ask_council \
    --topic mvp-corporate-actions \
    --template data_architecture \
    --context docs/bugs/bugs.md \
    --context src/mvp/models.py \
    --context src/mvp/tracker.py \
    --context src/mvp/store.py \
    --context src/mvp/backfill.py \
    --context DECISIONS.md \
    --question "$(cat "${QUESTION_FILE}")"
