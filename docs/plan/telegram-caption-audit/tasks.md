
# Telegram Message Caption-Fit Audit — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: TCA-1, TCA-2, TCA-3.**

- [ ] **TCA-1** — Inventory every Telegram message type and sender into findings.md | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: <—>
- [ ] **TCA-2** — Measure rendered MarkdownV2 length of each message type vs 1024/4096 | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: <—>
- [ ] **TCA-3** — Classify fit verdicts and write layout recommendations | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: <—>

## Story done when

- **TCA-1** — `findings.md` lists every distinct message type with trigger, source file and whether a chart accompanies it today.
- **TCA-2** — every row has measured min/typical/max escaped length, with the fixture or recorded sample each number came from.
- **TCA-3** — every row has a verdict and recommended layout, and the summary counts (fit / trim / split) are stated.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md` for a single story, the epic `README.md` story
list for an epic sub-story) and add one line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
