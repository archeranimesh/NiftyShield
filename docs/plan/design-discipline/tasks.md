
# Design Discipline — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: DD-1..DD-7.**

- [ ] **DD-1** — Verify the bug-to-principle matrix against bug bodies; write `docs/refactor/bug-principle-evidence.md` | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DD-2** — Write the two-tier decision card (`docs/refactor/decision-card.md`, ≤40 lines) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DD-3** — `design-check` skill + CLAUDE.md / `AGENTS.md` plan-gate rewording (Design clause, widened trigger) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DD-4** — Mandatory "Design lens" in the bug template and bug close, for `src/` and `scripts/` bugs only | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DD-5** — Presence hook: warn on `src/`/`scripts/` edit with no Design review block; add design line to `UserPromptSubmit` reminder | Owner: Claude | Model: claude-sonnet-5 | Review: none |
  SHA: —
- [ ] **DD-6** — Add the card's triggers to `code-review-checklist.md` and the `code-reviewer` agent prompt | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DD-7** — Log ranked refactor stories from DD-1 in `TODOS.md` (not executed here) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **DD-1** — Every closed and open bug has a row: root cause, principle, blast radius it would have limited.
- **DD-2** — Card is ≤40 lines, Tier 1 and Tier 2, each trigger with an in-repo example.
- **DD-3** — A plan line without a Design clause is rejected by the protocol text in both CLAUDE.md and `AGENTS.md`.
- **DD-4** — Closing a `src/` or `scripts/` bug without a Design lens is blocked or flagged.
- **DD-5** — Hook warns as described; the block switch is one documented line, flipped about one week after merge.
- **DD-6** — `code-reviewer` output cites the card's triggers on a seeded violation.
- **DD-7** — Top-ranked refactors appear in `TODOS.md` as pointer-only items.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md` for a single story, the epic `README.md` story
list for an epic sub-story) and add one line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
