#!/usr/bin/env bash
# PreToolUse hook — warns when Read targets src/ or scripts/ before graph tools.
#
# Exit 0  → allow the tool call (output shown to assistant as context)
# Exit 2  → block the tool call (hard reject)
#
# This hook warns only. The assistant must decide whether to proceed.
# Legitimate uses (e.g. Read needed to satisfy Edit's precondition after a graph
# lookup) are expected — the reminder is friction, not a wall.

set -euo pipefail

INPUT=$(cat)

# Extract file_path from tool_input JSON
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('tool_input', {}).get('file_path', ''))
" 2>/dev/null || true)

# Only warn for src/ or scripts/ paths
if echo "$FILE_PATH" | grep -qE '/(src|scripts)/'; then
    cat <<'EOF'
⛔ PROTOCOL REMINDER — Read on src/ or scripts/ detected.

Decision tree (CLAUDE.md §Step 1):
  1. Need a symbol/function?   → search_graph or get_code_snippet
  2. Need callers/callees?     → trace_path
  3. Need a grep?              → search_code
  4. Need a specific line?     → bash sed -n 'N,Mp' <file>  (cheaper than Read)
  5. Still not enough?         → Read is permitted — but state why graph was insufficient.

If you are calling Read solely to satisfy the Edit tool precondition after already
inspecting the target lines via bash, that is a legitimate use — proceed.
Otherwise, replace this Read with a graph call.
EOF
fi

# Always exit 0 — warn only, never block.
exit 0
