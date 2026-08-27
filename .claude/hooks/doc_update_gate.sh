#!/usr/bin/env bash
# PreToolUse(Bash) hook — reminds when a `git commit` stages code but no state doc.
#
# Exit 0 → allow the tool call (v1 always does this — advisory only).
# Exit 2 → block the tool call (NOT used in v1; see deferral note below).
#
# Mechanism:
#   1. Read tool_input JSON from stdin, extract .command via python3 (same pattern
#      as guard_src_reads.sh:20-24).
#   2. Act only when the command creates a git commit. Skip `git log`, `--amend`,
#      and `--dry-run` — those inspect or rewrite, they don't open a fresh Step 5a
#      boundary.
#   3. `git diff --cached --name-only`: if the staged set includes a src/ or
#      scripts/ *.py file AND none of the Step 5a state docs (TODOS.md, CONTEXT.md,
#      DECISIONS.md, docs/plan/README.md) → print a reminder to stderr naming the
#      omission.
#   4. Escape hatch: the literal [skip-docs] anywhere in the command (i.e. in the
#      commit message) → silent exit 0.
#   5. Tests-only commits (every staged path under tests/) → no reminder.
#
# v1 is ADVISORY: exit 0 on every path, never blocks. The exit-2 escalation is
# deferred until a week of observing the false-positive rate — pure refactors and
# individual commits of a multi-commit phase both legitimately omit doc updates
# (TODOS.md 2026-08-27, round-2 workflow token-optimization, item #2).

set -uo pipefail

INPUT=$(cat)

CMD=$(echo "$INPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('tool_input', {}).get('command', ''))
" 2>/dev/null || true)

# Only act on commands that create a git commit.
echo "$CMD" | grep -qE '\bgit\b[^|;&]*\bcommit\b' || exit 0

# Skip inspection / rewrite forms — no new Step 5a boundary.
echo "$CMD" | grep -qE '(--amend|--dry-run)' && exit 0

# Escape hatch — [skip-docs] in the commit message.
echo "$CMD" | grep -qF '[skip-docs]' && exit 0

git rev-parse --git-dir >/dev/null 2>&1 || exit 0

STAGED=$(git diff --cached --name-only 2>/dev/null || true)
[ -z "$STAGED" ] && exit 0

# Tests-only commit → no reminder (every staged path under tests/).
echo "$STAGED" | grep -qvE '^tests/' || exit 0

# No staged code file → nothing to enforce.
echo "$STAGED" | grep -qE '^(src|scripts)/.*\.py$' || exit 0

# A Step 5a state doc is staged → satisfied.
echo "$STAGED" | grep -qE '^(TODOS\.md|CONTEXT\.md|DECISIONS\.md|docs/plan/README\.md)$' && exit 0

cat >&2 <<'EOF'
⚠ STATE-DOC REMINDER — this commit stages src/ or scripts/ *.py but no Step 5a state doc.
CLAUDE.md §Step 5a expects one of these updated alongside a code change:
  · TODOS.md            — mark completed items, add a session-log entry
  · CONTEXT.md          — "What Exists" tree if files were added
  · DECISIONS.md        — any new architecture decision
  · docs/plan/README.md — status column for the story/epic touched
Pure refactor, or one commit of a multi-commit phase? Add [skip-docs] to the
commit message to silence this. Advisory only — the commit will proceed.
EOF

exit 0
