# Telegram Markdown Migration — prompt (router)

Central entry point for this epic. `/work` loads this file, **not** a sub-story `prompt.md`.
Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else, then follow the steps below to find and run exactly one task. Do not skip to a folder-level `prompt.md` directly — this file picks
the right one for you.

**Origin:** `README.md` in this folder — the epic index. Read it if you have not this session; it carries the scope decisions, the ordered story list, the cross-cutting constraints (non-fatal send
contract, the escape-every-dynamic-value rule, the MD-2 live-risk window), the supersession / coordination notes, and the Improvement backlog this router's logic draws from.

---

## Step 1 — find the next task

Story order is fixed — it is the row order of the **Stories** table in this folder's `README.md`. Keep this list identical to that table:

1. `backbone/` (P0) — transport switch to MarkdownV2 + caller escaping audit. Depends on: nothing.
2. `formatting-rules/` (P1) — canonical value/table formatting spec + tested helpers. Depends on: `backbone/` complete.
3. `strategy-rollout/` (P2) — per-message-family migration, staged by risk. Depends on: `backbone/` + `formatting-rules/` complete.

Do not jump ahead even if a later story looks more urgent or more interesting.

1. Open `backbone/tasks.md`. If it has any unchecked `- [ ] **MD-N**` line, the first one (top to bottom) is your task — stop searching, go to Step 2.
2. Only if every `MD-*` box in `backbone/tasks.md` is checked: open `formatting-rules/tasks.md`. First unchecked `FMT-*` line is your task.
3. Only if every `FMT-*` box is checked: open `strategy-rollout/tasks.md`. First unchecked `ROLL-*` line is your task — **except** where that file's own parallelization note says otherwise (`ROLL-7`
   through `ROLL-16` are independently startable once their shared soft-dependency is met; if you are one of several parallel sessions working this epic, coordinate before claiming a `ROLL-*` task in
   that range so two sessions do not pick the same one).
4. If all three files are fully checked, the epic is complete — stop and say so. Do not invent new work.

## Step 2 — confirm you are the right owner

The task line carries `| Owner: … | Model: … | Review: … | SHA: …`. Read it before doing anything.

- If `Owner` does not match the agent running this session, **stop** and report: which task you found, what it is routed to, and that this session should not implement it. Do not proceed "just this
  once" — the routing reflects a judgment-call / mechanical split made during design review, not a preference.
- If `Model` names a model this session is not running, say so before proceeding — the human running this may want to switch sessions.
- Note the `Review` gate now — if it names a sub-agent (`code-reviewer` / `greeks-analyst` / `roll-validator`), that gate is mandatory before commit per `CLAUDE.md` Agent AutoTrigger Rules. Several
  `strategy-rollout/` and `backbone/` tasks require the **real** `@code-reviewer` subagent (Opus) against `git diff HEAD` because they touch financial-logic close-notification or P&L-rendering paths —
  that is not satisfied by a persona approximation. The task's `stories.md` As-built / spec section records which.

## Step 3 — load the sub-story context

Read that story's own `prompt.md` (`backbone/prompt.md`, `formatting-rules/prompt.md`, or `strategy-rollout/prompt.md` — whichever folder Step 1 landed you in) for its hard constraints: the exact
test-gate command, the non-fatal send contract, the graph-before-Read rule, and any story-specific coordination check (e.g. `strategy-rollout/prompt.md`'s ROLL-4 coordination check against
`telegram-approval-auth-fix`). This file does not duplicate those — they can drift out of sync otherwise.

Then read the matching task's full spec in that folder's `stories.md`.

## Step 4 — implement, verify, record

Follow the sub-story `prompt.md`'s protocol exactly: implement, run the test gate, run the `Review` gate if flagged, commit via `.claude/skills/commit/SKILL.md` (execute the commit, do not draft
it), set `SHA:` on the task line + tick the box, update this epic's `README.md` **Stories** table status column, add one line to `TODOS.md`.

**Stop.** One task per session — do not proceed to the next unchecked item in this folder or any other, even if it looks like a quick follow-on.
