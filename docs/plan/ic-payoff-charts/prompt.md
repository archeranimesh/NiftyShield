# IC Payoff Charts — prompt (router)

Central entry point for this epic. `/work` loads this file, **not** a sub-story `prompt.md`. Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else, then follow the steps below to find and
run exactly one task.

**Origin:** `README.md` in this folder — the epic index. Read it if you have not this session; it carries the scope decisions, the ordered story list, the cross-cutting constraints (non-fatal send
contract, additive-send rule, renderer-degrades rule, message budget), and the `greeks-bs-fallback/` dependency this router's logic depends on.

---

## Step 1 — find the next task

Story order is fixed — it is the row order of the **Stories** table in this folder's `README.md`:

1. `chart-core/` — expiry payoff chart + `send_photo` plumbing + lifecycle wiring. Depends on: nothing.
2. `chart-model-overlay/` — T+0 curve + ±1σ/±2σ bands + POP. Depends on: `chart-core/` complete **and** `greeks-bs-fallback/` GF-2 + GF-3 shipped.

Do not jump ahead even if a later task looks more urgent.

Open `chart-core/tasks.md`. If it has any unchecked `- [ ]` line, the first one (top to bottom) is your task — stop searching, go to Step 2. Only if every box in `chart-core/tasks.md` is checked:
**first** confirm `greeks-bs-fallback/` GF-2 and GF-3 are ticked in `docs/plan/greeks-bs-fallback/tasks.md`. If they are not, the epic is blocked — say so and stop. If they are, open
`chart-model-overlay/tasks.md`; the first unchecked line is your task. If every sub-story `tasks.md` is fully checked, the epic is complete — say so and stop.

## Step 2 — confirm you are the right owner

The task line carries `| Owner: … | Model: … | Review: … | SHA: …`. Read it before doing anything.

- If `Owner` does not match the agent running this session, **stop** and report: which task you found, what it is routed to, and that this session should not implement it.
- If `Model` names a model this session is not running, say so before proceeding.
- Note the `Review` gate now — `code-reviewer` is mandatory before every code commit in this epic (financial-logic surface); `greeks-analyst` is additionally blocking on any task touching
  `paper_ic_snapshot.py`, the `IronCondor*` classes, or option-chain IV.

## Step 3 — load the sub-story context

Read that story's own `prompt.md` for its hard constraints (test-gate command, the non-fatal and renderer-degrades contracts, coordination checks) and its `stories.md` for the task's full spec.
Neither sub-story has a `schema.md` — this epic changes no DB schema.

## Step 4 — implement, verify, record

Follow the sub-story `prompt.md`'s protocol: implement, run the test gate, run the `Review` gate(s) if flagged, commit via `.claude/skills/commit/SKILL.md` (execute it, do not draft it), set `SHA:` on
the task line + tick the box, update this epic's `README.md` **Stories** table status column, add one line to `TODOS.md`.

**Stop.** One task per session — do not proceed to the next unchecked item in any story.
