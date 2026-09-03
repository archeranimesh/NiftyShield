#!/usr/bin/env bash
# PreToolUse(Bash) hook — warns on a bare full-suite `pytest tests/unit/` run
# from the main session (spawn @test-runner instead). Recursive test-runner
# subagent runs will also see the line; it is warn-only noise there.
#
# Exit 0 always — warn only, never block. Logic + tests:
#   scripts/dev/hooks/check_inline_full_suite.py

set -uo pipefail

cat | python3 scripts/dev/hooks/check_inline_full_suite.py 2>/dev/null || true

exit 0
