# docs/bugs/ — Session Orientation

> Direction only. Full defect detail (severity, root cause, symptom, suggested fix)
> lives in `bugs.md` — read the relevant entry there before touching code.

---

## Session start protocol

1. Read `task.md`. Find the first unchecked `- [ ]` line. That is your only task —
   do not look at any other unchecked item.
2. Read that task's `bugs.md` entry (matching `BUG-ID`) before writing any code.
   Re-confirm root cause against current code first — `bugs.md` is a snapshot at
   discovery time. Use the graph (`search_graph` / `get_code_snippet` / `trace_path`),
   not `Read`, per Rule 0.
3. If the task is a decision/scope question rather than an implementable step (e.g.
   blocked on Animesh's input), surface it and stop — do not guess and proceed.
4. Implement. Tests mandatory: one happy-path + one error/edge-case per public function.
5. Financial-logic bugs (delta, P&L, Decimal paths, BrokerClient boundaries) require
   the real `@code-reviewer` subagent against `git diff HEAD` before commit — no
   exceptions, per root `CLAUDE.md`.
6. Commit. Append `| SHA <commit_sha>` to the completed line in `task.md`.
7. Flip status in `bugs.md` to `✅ Fixed` + the same SHA. Add one `TODOS.md` session
   log line. Update `CONTEXT.md` if module structure changed.
8. One bug fix per commit — do not bundle unrelated `BUG-ID`s together.
