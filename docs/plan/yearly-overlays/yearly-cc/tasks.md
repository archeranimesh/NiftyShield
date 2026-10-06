# Yearly CC — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit.

**Open: YC-1, YC-2.**

- [ ] **YC-1** — `--expiry-type {monthly,yearly}` on `--auto-cc`; `auto_cc_bootstrap` resolves December and records under the yearly namespace | Owner: Antigravity | Model: n/a | Review: code-reviewer
  | SHA: —
- [ ] **YC-2** — `CCOverlayV1` yearly instance: exits (profit target, delta stop, DTE review) and re-entry read the yearly policy | Owner: Claude | Model: claude-sonnet-5-5 | Review: greeks-analyst |
  SHA: —

## Story done when

- **YC-1** — dry run on fixtures opens a December call under the yearly namespace; monthly path byte-identical.
- **YC-2** — yearly exit and re-entry tests green; monthly CC tests unchanged.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
