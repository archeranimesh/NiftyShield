
# Calendar Bi-weekly variant — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Story complete.** CB-1..CB-4 done (CB-1/2 Antigravity, reviewed). CB-4 added the cross-variant `OTHER_VARIANT_OPEN` entry guard its walk found missing.

- [x] **CB-1** — `BIWEEKLY` config and `BiweeklyCyclePolicy` (skip-current-weekly pair, back-to-back chain, handoff to monthly) | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: 6aca587
- [x] **CB-2** — `BiweeklyExitRule` (₹1,600 target, day 3-4 breach window, 200-point rule, same-pair redeploy, time exit) | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: 20817d1
- [x] **CB-3** — Register `paper_nifty_calendar_biweekly`: daemon, entry and snapshot scripts by variant, payoff registration, `Cal BW` label | Owner: Claude | Model: claude-sonnet-5-5 | Review:
  code-reviewer
  | SHA: 8e5794e
- [x] **CB-4** — Full-month two-variant integration test; close-out docs and cutover note update | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: <pending>

## Story done when

- **CB-1** — for a fixture month the policy yields the correct near and far expiries on each entry date, and never an entry whose hard exit overlaps the next monthly entry window.
- **CB-2** — every bi-weekly exit path is hit by a test, including the 200-point rule boundary and same-pair redeploy keeping the original max-hold date.
- **CB-3** — the second variant runs through the same shell, scripts and renderers with additive edits only; no `if variant` was added anywhere.
- **CB-4** — an offline test walks a full month across both strategies; docs and cutover note updated.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md` for a single story, the epic `README.md` story
list for an epic sub-story) and add one line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
