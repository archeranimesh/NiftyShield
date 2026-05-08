#!/usr/bin/env bash
# PreToolUse hook — council decision checkpoint for Edit and Write tool calls.
#
# Fires before any file edit and surfaces the 3 council trigger criteria as a
# compact reminder. Exit 0 always (warn only, never block).
#
# The council is a planning-phase tool. If all 3 criteria hold, stop and draft
# the council question before writing any code. See docs/council/README.md.

set -euo pipefail

INPUT=$(cat)

# Extract tool name
TOOL_NAME=$(echo "$INPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('tool_name', ''))
" 2>/dev/null || true)

# Only fire on Edit or Write
if [[ "$TOOL_NAME" == "Edit" || "$TOOL_NAME" == "Write" ]]; then
    cat <<'REMINDER'
⚖️  COUNCIL CHECKPOINT (CLAUDE.md §Step 2b)

Before writing code, confirm this decision does NOT meet all three council criteria:

  1. Load-bearing and costly to reverse?
     (embedded in backtest engine, strategy doc, or live execution logic)

  2. Two defensible approaches with materially different outcomes?
     (not stylistic preference — real P&L or architectural difference)

  3. Spans multiple disciplines simultaneously?
     (options microstructure + quant modelling + backtest fidelity + NSE execution)

If ALL THREE hold → stop, draft the council question, wait for output before coding.
If any one does NOT hold → proceed. This reminder is friction, not a wall.

Templates: backtest_methodology | strategy_parameters | data_architecture
Workflow:  docs/council/README.md
REMINDER
fi

exit 0
