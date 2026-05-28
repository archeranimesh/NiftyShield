#!/usr/bin/env bash
# Smoke-test: verifies all council members are responding.
# Run from project root: bash scratch/council_ping.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/council_ping_question.md"

cd "${PROJECT_ROOT}"

python scripts/ask_council.py \
    --topic council-ping-test \
    --template strategy_parameters \
    --question "$(cat "${QUESTION_FILE}")"
