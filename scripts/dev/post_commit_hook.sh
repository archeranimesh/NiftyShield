#!/bin/bash
# Post-commit: remind to re-index codebase graph if src/ or scripts/ changed
CHANGED=$(git diff --name-only HEAD~1 HEAD 2>/dev/null | grep -E '^(src|scripts)/')
if [ -n "$CHANGED" ]; then
    echo "⚡ src/ or scripts/ changed — run 'make index' in your AI session to re-index the graph."
fi
