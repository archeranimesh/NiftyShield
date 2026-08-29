# Repo-wide reflow — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation spec.

**Open: DFM-5.**

- [ ] **DFM-5** — reflow every in-bounds `.md` to fill-to-≤200, per-directory commits; update the line-style rule | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>

## Story done when

- **DFM-5** — `reflow_md.py --check` is clean on every repo `.md` except `docs/archive/**` and `docs/plan/_TEMPLATE/**`; each commit is word-diff clean on reflow hunks; `docs/plan/README.md`
  §"Markdown line style" is updated to drop the POC-folder carve-out.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box (DFM-5 has multiple commits — tick it on the last one). Then update the epic `README.md` story-list status column and add one line
to `TODOS.md` Session Log.
