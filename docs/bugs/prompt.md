# docs/bugs/ — Session Orientation

> Direction only. Full defect detail (severity, root cause, symptom, suggested fix)
> lives in `docs/bugs/bugs.md` — read the relevant entry there before touching code.
>
> Paths below are relative to the repo root, not this file's own directory —
> a bare `task.md` or `bugs.md` reference has been misread as project-root
> `task.md` before (no such file exists there); always resolve to
> `docs/bugs/task.md` and `docs/bugs/bugs.md`.

---

## Session start protocol

1. Read `docs/bugs/task.md`. Find the first unchecked `- [ ]` line **that belongs to a
   `BUG-ID` checklist** (a line under a `## BUG-NNN — ...` heading, formatted
   `**BNNN.x**`). That is your only task — do not look at any other unchecked
   item, and do not substitute a different one.

   Skip over — but do not silently ignore — any unchecked line that sits
   outside a `BUG-ID` section (e.g. under a "decision"/"scope" heading like
   "Paper-phase scope decision") or whose text says it's blocked on a human/
   live-host action (e.g. "pending Animesh", "pending live host", "SHA
   pending"). Those are not Claude-actionable implementation steps; mention
   them once at session start as still-open ("also outstanding: <line>,
   blocked on X") so they don't get lost, then move on to the next
   `BUG-ID` item.

   If a `BUG-ID` section has every `B<N>.x` line checked, treat it as closed
   and move to the next `BUG-ID` section in file order — do not stop on a
   checked box.
2. Read that task's `docs/bugs/bugs.md` entry (matching `BUG-ID`) before writing any
   code. Re-confirm root cause against current code first — `docs/bugs/bugs.md` is a
   snapshot at discovery time, not a live source of truth. Use the graph
   (`search_graph` / `get_code_snippet` / `trace_path`), not `Read`, per Rule 0.
3. If the task is a decision/scope question rather than an implementable step (e.g.
   blocked on Animesh's input), surface it and stop — do not guess and proceed.
4. Implement. Tests mandatory: one happy-path + one error/edge-case per public function.
5. Financial-logic bugs (delta, P&L, Decimal paths, BrokerClient boundaries) require
   the real `@code-reviewer` subagent against `git diff HEAD` before commit — no
   exceptions, per root `CLAUDE.md`.
6. Commit. Append `| SHA <commit_sha>` to the completed line in `docs/bugs/task.md`.
7. Flip status in `docs/bugs/bugs.md` to `✅ Fixed` + the same SHA. Add one `TODOS.md`
   session log line. Update `CONTEXT.md` if module structure changed.
8. One bug fix per commit — do not bundle unrelated `BUG-ID`s together.

## If the sandbox `.git` is lock-contended

If `.git/index.lock` exists and can't be removed (permission denied — a concurrent
live-host process holds it, not a stale lock), do not force it. Finish steps 1–5,
leave the completed `docs/bugs/task.md` line marked `| SHA pending — sandbox
.git/index.lock held by a concurrent process, commit deferred to live host`, add the
`TODOS.md` session log entry the same way, and stop before step 6. When the real SHA
is provided later, replace every `SHA pending` reference for that item in both
`docs/bugs/task.md` and `TODOS.md`.
