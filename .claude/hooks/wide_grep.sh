#!/usr/bin/env bash
# PreToolUse(Bash) hook — warns on an unscoped grep/sed/awk over a large file
# (or a recursive grep with no include/exclude filter).
#
# Exit 0 always — warn only, never block. Logic + tests:
#   scripts/dev/hooks/check_wide_grep.py

set -uo pipefail

cat | python3 scripts/dev/hooks/check_wide_grep.py 2>/dev/null || true

exit 0
