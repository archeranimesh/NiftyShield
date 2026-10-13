<!-- Copy the whole `story/` folder to docs/plan/<slug>/ (single story) or
docs/plan/<epic-slug>/<story-slug>/ (epic sub-story). Delete these HTML comments once
filled in. See docs/plan/README.md §Conventions. -->

# <Story title> — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task.
Each task = one commit unless noted. See `prompt.md` for why the story exists;
see `stories.md` for the per-task implementation spec.

**Open: <task ids>.**

<!-- Task-line format (§Conventions "Task-line format"): one `- [ ]` per task, five
`|`-separated fields. Owner/Model/Review are filled now, at authoring time; SHA stays `—`
until the task's commit lands, then set the real SHA and tick the box.
  Owner:  Claude | Antigravity | Animesh
  Model:  claude-sonnet-5 | claude-opus-5 | … | n/a   (n/a when Owner != Claude)
  Review: code-reviewer | greeks-analyst | roll-validator | none   (none for docs-only) -->

- [ ] **<ID-1>** — <what this task does> | Owner: <Claude|Antigravity|Animesh> | Model: <model-id|n/a> | Review: <code-reviewer|none> | SHA: <—>
- [ ] **<ID-2>** — <what this task does> | Owner: <Claude|Antigravity|Animesh> | Model: <model-id|n/a> | Review: <code-reviewer|none> | SHA: <—>

## Story done when

<!-- Acceptance criteria — prose, NO `- [ ]` / `- [x]` checkboxes (§Conventions "Checkbox
consistency"). Per-task status lives only in the working list above; this list is verified
at story close. `check_checkbox_consistency.py` flags any `- [ ]` / `- [x]` **ID** line
placed here. For an epic sub-story, name this block `## Story done when`; the epic's own
`README.md` status column rolls these up. -->

- **<ID-1>** — <one-line done criterion>
- **<ID-2>** — <one-line done criterion>

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box.
Then update this story's status wherever it is summarised (`docs/plan/README.md` for a
single story, the epic `README.md` story list for an epic sub-story) and add one line to
`TODOS.md` Session Log.
When the whole story is done, follow §Conventions *Completion → archive* — do not leave a
done story half-archived.
