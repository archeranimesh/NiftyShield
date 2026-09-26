
# Strategy Module Refactor & AI-Collaboration Blueprint — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: BP-1, BP-2, BP-3, BP-4, BP-5.**

- [ ] **BP-1** — Run `/md-organize`; resolve or confirm-clear the `TODOS.md`/`DECISIONS.md` growth flagged in discussion | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **BP-2** — Extend `paper-pnl-golden-tests/` scope to `ic_nifty_v1`/`v2` entry/roll/close decision points | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **BP-3** — Draft + run council question: `ic_nifty_v1`/`v2` decomposition boundary | Owner: Animesh | Model: n/a | Review: none | SHA: <—>
- [ ] **BP-4** — Write council-ruled file-by-file decomposition `plan.md` (no code) | Owner: Claude | Model: claude-opus-5-5 | Review: none | SHA: <—>
- [ ] **BP-5** — Draft generalized AI-collaboration blueprint for `protocol-reference` §3 from this case study | Owner: Claude | Model: claude-opus-5-5 | Review: none | SHA: <—>

## Story done when

- **BP-1** — `/md-organize`'s Quick Checklist is clean, or its findings are folded into this story's own notes if it surfaces something new.
- **BP-2** — `paper-pnl-golden-tests/tasks.md` has explicit tasks (or an amended scope note) covering `ic_nifty_v1`/`v2` decision-point fixtures, not just `PaperTracker` P&L math.
- **BP-3** — A `docs/council/` file exists ruling on the decomposition boundary, and `DECISIONS.md` records the ruling per `protocol-reference` §1.
- **BP-4** — `docs/plan/strategy-refactor-blueprint/plan.md` exists, names every file + block to move, the commit order, and each commit's test/review gate — council-approved, zero code written.
- **BP-5** — A drafted section (as a `docs/plan/strategy-refactor-blueprint/` extra file, not yet merged into `protocol-reference`) exists, generalizing the routing this story actually used.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md` for a single story, the epic `README.md` story
list for an epic sub-story) and add one line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
