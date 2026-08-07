Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/telegram-markdown-migration/backbone/tasks.md` and find the first unchecked box.
That is your **only task** for this session. Do not look at any other unchecked item. One
task. Complete it fully. Stop.

**Origin:** `docs/plan/telegram-markdown-migration/README.md` — epic index, read it first for
full context on why this migration exists and its scope decision (replace default parse mode
globally, not opt-in).

**Story spec:** Read the matching task in
`docs/plan/telegram-markdown-migration/backbone/stories.md` for the full spec.

**Hard constraint — do not violate:** `TelegramNotifier.send()` is called from `try/except`
blocks throughout the strategy layer under a non-fatal contract (`src/notifications/CLAUDE.md`
— notification failures must never raise into strategy logic). Nothing in this story may change
that contract. A message that fails to send after this migration must still return `False` /
log a warning, never raise.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph. Order: `git log` → `search_graph`/`get_code_snippet` → `search_code` → `sed -n` →
`Read` (state why the graph was insufficient).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first — do not write fixtures from memory.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing.

**Financial-logic commit note:** MD-3 and MD-4 touch strategy close-notification code paths.
Per root `CLAUDE.md`'s Agent AutoTrigger Rules, run the real `@code-reviewer` subagent against
`git diff HEAD` before committing those tasks specifically — not Antigravity's persona
approximation.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft
it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
