#!/usr/bin/env bash
# UserPromptSubmit hook — inject protocol checklist for implementation tasks only.
# Skips general queries, explanations, and read-only analysis requests.
#
# Exit 0 always. stdout is injected as context before the AI processes the prompt.

set -euo pipefail

INPUT=$(cat)

# Extract the prompt text
PROMPT=$(echo "$INPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
# UserPromptSubmit payload has the prompt under 'prompt'
print(data.get('prompt', '').lower())
" 2>/dev/null || true)

# Task-indicating patterns — imply file writes or DB mutations
TASK_PATTERN='\b(implement|fix|add|build|create|write|update|refactor|migrate|roll|backtest|record|seed|scaffold|change|modify|convert|replace|wire|extend|integrate|enable)\b'

# Query-indicating patterns — read-only, no file changes expected
QUERY_PATTERN='^(what|why|how does|explain|show me|list|can you|does|is |are |which|when|where|who|review what|read|check what|tell me)'

# Skip if it looks like a query
if echo "$PROMPT" | grep -qiE "$QUERY_PATTERN"; then
    exit 0
fi

# Inject only if it looks like a task
if echo "$PROMPT" | grep -qiE "$TASK_PATTERN"; then
    cat <<'CHECKLIST'
⚙️  TASK PROTOCOL — complete these steps before writing any code or editing any file:

1. PROMPT SCORE — does the request name: specific files? phase/story? tests required? DoD?
   If 3 or more are missing → ask ONE clarifying question, then wait. Do not start.

2. COUNCIL CHECKPOINT (CLAUDE.md §Step 2b) — do ALL THREE hold?
   (a) load-bearing and costly to reverse  (b) two defensible approaches with different outcomes
   (c) spans multiple disciplines simultaneously
   All three → draft council question, wait for output. Any one missing → proceed.

3. STATE PLAN → WAIT FOR GO-AHEAD
   Format: "Plan: [one sentence] → touches [files] → tests in [file] → commit. Proceed?"
   If >2 files → wait for explicit go-ahead before continuing.

4. ROUTING (Step 3b) — after go-ahead, decide WHO implements:
   Antigravity → invoke handoff-antigravity skill, produce prompt, STOP. Do not write code.
   Claude     → proceed to Step 4, then AutoTrigger agents after implementation.

AutoTrigger agents (Claude path only — not optional):
   test-runner  → after any code edit (blocking: must pass before code-reviewer)
   code-reviewer → before every commit (blocking: CRITICAL/ERROR must resolve)
   greeks-analyst → any change to src/paper/, option chain, or delta/gamma fields
CHECKLIST
fi

exit 0
