#!/usr/bin/env bash
# PreToolUse(Bash) hook — blocks a bare full-suite `pytest tests/unit/` run
# from the main session (spawn @test-runner instead). Recursive test-runner
# subagent runs will also see this — it blocks there too, so a narrowed run
# is required even inside the subagent.
#
# Exit 2 blocks the tool call (bare full-suite run); exit 0 otherwise. Logic +
# tests: scripts/dev/hooks/check_inline_full_suite.py

set -uo pipefail

python3 scripts/dev/hooks/check_inline_full_suite.py
exit $?
