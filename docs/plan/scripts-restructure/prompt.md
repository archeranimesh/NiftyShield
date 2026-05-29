Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read `docs/plan/scripts-restructure/tasks.md` and find the first unchecked box — the first `- [ ]` line. That is your **only task** for this session. Do not look at any other unchecked item. Do not attempt to batch or combine tasks. One task. Complete it fully. Move on to nothing else.

**Story spec:** Read the matching story in `docs/plan/scripts-restructure/stories.md` (same task ID) for the full implementation spec, "Before any code" checks, and commit message. Follow it exactly.

**Context:** Read `docs/plan/scripts-restructure/stories.md` — the migration rationale, directory layout, and classification rules (pipeline/lookup/record axis) are documented there. Do not infer structure from the current flat layout. Every new script must be classified by the axis in stories.md before placement.

**Pre-implementation gate:** State in one sentence: which task you are implementing (ID + one-line description), which files will move or change, and what the cron/import impact is. Do not move any files until this plan is stated and confirmed.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first trying the graph. Order: `git log --oneline -10 <file>` for intent → `search_graph` / `get_code_snippet` for symbols → `search_code` for grep → `bash sed -n 'N,Mp' <file>` for a specific block → `Read` only if all of the above are insufficient.

**Cron audit (mandatory before any move):** Run `crontab -l` and grep for any reference to the file being moved. Update cron entries before committing. A moved script with a stale cron path is a silent failure.

**Import audit (mandatory before any move):** `grep -r "scripts\.<module>" .` — find all callers. Update every import path in the same commit as the move.

**`__init__.py` rule:** Every new package directory must have an `__init__.py`. A single comment line is sufficient. Without it, codebase-memory-mcp silently skips the directory.

**Test gate — blocking:** After each move, run:
`python -m pytest tests/unit/ --tb=no -q`
All tests must be green before the next move.

**Commit format:** One commit per folder moved. Never bundle two folder migrations into one commit. Format in `.claude/skills/commit/SKILL.md`.

**Verify and record:** Copy the SHA from `git log --oneline -1`. Open `docs/plan/scripts-restructure/tasks.md`, change `- [ ]` to `- [x]`, append `| SHA: <sha>`. Add one line to `TODOS.md` session log.

**Stop.** You are done. Do not proceed to the next unchecked item.
