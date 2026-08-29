# Plan-folder conversion — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation spec and the per-folder progress
table.

**Open: DFM-1, DFM-2, DFM-3, DFM-4.**

- [ ] **DFM-1** — enumerate + tier every non-archived `docs/plan/` folder (A/B/C/D), record the table in `stories.md` | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **DFM-2** — convert every tier-A folder (full: structure + `stories.md` covers every task + reflow); 1 commit/folder | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **DFM-3** — convert every tier-B folder (structure + 1-line digest per shipped task + reflow); 1 commit/folder | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **DFM-4** — reflow-only pass on every tier-C folder (structure already canonical) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>

## Story done when

Acceptance criteria — prose, no checkboxes. Verified at story close; per-task status lives only in the working list above.

- **DFM-1** — `stories.md` carries a row for every non-archived `docs/plan/` folder with its tier, current shape, and the specific work needed; the tier split is confirmed with Animesh.
- **DFM-2** — every tier-A folder passes `check_story_structure.py --all` and `check_checkbox_consistency.py` with no findings; its `stories.md` covers every task; its `.md` are fill-to-≤200.
- **DFM-3** — every tier-B folder has the canonical file set and canonical task lines; shipped tasks carry a one-line digest and their real SHA; its `.md` are fill-to-≤200.
- **DFM-4** — `reflow_md.py --check` is clean on every tier-C folder; the commit(s) are word-diff clean.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update the epic `README.md` story-list status column and add one line to `TODOS.md` Session Log. For DFM-2 / DFM-3, also tick
the folder's row in the `stories.md` progress table as each folder lands — the DFM task box itself is ticked only when the last folder in its tier is done.
