# Full-repo-review follow-ups — prompt (router)

Central entry point for this epic. `/work` loads this file, **not** a sub-story `prompt.md`. Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else, then follow the steps below to find and
run exactly one task.

**Origin:** `README.md` in this folder — the epic index. Read it if you have not this session — it carries the scope decisions, the priority order, the surface/model routing, and the cross-cutting
constraints this router's logic depends on.

---

## Step 1 — find the next task

Story order is fixed — it is the row order of the **Priority order** table in this folder's `README.md`. Keep this list identical to that table:

1. `portfolio-pnl-critical-fix/` — P0, live P&L wrong today
2. `sqlite-backup-cron/` — P0, no backup of the store of record
3. `docs-navigation-and-staleness/` — P1, stale status table + dead links
4. `telegram-approval-auth-fix/` — P1, group-chat approval auth bug
5. `protocol-standards-reconciliation/` — P2, reviewer/protocol contradictions
6. `logging-migration-completion/` — P2, bare loggers + script entrypoints
7. `greeks-parity-validation/` — P3, contested — needs a council/strategist consult first
8. `paper-pnl-golden-tests/` — P3, test hardening
9. `suppression-hygiene-triage/` — P3, docs/policy triage

Do not skip ahead within a tier for convenience, and never start a P2/P3 story before a noted P0/P1 blocker closes (see README "Dependencies worth noting"). Otherwise tier order is a priority guide,
not a hard gate — open each folder's `tasks.md` in the order above.

Open `portfolio-pnl-critical-fix/tasks.md`. If it has any unchecked `- [ ]` line, the first one (top to bottom) is your task — stop searching, go to Step 2. Only if every box in that file is checked:
open `sqlite-backup-cron/tasks.md`, first unchecked line is your task. And so on down the list. If every sub-story `tasks.md` is fully checked, the epic is complete — say so and stop; do not invent
new work.

## Step 2 — confirm you are the right owner

The task line carries `| Owner: … | Model: … | Review: … | SHA: …`. Read it before doing anything.

- If `Owner` does not match the agent running this session, **stop** and report: which task you found, what it is routed to, and that this session should not implement it.
- If `Model` names a model this session is not running, say so before proceeding.
- Note the `Review` gate now — if it names a sub-agent (`code-reviewer` / `greeks-analyst` / `roll-validator` / `options-strategist`), that gate is mandatory before commit per `CLAUDE.md` Agent
  AutoTrigger Rules.
- `greeks-parity-validation/` is gated on a council/strategist tolerance-band decision before any code — if the first unchecked box there is that consult, stop and flag it rather than implementing.
- Per README, 4 of the 9 stories are Antigravity handoffs (`sqlite-backup-cron`, `docs-navigation-and-staleness`, `logging-migration-completion`, and check the current `Owner` field for any others
  reassigned since). For those, route via `.claude/skills/handoff-antigravity/SKILL.md` rather than implementing inline; Claude still runs the Phase Completion Output verification (SHA match, test
  count) before closing.

## Step 3 — load the sub-story context

Read that story's own `prompt.md` for its protocol and gate checks, and its `stories.md` for the task's full spec. The story dir's `tasks.md`/`stories.md` are the canonical spec for that follow-up —
there is no separate root spec document for this epic (unlike `backtest-engine/`, which points into `BACKTEST_PLAN_PHASE1.md`).

## Step 4 — implement, verify, record

Follow the sub-story `prompt.md`'s protocol: implement (or hand off to Antigravity per Step 2), run the test gate, run the `Review` gate if flagged, commit via `.claude/skills/commit/SKILL.md`
(execute it, do not draft it), set `SHA:` on the task line + tick the box, update this epic's `README.md` Stories status if it tracks one, add one line to `TODOS.md`.

**Stop.** One task per session — do not proceed to the next unchecked item in any story.
