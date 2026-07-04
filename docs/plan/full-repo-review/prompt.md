Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/full-repo-review/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task.
Complete it fully. Stop.

**This is a review-only epic — no production code changes.** Every task (FR-1 through
FR-8) produces a written finding, not a diff — FR-8 specifically produces the tooling/
Antigravity-handoff usage guide, itself a finding, not an edit to any live doc yet. Only
FR-9 (the final task) touches the repo outside `findings/`, and even then only to write the
synthesized roadmap + update `DECISIONS.md` — it does not implement any fix.

**Origin:** Two independent chat-session reviews (2026-07-04) surfaced findings the
existing per-commit gates (`code-reviewer`, `test-runner`, `greeks-analyst`,
`roll-validator`) don't catch because they operate on diffs, not on repo-wide consistency:
`LOGGING.md`'s own migration checklist undercounts real non-compliant files by ~3-4x (6
claimed vs. 20 files still on bare `logging.getLogger`, 22 scripts never calling
`setup_logging()`); `REVIEW.md` §G7 (mandates `%`-style logger calls) directly contradicts
`LOGGING.md` (mandates structlog keyword args) and has never been reconciled; `CONTEXT.md`
claims `src/nuvama/CLAUDE.md` doesn't exist when it does (47 lines); `DECISIONS.md`
(2026-07-04 entry) already found `RapidCouncil` and `SignalAggregator` were built as
unreconciled duplicate consensus mechanisms. If three separate blind spots surfaced from a
handful of spot-checks, a structured multi-model, multi-persona review of the full repo —
design docs, source, tests, and the prompting/protocol layer itself — is warranted as a
**one-time** audit. This is explicitly not a proposal to add a standing review gate;
`code-reviewer`/`test-runner`/`greeks-analyst`/`roll-validator` remain the daily mechanism.

**Why multiple models, not one:** different models have uncorrelated failure modes — the
value is in disagreement surfacing a blind spot, not in consensus alone (consensus with a
single systematically-wrong assumption baked into all reviewers proves nothing). Model
assignment per task is in `stories.md` and is **not interchangeable** — a task assigned to
Opus for deep single-pass financial judgment should not be run on Sonnet to save cost, and
a task assigned to Fable for long-horizon cross-document synthesis should not be split
across several shorter Sonnet sessions, because the point of that assignment is exactly the
capability the cheaper model lacks.

**Folder to attach in each session:** every task in `stories.md` states an explicit
"Folder/files to attach" line. Attach only that scope for that session — do not attach the
full repo for a task scoped to `docs/` only, and do not scope down a task that explicitly
needs full-repo visibility (FR-2, FR-5, FR-7).

**Persona discipline:** every task's prompt in `stories.md` ends with the same closing
instruction — state the persona you are reviewing as, and name at least one perspective
this panel composition does not otherwise cover. Do not skip this even if nothing comes to
mind; write "none identified" explicitly rather than omitting the section. FR-7 exists
specifically to collect and act on these self-reported gaps — a persona that every single
task says "none identified" for is itself a signal the panel may be too narrow or the
prompt too leading.

**Output contract:** each of FR-1 through FR-6 writes one file to
`docs/plan/full-repo-review/findings/<task-id>_<persona-slug>.md` (directory does not exist
yet — create it in FR-1, the first task). FR-7 reads all six and writes
`findings/FR-7_synthesis.md`. FR-8 (tooling/Antigravity-handoff usage guide) reads FR-5's
output and writes `findings/FR-8_practitioner-devex.md`. FR-9 is the only task that edits
files outside this folder, and only per its own spec. **Nothing appears in `findings/`
until a task is actually run — this folder of prompts is a spec, not a job queue; no
automation fires on its own.**

**How a task actually gets executed — pick one mechanism per task, state which in your
`| Model:` note when you tick the box:**

1. **Subagent with a model override, run from inside an existing Claude session** (the
   `Agent` tool's `model` parameter accepts `opus`, `sonnet`, `fable`). Whoever is driving
   that outer session spawns the task with a self-contained prompt built from this file +
   the matching section of `stories.md`, and — critically — **explicitly instructs the
   subagent to call `Write` and save its findings to the exact output path** given in
   `stories.md` before returning. A subagent's returned message is not saved anywhere by
   itself; if the prompt doesn't tell it to write the file, no file appears. Verify the file
   exists on disk after the subagent reports back — do not trust the summary alone.
2. **Manual cross-session run** — open a new chat in the Claude app, pick the model from the
   model selector in that session (this is the only way to actually get Fable specifically,
   since it is not selectable as a subagent override in every environment), attach the
   folder/files `stories.md` specifies for that task, paste in that task's full spec
   (context + task steps + closing block), then take the model's response and save it
   yourself — paste it into a new file at the exact `findings/` path given, or ask that same
   session to write the file if it has file tools in that context. Either way, the file
   landing at the right path is a manual step you must not skip after the model responds.

Whichever mechanism is used, **the task is not complete until the file physically exists at
the stated path** — a good response in a chat window that never gets saved to
`docs/plan/full-repo-review/findings/` has produced nothing `tasks.md` can be ticked for.

**Test gate:** none of FR-1–FR-7 touch code, so no `pytest` run is required for them. FR-8
may add new story stubs to `docs/plan/` (docs only) — no code, so still no test gate.

**Commit:** one commit per task, format from `.claude/skills/commit/SKILL.md`, type `docs`
scope `plan`. Execute the commit — do not draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha> | Model: <model used>`. Add one
line to `TODOS.md` per task.

**Stop.** Do not proceed to the next unchecked item.
