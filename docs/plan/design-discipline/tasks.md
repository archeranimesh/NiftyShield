
# Design Discipline — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: DD-1..DD-10.**

- [ ] **DD-1** — Verify the bug-to-principle matrix against bug bodies; write `docs/refactor/bug-principle-evidence.md` | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DD-2** — Audit the 23 GoF patterns for Python applicability; write `docs/refactor/gof-python-applicability.md` | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DD-3** — Write the two-tier decision card (`docs/refactor/decision-card.md`, ≤40 lines); absorbs checklist §1–3 | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DD-4** — `scripts/dev/design_scan.py`: tested read-only CLI emitting a per-module conformance scorecard | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **DD-5** — Baseline report: scorecard, churn × complexity × bug hotspots, top-5 hand-scored, latency axis, refactor ROI ranking | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DD-6** — `design-check` skill + CLAUDE.md / `AGENTS.md` plan-gate rewording (Design clause, widened trigger) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DD-7** — Mandatory "Design lens" in the bug template and bug close, for `src/` and `scripts/` bugs only | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DD-8** — Presence hook: warn on `src/`/`scripts/` edit with no Design review block; add design line to `UserPromptSubmit` reminder | Owner: Claude | Model: claude-sonnet-5 | Review: none |
  SHA: —
- [ ] **DD-9** — Reconcile `code-review-checklist.md` (keep §1–3, §5 for refactor stories, drop §4 and §6) and wire it into the `code-reviewer` agent | Owner: Claude | Model: claude-sonnet-5 | Review:
  none | SHA: —
- [ ] **DD-10** — Log ranked refactor stories from the DD-5 ROI list in `TODOS.md` (not executed here) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **DD-1** — Every closed and open bug has a row: root cause, principle, blast radius it would have limited.
- **DD-2** — All 23 patterns have one verdict (built into Python / use as-is / use in Python-native form / not applicable); every "use" verdict cites an in-repo example or bug id; no verdict
  contradicts `design-principles.md`, or that doc is amended.
- **DD-3** — Card is ≤40 lines, Tier 1 and Tier 2, each trigger with an in-repo example.
- **DD-4** — Scan runs offline over `src/` and `scripts/`, one function per check, unit-tested with a happy path and an edge case each.
- **DD-5** — Report ranks hotspots and refactors, hand-scores the top 5, and keeps latency findings separate from design findings.
- **DD-6** — A plan line without a Design clause is rejected by the protocol text in both CLAUDE.md and `AGENTS.md`.
- **DD-7** — Closing a `src/` or `scripts/` bug without a Design lens is blocked or flagged.
- **DD-8** — Hook warns as described; the block switch is one documented line, flipped about one week after merge.
- **DD-9** — `code-reviewer` output cites the card's triggers on a seeded violation, and the checklist no longer contains inapplicable sections.
- **DD-10** — Top-ranked refactors appear in `TODOS.md` as pointer-only items naming the bugs they would have prevented.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md` for a single story, the epic `README.md` story
list for an epic sub-story) and add one line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
