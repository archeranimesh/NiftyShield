
# Design Baseline — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: DBL-1..DBL-4.**

- [ ] **DBL-1** — `scripts/dev/design_scan.py`: tested read-only CLI emitting a per-module conformance scorecard | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **DBL-2** — Baseline report: scorecard, churn × complexity × bug hotspots, top-5 hand-scored, latency axis, refactor ROI ranking | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DBL-3** — Log ranked refactor stories from the DBL-2 ROI list in `TODOS.md` (not executed here) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **DBL-4** — Calibration review: re-run the scan, tally recurring lens principles, decide the hook warn-to-block flip | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **DBL-1** — Scan runs offline over `src/` and `scripts/`, one function per check, unit-tested with a happy path and an edge case each.
- **DBL-2** — Report ranks hotspots and refactors, hand-scores the top 5, and keeps latency findings separate from design findings.
- **DBL-3** — Top-ranked refactors appear in `TODOS.md` as pointer-only items naming the bugs they would have prevented.
- **DBL-4** — Calibration report cites the re-run scan and bug counts, and the hook mode matches its decision.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story table, in `docs/plan/README.md` if the epic row changes, and add one
line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
