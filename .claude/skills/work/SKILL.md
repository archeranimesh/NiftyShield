# NiftyShield — Work Session Entry-Point Skill

> Invoke at the start of any task-shaped session to route to the right work tree and load the
> right prompt.
> Trigger phrases: "work", "start work", "pick up a task", "/work"
>
> Goal: one front door for the two shapes of task work in this repo — feature stories
> (`docs/plan/<story>/`) and bug fixes (`docs/bugs/`). Instead of remembering which files to
> pull, invoke `/work`, pick the target, and let the skill load the prompt + first unchecked
> task + `CONTEXT.md` before handing to the normal protocol.

---

## This is a front-end, not a replacement

`/work` composes with the existing protocol — it does not bypass it. `task_protocol.sh`
(UserPromptSubmit) still fires on the invoking message, and this skill's last step hands
control to `CLAUDE.md` Step 2b (council checkpoint) → Step 3 (plan + go-ahead) → the rest of
the pre-task protocol unchanged. The skill only does the routing and file-loading that was
previously scattered prose in `CLAUDE.md` Step 1.

Open-ended discussion needs no `/work` — it proceeds as normal conversation, and its outcomes
get filed into one of the two trees below.

---

## Step A — Detect or ask

If the invoking message already names a target, skip straight to the matching branch:

- A story / RDO / epic id or story-folder name (`continue RDO-4`, `work SEP-2`,
  `docs/plan/greeks-bs-fallback/`) → **Feature branch**, pre-selected to that story.
- A bug id (`fix BUG-038`, `BUG-037`) → **Bug branch**, pre-selected to that entry.

Otherwise, `AskUserQuestion`:

- **Question:** "What are we working on?"
- **Options:** `Feature` (a story under `docs/plan/`) · `Bug` (an entry in `docs/bugs/`)

---

## Feature branch

1. Read `TODOS.md` → `## Feature Backlog`.
2. Present the **first 5** list items verbatim — for each: the list number, the title, the
   named next task (e.g. "starting at **GF-1**"), and the story path (`docs/plan/<story>/`).
   Do not re-order, summarise, or skip items; the list is already story-by-story priority
   ordered.
3. Operator picks one (or confirms the pre-selected story from Step A).
4. Classify the chosen folder (`docs/plan/README.md` §Conventions "Folder shapes"):
   - **Flat single-story folder** — has its own `tasks.md` (or legacy `<name>_tasks.md`).
   - **Epic root** — `prompt.md` + `README.md`, **no root `tasks.md`**; one sub-folder per
     story directly under it.
   Legacy epics with `phaseN/` or `stories/<ID>.md` sub-layers are handled the same way as
   an epic root — the sub-folder holding the first unchecked box is the active story.
5. Load context for the classified shape:

   **Flat story:**
   - `docs/plan/<story>/prompt.md` (design / why the story exists)
   - the story's `*_tasks.md` — identify the **first unchecked `- [ ]` task**; that is the
     session's task
   - the story's `*_stories.md` if present (spec / DoD detail)
   - the story's `schema.md` if present (DB-touching stories only)

   **Epic:**
   - `docs/plan/<epic>/prompt.md` (the router) + `README.md` (shared brief — story order,
     scope decisions, cross-cutting constraints)
   - walk the story list **in the fixed order the router states**; the active story is the
     first one whose `<epic>/<story>/tasks.md` still has an unchecked `- [ ]`. Do not skip
     ahead even if a later story looks more urgent.
   - for that story: its `prompt.md` + `stories.md` (+ `schema.md` if present), and the
     **first unchecked `- [ ]` task** in its `tasks.md` — that is the session's task
   - if every sub-story `tasks.md` is fully checked, the epic is complete — say so and stop.
6. Also read `CONTEXT.md` (authoritative codebase state — always required before code).
7. State: the chosen story (and parent epic if any), the first unchecked task id + text,
   its `| Owner | Model | Review |` values from the task line, and any load hints the
   story's `prompt.md` calls for (module `CLAUDE.md`, `DECISIONS.md`, `REFERENCES.md`,
   `BACKTEST_PLAN.md`, `LITERATURE.md` entries). If `Owner` is not this session's agent,
   stop and report — do not implement someone else's routed task.
8. Hand off to `CLAUDE.md` Step 2b — council checkpoint, then Step 3 plan + go-ahead, then
   the normal protocol. AutoTrigger agents fire per the `CLAUDE.md` table as implementation
   proceeds.

---

## Bug branch

1. Read `docs/bugs/prompt.md` (session-start protocol), then `docs/bugs/task.md` and
   `docs/bugs/bugs.md`.
2. Present every **open** entry — `🔴 Open` or `🟡 Fix in progress` status in `bugs.md`. For
   each: the `BUG-NNN` id, the one-line title, and the first unchecked `- [ ]` `**BNNN.x**`
   line from `docs/bugs/task.md`.
   - Diagnostic-only / awaiting-data entries (e.g. `🔍` status, "awaiting a live trading
     day") are not actionable — mention them once as still-open, do not offer them as a pick.
   - Skip unchecked `task.md` lines that sit outside a `BUG-ID` section or are blocked on a
     human/live-host action; name them once so they are not lost, per `docs/bugs/prompt.md`.
3. Operator picks one (or confirms the pre-selected bug from Step A).
4. Load, for the chosen bug:
   - its full `docs/bugs/bugs.md` entry (symptom / root cause / suggested fix)
   - its `docs/bugs/task.md` lines — identify the **first unchecked `**BNNN.x**`** line;
     that is the session's task
5. Also read `CONTEXT.md`.
6. Re-confirm the root cause against current code with the graph
   (`search_graph` / `get_code_snippet` / `trace_path`) before any plan — `bugs.md` is a
   snapshot at discovery time, not a live source of truth.
7. If the first unchecked line is a decision / scope question rather than an implementable
   step, surface it and stop — do not guess and proceed.
8. Hand off to `CLAUDE.md` Step 2b onward. Financial-logic bugs (delta, P&L, Decimal paths,
   BrokerClient boundaries) require the real `@code-reviewer` subagent against
   `git diff HEAD` before commit; `greeks-analyst` / `roll-validator` fire per the
   AutoTrigger table if the fix touches their surfaces.
