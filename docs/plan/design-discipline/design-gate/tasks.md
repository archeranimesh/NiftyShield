
# Design Gate — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: DG-1..DG-9.**

- [ ] **DG-1** — Verify the bug-to-principle matrix against bug bodies; write `docs/refactor/bug-principle-evidence.md` | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DG-2** — Audit the 23 GoF patterns for Python applicability; write `docs/refactor/gof-python-applicability.md` | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DG-3** — Triage the remaining `docs/refactor/` docs (keep, merge or retire) and reconcile with module `CLAUDE.md`, `DECISIONS.md`, `REVIEW.md` | Owner: Claude | Model: claude-sonnet-5 |
  Review: none | SHA: —
- [ ] **DG-4** — Write the two-tier decision card (`docs/refactor/decision-card.md`, ≤40 lines); absorbs checklist §1–3 | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DG-5** — `design-check` skill + CLAUDE.md / `AGENTS.md` plan-gate rewording (Design clause, widened trigger) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DG-6** — Carry the gate to Antigravity handoff, `plan-loop` workers and the `new-story` scaffold | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DG-7** — Mandatory "Design lens" in the bug template and bug close for `src/`/`scripts/` bugs, enforced by a pre-commit check | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DG-8** — Presence hook: warn on `src/`/`scripts/` edit with no Design review block (`Design: n/a` escape hatch); add design line to `UserPromptSubmit` reminder | Owner: Claude | Model:
  claude-sonnet-5 | Review: none | SHA: —
- [ ] **DG-9** — Reconcile `code-review-checklist.md` (keep §1–3, §5 for refactor stories, drop §4 and §6) and wire it into the `code-reviewer` agent | Owner: Claude | Model: claude-sonnet-5 | Review:
  none | SHA: —

## Story done when

- **DG-1** — Every closed and open bug has a row: root cause, files touched, principle, blast radius it would have limited.
- **DG-2** — All 23 patterns have one verdict; every "use" verdict cites an in-repo example or bug id; no verdict contradicts `design-principles.md`, or that doc is amended.
- **DG-3** — All eight `docs/refactor/` files have a verdict; no rule is stated twice with different wording.
- **DG-4** — Card is ≤40 lines, Tier 1 and Tier 2, each trigger with an in-repo example.
- **DG-5** — A plan line without a Design clause is rejected by the protocol text in both CLAUDE.md and `AGENTS.md`.
- **DG-6** — Generated Antigravity handoff and `plan-loop` worker prompts both require a Design review.
- **DG-7** — Closing a `src/` or `scripts/` bug without a Design lens fails the pre-commit check.
- **DG-8** — Hook warns as described and accepts `Design: n/a`; the block switch is one documented line.
- **DG-9** — `code-reviewer` output cites the card's triggers on a seeded violation, and the checklist has no inapplicable section.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story table, in `docs/plan/README.md` if the epic row changes, and add one
line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
