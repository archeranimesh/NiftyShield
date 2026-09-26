
# Cross-Project Claude Template Blueprint — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task spec.

**Open: PTB-2, PTB-3, PTB-4, PTB-5.**

- [x] **PTB-1** — Write up 2026-09-26 discussion as `plan.md` draft (tier table + open questions) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <pending>
- [ ] **PTB-2** — Concretize Tier 0 (Bootstrap) file skeletons | Owner: Animesh | Model: n/a | Review: none | SHA: <—>
- [ ] **PTB-3** — Concretize Tier 1 (Recurring work) skill/doc genericization | Owner: Animesh | Model: n/a | Review: none | SHA: <—>
- [ ] **PTB-4** — Concretize Tier 2/3 gating criteria + generalized model-routing buckets | Owner: Claude | Model: claude-opus-5-5 | Review: none | SHA: <—>
- [ ] **PTB-5** — Decide distribution mechanism; hand off template-repo build to a new story | Owner: Animesh | Model: n/a | Review: none | SHA: <—>

## Story done when

- **PTB-1** — `plan.md` exists and captures the discussion so far without loss (tier table, scratch/tmp distinction, architecture-doc trio, model-routing sketch, all open questions from `prompt.md`
  §"Perspectives not covered").
- **PTB-2** — Tier 0's exact starting file set (contents, not just names) is written and Animesh has confirmed it's what a brand-new project should literally start with.
- **PTB-3** — Tier 1's skill/doc set is written with NiftyShield-specific content stripped out, confirmed generic.
- **PTB-4** — Tier 2/3 trigger conditions are concrete enough to apply to a real project (not just "correctness-critical," but a checklist), and the three model-routing buckets are named with what
  actually goes in each.
- **PTB-5** — A distribution-mechanism decision is recorded in `DECISIONS.md`, and a new `docs/plan/` story exists (linked from here) scoped to building the actual template repo.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md`) and add one line to `TODOS.md` Session Log. When
the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
