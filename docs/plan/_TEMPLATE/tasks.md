<!-- Copy with the folder. Delete these HTML comments once filled in. -->

# <Story title> — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task.
Each task = one commit unless noted. See `prompt.md` for why the story exists;
see `stories.md` (if present) for per-task implementation detail.

**Open: <task ids>.**

- [ ] **<ID-1>** — <what this task does> →
  verify: <the check that proves it done>.
- [ ] **<ID-2>** — <what this task does> →
  verify: <check>.

## Epic done when

<!-- Acceptance criteria — prose, NO `- [ ]` / `- [x]` checkboxes (RDO-15, convention a).
Per-task status lives only in the working list above; this list is verified at epic close.
`check_checkbox_consistency.py` flags any `- [ ]` / `- [x]` **ID** line placed here. -->

- **<ID-1>** — <one-line done criterion>
- **<ID-2>** — <one-line done criterion>

## After each task

Tick the box and append the completion tail:
`| Owner: <Claude|Antigravity|Animesh> | Model: <model-id|n/a> | SHA: <sha>`.
Then update this story's row in `docs/plan/README.md` (status + next marker) and add one
line to `TODOS.md` Session Log.
When the whole story is done, delete its `TODOS.md` priority-list line (move to
`docs/archive/TODOS_ARCHIVE.md`).
