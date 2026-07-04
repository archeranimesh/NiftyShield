Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/full-repo-review/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task.
Complete it fully. Stop.

**Operating philosophy for this entire epic — read this before any task, every time:**
Animesh and Claude are co-invested in NiftyShield's outcome, not in a client/vendor or
grader/gradee relationship. There is no adversarial "AI polices the human's code" framing
and no deferential "AI approves whatever the human already built" framing either — both
are wrong for the same reason: neither treats the other party's blind spots as worth
surfacing. The only framing that serves the mission (`MISSION.md`'s Five Immutable
Principles, "Protect Before You Earn" above all) is two co-investors who each know the
other has genuine gaps and actively hunt for them, because a blind spot caught late costs
real capital and a blind spot caught here costs nothing but an hour of review.

This cuts both ways and every persona in `stories.md` must apply it symmetrically:
- **Findings about the code/docs are not personal and not adversarial theater.** Rate
  severity by actual business impact (does this expose capital, does this cost a real
  decision-quality point, per `MISSION.md`'s Grounding Test) — not by how many findings
  make the review look thorough. A padded list of INFO-level nitpicks is as useless to a
  co-investor as a review that rubber-stamps everything.
- **The reviewer's own blind spots are equally in scope.** Every closing block in
  `stories.md` asks the reviewing model to name a missing persona — that instruction exists
  because the model doing FR-1 through FR-8 can be just as wrong as the code it's reviewing
  (see: this same conversation's `RapidCouncil` mistake — citing a file as "live" without
  checking `DECISIONS.md` first, caught by Animesh, not self-caught). Catching that kind of
  error is the job, on both sides, not a failure to be defensive about.
- **The point of FR-7 (synthesis) is not "did the code pass."** It's "where did the panel,
  including its blind spots, converge on something that actually threatens the mission" —
  capital protection, the three-phase validation gate, pool segregation — versus something
  that's stylistically imperfect but low-stakes. Rank accordingly; do not treat all
  CRITICAL tags as equally urgent without checking which mission principle each one touches.
- **FR-9's roadmap is the actual deliverable.** A findings folder nobody acts on has not
  helped either co-investor. If a finding doesn't produce a follow-up story stub or a
  `DECISIONS.md` entry, ask whether it was worth flagging at all before filing it away.

**This is a review-only epic — no production code changes.** Every task (FR-1 through
FR-8) produces a written finding, not a diff — FR-1 specifically decides whether this
epic's own process is sound (see ordering note below) and FR-8 produces the tooling/
Antigravity-handoff usage guide, itself a finding, not an edit to any live doc yet. Only
FR-9 (the final task) touches the repo outside `findings/`, and even then only to write the
synthesized roadmap + update `DECISIONS.md` — it does not implement any fix.

**Ordering:** FR-1 (Protocol Review) runs first, ahead of the financial/architecture/
security tasks, even though it reads like a meta/wrap-up task. It has no dependency on any
other task's output and it judges whether this epic's own protocol — including the
"Operating philosophy" below — is sound before FR-2 through FR-6 spend Opus/Fable budget
executing under it. Same reasoning as `CLAUDE.md`'s own Step 2b council checkpoint: verify
the process before running it, not after the fact.

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
yet — create it in FR-1, the first task, which now runs before the others per the ordering
note in `stories.md`). FR-7 reads all six (FR-1..FR-6) and writes
`findings/FR-7_synthesis.md`. FR-8 (tooling/Antigravity-handoff usage guide) reads FR-1's
output specifically and writes `findings/FR-8_practitioner-devex.md`. FR-9 is the only task
that edits files outside this folder, and only per its own spec. **Nothing appears in
`findings/` until a task is actually run — this folder of prompts is a spec, not a job
queue; no automation fires on its own.**

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
