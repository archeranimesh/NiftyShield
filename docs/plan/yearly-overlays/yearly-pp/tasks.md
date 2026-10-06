# Yearly PP — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit.

**Open: YP-1, YP-2.**

- [ ] **YP-1** — `--expiry-type {monthly,yearly}` on `--auto-pp`; `auto_pp_bootstrap` resolves December, records under the yearly namespace | Owner: Antigravity | Model: n/a | Review: code-reviewer |
  SHA: —
- [ ] **YP-2** — Yearly PP roll window (`_open_pp_dte`, `_PP_ROLL_DTE_THRESHOLD`) and crash-monetize re-entry gate read the policy | Owner: Claude | Model: claude-sonnet-5-5 | Review: roll-validator |
  SHA: —

## Story done when

- **YP-1** — dry run on fixtures opens a December put under the yearly namespace; monthly path unchanged.
- **YP-2** — roll tests green for both tenors; `roll-validator` returns clean.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
