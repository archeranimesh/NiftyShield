# Planning protocol

> How to structure a multi-week refactor as trackable, resumable, reviewable work — so a long-running effort survives many separate sessions (human or AI-assisted) without losing track of what's done,
> what's next, or why a decision was made.

## The core unit: a story folder

A **story** is the smallest independently-schedulable unit of refactor work — one coherent deliverable with its own task list. Give every story its own folder with a fixed, small file set:

| File | Required? | Holds |
|---|---|---|
| `prompt.md` | required | Why the story exists (the audit evidence/motivation), session-start instructions, scope guard (explicit in/out of bounds), task overview. |
| `tasks.md` | required | The working checkbox list — one checkbox per task id, top to bottom, in execution order. |
| `stories.md` | required | Per-task spec: files to change, what to implement, tests required, commit message template. |
| `schema.md` | conditional | Schema/DDL definitions, only when the story changes persistent storage shape. |
| `plan.md` / `spec.md` | optional | A file-by-file plan or audit-evidence table for a large/complex story — no task checkboxes of its own. |

Keep the file set small and fixed on purpose: an extra loose `.md` file in a story folder that *also* carries task checkboxes creates a second source of truth that can silently drift from `tasks.md`.
If you need more narrative, add it inside the required files or as a non-checkbox `plan.md`/`spec.md`, never as a new ad hoc file with its own checkbox list.

### Why `prompt.md` matters as much as the task list

`prompt.md` is what lets a session — possibly a different person, possibly a different AI agent, possibly the same one a week later — pick up a half-finished story cold. It should state, every time,
in this order:
1. The one-sentence deliverable.
2. The session-start ritual (read whatever context doc exists, acknowledge it, then find the first unchecked task and read *only* that task's spec before writing anything).
3. "Why this story exists" — the audit evidence or motivating finding, cited concretely (which files, what was found), not asserted abstractly.
4. An explicit scope guard: a bulleted "in bounds" and "out of bounds" list. This is what prevents scope creep from one session to the next — without it, each new session re-derives (or mis-derives)
   what's actually allowed.
5. Session-start load hints — which *other* docs/files this story's tasks depend on, so a session doesn't have to rediscover the dependency graph from scratch.

### One task per session, done fully, then stop

The discipline that makes multi-session work tractable: each session finds the first unchecked task, reads that task's full spec, completes it fully (implementation + tests + docs + commit), and stops
— it does not start a second task in the same session "while it's fresh." This keeps each session's context small (faster, cheaper, less error-prone) and keeps `tasks.md` an accurate, checkable record
of exactly how much is done at any point, even across an arbitrary gap between sessions.

## Grouping stories: the epic

Once a handful of related stories exist, group them under an **epic** folder: a `prompt.md` (a router listing its stories in a fixed order) and a `README.md` (the shared brief — why the epic exists,
architecture diagram, cross-cutting constraints, a status table of its stories) at the epic root, with each story nested as its own sub-folder underneath. The epic root carries no `tasks.md` of its
own — every checkbox lives in a sub-story's `tasks.md`; the epic's `README.md` status table is a progress *view*, not a second source of truth.

Don't force this structure prematurely: create stories as plain, standalone folders first; only wrap them in an epic once a real grouping need emerges (e.g. several stories share one blocking
dependency or one architecture). Retrofitting an epic wrapper around existing stories is cheap; inventing epic structure before you know the real groupings is not.

### What belongs in an epic's `README.md`

- **Why this epic exists**, tracing back to the audit/motivation, same as a story's `prompt.md`.
- **Scope decisions** — explicit calls made while scoping (e.g. "this sub-story integrates with an existing solution rather than re-implementing"), dated, with who/what confirmed them.
- **Architecture diagram** — one diagram showing how the epic's stories relate to each other and to what they depend on / consume, authored at design time (before implementation starts), not deferred
  to whichever session happens to be implementing.
- **Cross-cutting constraints** — rules that apply to every story in the epic (e.g. "every adapter test must assert both X and Y," "every module gets its own exception hierarchy") stated once at the
  epic level, cited by each story rather than restated and risking drift.
- **Supersession / coordination notes** — dated entries recording a decision made elsewhere that affects this epic, without this epic's own files implementing that decision itself. This is how a
  design decision made in one story (e.g. a cross-cutting logging convention) gets a durable pointer in every consumer epic's README without that design story reaching into and editing each consumer's
  files.

## Design review as its own phase, before implementation starts

Once several stories/epics have been scoped but before any of them produce code, run a dedicated **pre-implementation design review** pass across all of them together. This catches two kinds of defect
that are expensive to fix after the fact and cheap to fix before:

1. **Concrete, blocking defects** — e.g. a method-name mismatch between one story's planned interface and another story's planned consumer of it, which would fail the moment either is picked up.
2. **Pattern-level inconsistencies** — the same SOLID/extensibility gap recurring across multiple stories' plans (missing exception wrapping, inconsistent config pattern, missing DIP injection) that's
   cheaper to standardize once, across all affected stories' plans, than to catch piecemeal during N separate implementation reviews later.

Record findings the same way a story records anything: an audit-evidence table (`spec.md`), then per-finding fix tasks (`stories.md`/`tasks.md`). Low-risk, obvious fixes can apply directly during the
review; anything touching an already-checked-complete task in another story needs its own follow-up task, not a silent edit to someone else's closed work.

## Archiving completed work without losing its history

Once a standalone story's task list shows every task complete, move its folder from the active-plan location to an archive location (e.g. a scripted `git mv` from `docs/plan/<slug>` to
`docs/archive/<slug>`), and mechanically rewrite every cross-reference to the old path across the rest of the tree (other stories, the project's root context doc, any guide docs) in the same operation
— don't leave stale paths for a future session to trip over. Automate this with a script once you've done it manually a handful of times; back it with a non-blocking pre-commit check that warns
(without blocking) whenever a story looks complete but hasn't been archived yet, as a safety net for the case where the step is simply forgotten.

An epic stays in the active-plan location until *every* one of its sub-stories is archived — don't partially archive an epic.

## Running a multi-story epic in one sitting (optional, use with a backstop)

If you want to drive several of an epic's stories in a single extended session rather than spreading them across separate sessions, each story's independent scoping (its own `prompt.md`/
`tasks.md`/`stories.md`, its own first-unchecked-task) makes it a natural unit to delegate to a fresh sub-agent/sub-session per story — reading only that story's own files plus the epic's shared
`README.md`, never the whole epic's accumulated transcript. This keeps each story's context small even when run back-to-back.

If instead you drive many task segments inside one single continuous session with no re-check between them, expect two specific failure modes to recur: a session stops re-reading the shared context
doc on each resumed segment, and a session stops restating its plan / waiting for go-ahead before each segment's edits, treating the earlier session's approval as still covering the new segment. Put a
forced checkpoint (e.g. every N turns, require a plan/go-ahead confirmation) as a backstop if you choose this mode — but delegating story-by-story to fresh sessions avoids needing that backstop to
fire at all, since each fresh session's own first turn already re-does the context read and the plan-and-wait step naturally.
