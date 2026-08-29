# Format enforcement — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation spec.

**Blocked until `plan-folders/` and `repo-wide-reflow/` are both complete.**

**Open: DFM-6, DFM-7, DFM-8, DFM-9, DFM-10.**

- [ ] **DFM-6** — widen `md-line-length` `files:` to every repo `.md` bar `docs/archive/` + `_TEMPLATE/`; tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **DFM-7** — `check_story_structure.py`: `--staged` mode + shrinking legacy allowlist; rewire pre-commit | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **DFM-8** — wire `check_checkbox_consistency.py` into `.pre-commit-config.yaml`; confirm green tree-wide | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **DFM-9** — `ci.yml` `docs-format` job: three hooks `--all`, fail on any finding; update `md-organize` skill | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **DFM-10** — `scripts/dev/new_plan_folder.py` + tests + `/new-story` skill; link from README §Conventions | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>

## Story done when

Acceptance criteria — prose, no checkboxes. Verified at story close.

- **DFM-6** — `md-line-length` fires on any `.md` outside `docs/archive/` / `_TEMPLATE/`; `check_md_line_length.py` unit tests cover the widened scope; `pre-commit run --all-files md-line-length` is
  green.
- **DFM-7** — editing a legacy-shaped folder not on the allowlist fails pre-commit; the allowlist is empty (or documented residual); `check_story_structure.py` tests cover `--staged` add + modify.
- **DFM-8** — `.pre-commit-config.yaml` has a `check-checkbox-consistency` hook; `pre-commit run --all-files` is green across the converted tree.
- **DFM-9** — a PR that introduces a format finding fails the `docs-format` CI job; `md-organize` SKILL.md describes its audit as a local pre-check.
- **DFM-10** — `python -m scripts.dev.new_plan_folder --story foo` produces a folder that passes `check_story_structure.py --all` with no edits; `/new-story` invokes it; tests green.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update the epic `README.md` story-list status column and add one line to `TODOS.md` Session Log. When the whole epic is done,
follow `docs/plan/README.md` §Conventions *Completion → archive* — the epic folder moves to `docs/archive/plan/doc-format-migration/`, the `TODOS.md` backlog line moves to `TODOS_ARCHIVE.md`, and the
`docs/plan/README.md` row becomes a pointer.
