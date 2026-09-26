
# Cross-Project Claude Template Blueprint — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task spec.

**Open: PTB-6, PTB-7, PTB-8, PTB-9.**

**Re-planned 2026-09-26 (after PTB-4):** the story's end state is now a self-contained `project-scaffold` — every tier's files, the `python/` overlay, a per-item `scaffold.sh`, and the tier/trigger
guide itself all live there, so nothing a consuming project needs is left behind in NiftyShield. PTB-5 no longer hands off to a separate build story (the repo already exists, Tier 0/1 are committed in
it); PTB-7..PTB-9 added. SHAs below are NiftyShield commits; `project-scaffold` commit SHAs are recorded in `plan.md` §Status.

- [x] **PTB-1** — Write up 2026-09-26 discussion as `plan.md` draft (tier table + open questions) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: dccc34a
- [x] **PTB-2** — Concretize Tier 0 (Bootstrap) file skeletons, including stripped `commit` + `session-close` skills (re-scoped from PTB-3, 2026-09-26 — both are Tier 0 per `plan.md`'s own tier table)
  | Owner: Animesh | Model: n/a | Review: none | SHA: f28959d
- [x] **PTB-3** — Concretize Tier 1 (Recurring work): `work` + `new-story` skill genericization only (narrowed from PTB-2, 2026-09-26) | Owner: Animesh | Model: n/a | Review: none | SHA: cf515b5
- [x] **PTB-4** — Concretize Tier 2/3 gating criteria + generalized model-routing buckets | Owner: Claude | Model: claude-opus-5-5 | Review: none | SHA: 783a68e
- [x] **PTB-5** — Distribution decision + `scaffold.sh` per-item selection and merge mechanics (re-scoped 2026-09-26: was "hand off template-repo build to a new story") | Owner: Claude | Model:
  claude-opus-5-5 | Review: none | SHA: 5110b0a
- [ ] **PTB-6** — Concretize the `python/` overlay (renamed from the earlier `python-addon/` concept, deferred at PTB-2, 2026-09-26 — now in scope: most future projects, CardLedger and TaxCalculation
  included, are Python) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **PTB-7** — Write Tier 2 (`stakes/`, `test-runner/`, `multi-surface/`) into `project-scaffold`, genericized, in PTB-5's fragment shape | Owner: Claude | Model: claude-sonnet-5 | Review: none
  | SHA: <—>
- [ ] **PTB-8** — Write Tier 3 (Rule 0 bundle, `md-organize`, `state_doc_freshness`, `weekly-audit`) into `project-scaffold`, genericized, in PTB-5's fragment shape | Owner: Claude | Model:
  claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **PTB-9** — Make `project-scaffold` self-documenting (root README + shipped trigger guide), end-to-end validation, archive this story | Owner: Claude | Model: claude-opus-5-5 | Review: none |
  SHA: <—>

## Story done when

- **PTB-1** — `plan.md` exists and captures the discussion so far without loss (tier table, scratch/tmp distinction, architecture-doc trio, model-routing sketch, all open questions from `prompt.md`
  §"Perspectives not covered").
- **PTB-2** — Tier 0's exact starting file set (contents, not just names) is written and Animesh has confirmed it's what a brand-new project should literally start with.
- **PTB-3** — Tier 1's skill/doc set is written with NiftyShield-specific content stripped out, confirmed generic.
- **PTB-4** — Tier 2/3 trigger conditions are concrete enough to apply to a real project (not just "correctness-critical," but a checklist), and the three model-routing buckets are named with what
  actually goes in each.
- **PTB-5** — The distribution decision is recorded in `DECISIONS.md`; `scaffold.sh` is committed in `project-scaffold`, selects Tier 0 always plus each later piece by its own question (no numeric
  tier level), never overwrites existing files, and merges `CLAUDE.md` / `.claude/settings.json` / `.gitignore` instead of overwriting them; `tier2/`/`tier3/` are restructured into per-piece folders;
  validated against a scratch destination.
- **PTB-6** — `python/`'s exact file set (contents, not just names) is written to `project-scaffold/`, its placement decided (inside a tier, sibling at root, or its own opt-in overlay) and stated,
  Animesh has confirmed it's what a brand-new Python project should start with beyond Tier 0's language-agnostic baseline, and `scaffold.sh` asks "is this a Python project?" and overlays `python/`
  flattened when the answer is yes.
- **PTB-7** — Every Tier 2 piece listed in `plan.md` §"What `tier2/` and `tier3/` will hold" exists in `project-scaffold/tier2/`, with no NiftyShield-domain content, every hook registered through
  PTB-5's `settings.json` merge, and every `CLAUDE.md` addition shipped as a fragment; a scaffold run with each Tier 2 piece selected produces valid JSON and runnable hooks.
- **PTB-8** — Same as PTB-7, for every Tier 3 piece in `project-scaffold/tier3/`.
- **PTB-9** — `project-scaffold/README.md` carries the full tier/trigger guide (so `plan.md` is no longer the only copy), a scaffolded project ships a compact trigger list telling it when to add the
  next piece, the three reference configurations (plain Tier 0, CardLedger-shaped, TaxCalculation-shaped) scaffold cleanly, Animesh confirms `project-scaffold` is ready to use, and this story is
  archived per §Conventions *Completion → archive*.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md`) and add one line to `TODOS.md` Session Log. When
the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
