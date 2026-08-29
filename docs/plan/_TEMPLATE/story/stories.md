<!-- Copy with the `story/` folder. Delete these HTML comments once filled in.
This file is the complete per-task implementation spec — a session should not need any
other planning doc to execute a task, only CONTEXT.md + the repo + CLAUDE.md / REVIEW.md. -->

# <Story title> — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, update the story status
> summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

<!-- If this story changes DB schema: state here once, at the top —
"DDL: use the exact schema in `schema.md`. Do not inline CREATE TABLE below." -->

---

## <ID-1> — <title>

**Files to change / create:**
- `<path>` — <what changes>
- `<test path>` — <what it covers>

**Before any code (graph queries — do not write model constructors from memory):**
- `get_code_snippet("<ModelClassName>")` — exact field list, required vs optional
- `search_graph("<EnumName>")` — every enum member used
- `trace_path("<function>")` — callers / callees if the change ripples

**What to implement:**

1. <step>
2. <step>

**Tests (`tests/unit/...`, no network, no real DB):**
- `test_<happy_path>` — <assertion>
- `test_<edge_or_error>` — <assertion>

**Commit:** `<type>(<scope>): <subject ≤60 chars>`

---

## <ID-2> — <title>

<!-- same structure -->
