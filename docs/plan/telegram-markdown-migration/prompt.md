Central entry point for this epic. Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing
anything else. Then follow the steps below to find and run exactly one task. Do not skip to a
folder-level `prompt.md` directly — this file picks the right one for you.

**Origin:** `docs/plan/telegram-markdown-migration/README.md` — epic index. Read it if you
haven't already this session; it has the scope decisions, supersession notes, and the
Improvement backlog section this file's routing logic draws from.

---

## Step 1 — find the next task

Priority order is fixed: `backbone/` (P0) → `formatting-rules/` (P1) → `strategy-rollout/` (P2).
Do not jump ahead even if a later folder looks more interesting or urgent.

1. Open `docs/plan/telegram-markdown-migration/backbone/tasks.md`. If it has any unchecked
   `- [ ] **MD-N**` line, the first one (top to bottom) is your task. Stop searching, go to
   Step 2.
2. Only if every `MD-*` box in `backbone/tasks.md` is checked: open
   `docs/plan/telegram-markdown-migration/formatting-rules/tasks.md`. First unchecked `FMT-*`
   line is your task.
3. Only if every `FMT-*` box is checked: open
   `docs/plan/telegram-markdown-migration/strategy-rollout/tasks.md`. First unchecked `ROLL-*`
   line is your task — **except** where that file's own parallelization note says otherwise
   (`ROLL-7` through `ROLL-16` are independently startable once their shared soft-dependency is
   met; if you are one of several parallel sessions working this epic, coordinate with the
   others before claiming a `ROLL-*` task in that range so two sessions don't pick the same one).
4. If all three files are fully checked, the epic is complete — stop and say so. Do not invent
   new work.

## Step 2 — confirm you're the right owner

Every task line carries a routing annotation: `Owner: Claude|Antigravity`, `Model:`, and
`Review:`. Read it before doing anything else.

- If `Owner` does not match the agent running this session, **stop immediately** and report:
  which task you found, what it's routed to, and that this session should not implement it.
  Do not proceed "just this once" — the routing reflects a judgment-call/mechanical split made
  during design review, not a preference.
- If `Model` names a specific model (e.g. "Opus" for a design-review pass) and this session is
  running a different one, say so explicitly before proceeding — the human running this may want
  to switch sessions rather than continue.
- Note the `Review` gate now, before implementing — if it says "real @code-reviewer, Opus —
  mandatory," that gate is not optional and must run before commit, per root `CLAUDE.md`'s Agent
  AutoTrigger rules.

## Step 3 — load the folder-level context

Once you've confirmed you're the right owner for the right task, read that folder's own
`prompt.md` (`backbone/prompt.md`, `formatting-rules/prompt.md`, or `strategy-rollout/prompt.md`
— whichever folder Step 1 landed you in) for the folder-specific hard constraints: the non-fatal
send contract, the graph-before-Read rule, any story-specific coordination checks (e.g.
`strategy-rollout/prompt.md`'s `ROLL-4` coordination check), and the exact test-gate command.
This file does not duplicate those — they can drift out of sync with the folder file otherwise.

Then read the matching task's full spec in that folder's `stories.md`.

## Step 4 — implement, verify, record

Follow the folder-level `prompt.md`'s protocol exactly: implement, run the test gate, run the
mandatory review if flagged, commit using `.claude/skills/commit/SKILL.md`'s format (execute the
commit, don't draft it), tick the box in that folder's `tasks.md` with `| SHA: <sha>`, add one
line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item, in this folder or any other, even if it
looks like a quick follow-on. One task per session, same as every folder-level `prompt.md`.
