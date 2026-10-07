#!/usr/bin/env bash
# Submit the data-source-routing council question: canonical contract identity, per-capability
# routing, and Greeks provenance for the far-dated yearly book.
# Run from anywhere: bash docs/plan/data-source-routing/council/submit.sh
#
# Prerequisites:
#   cd tools/llm-council && ./start.sh   (in a separate terminal)
#
# Output lands at docs/council/YYYY-MM-DD_data-source-routing.md. Read its Stage 3 first, then
# follow docs/plan/data-source-routing/council/README.md (absorb steps).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
QUESTION_FILE="${SCRIPT_DIR}/question.md"

cd "${PROJECT_ROOT}"

"${PROJECT_ROOT}/.venv/bin/python" -m scripts.council.ask_council \
    --topic data-source-routing \
    --template data_architecture \
    --context docs/plan/data-source-routing/README.md \
    --context docs/plan/dhan-far-expiry-chain/dhan-chain-adapter/findings.md \
    --context docs/plan/yearly-overlays/README.md \
    --context src/client/chain_source.py \
    --context src/client/protocol.py \
    --timeout 900 \
    --question "$(cat "${QUESTION_FILE}")"
