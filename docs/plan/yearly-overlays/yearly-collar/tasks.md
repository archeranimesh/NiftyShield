# Yearly Collar — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit.

**Open: YL-1, YL-2.**

- [ ] **YL-1** — `--expiry-type {monthly,yearly}` on `--auto-collar`; `auto_collar_bootstrap` and `_validate_collar_pairs` enforce one shared December expiry | Owner: Antigravity | Model: n/a |
  Review: code-reviewer | SHA: —
- [ ] **YL-2** — `CollarOverlayV1` yearly instance: DTE_REVIEW and re-entry gates read the policy | Owner: Claude | Model: claude-sonnet-5-5 | Review: greeks-analyst | SHA: —

## Story done when

- **YL-1** — pair on one December expiry opens; mismatched pair rejected; monthly collar unchanged.
- **YL-2** — yearly collar exit/re-entry tests green; monthly tests unchanged.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
