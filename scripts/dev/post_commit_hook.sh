#!/bin/bash
# Post-commit: remind to re-index codebase graph if src/ or scripts/ changed,
# and separately flag added/removed files, which is what actually rots CONTEXT_TREE.md.
CHANGED=$(git diff-tree --no-commit-id -r --name-only HEAD 2>/dev/null | grep -E '^(src|scripts)/')
if [ -n "$CHANGED" ]; then
    echo "⚡ src/ or scripts/ changed — run 'make index' in your AI session to re-index the graph."
fi

STRUCTURAL=$(git diff-tree --no-commit-id -r --diff-filter=AD --name-only HEAD 2>/dev/null | grep -E '^(src|scripts)/')
if [ -n "$STRUCTURAL" ]; then
    echo "⚡ Files added/removed under src/ or scripts/ — update CONTEXT_TREE.md (Step 5a) before closing this phase:"
    echo "$STRUCTURAL" | sed 's/^/    /'
fi
