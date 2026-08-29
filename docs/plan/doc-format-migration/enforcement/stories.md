# Format enforcement — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the epic `README.md` status column, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

**Every task here touches a hook script or CI — `Review: code-reviewer` is mandatory before commit, run against `git diff HEAD`.** Every changed hook line needs a unit test (happy + edge).

---

## DFM-6 — widen the md-line-length hook repo-wide

**Files to change:**
- `.pre-commit-config.yaml` — the `md-line-length` hook `files:` regex.
- `scripts/dev/hooks/check_md_line_length.py` — only if it needs an exclude for `docs/archive/` / `_TEMPLATE/` when invoked in `--all` style (today it takes explicit paths from pre-commit).
- `tests/unit/scripts/dev/hooks/test_check_md_line_length.py` — cover the new scope.

**Before any code:**
- `git show HEAD:.pre-commit-config.yaml` — current `files:` is `^([^/]+\.md|docs/(plan|bugs)/.*\.md)$`.
- Decide: widen to `^(?!docs/archive/|docs/plan/_TEMPLATE/).*\.md$` (all `.md`, two excludes) — pre-commit `files:` is a regex over the staged path.

**What to implement:**

1. Change `files:` to match every `.md` except `docs/archive/**` and `docs/plan/_TEMPLATE/**`.
2. If a repo `.md` legitimately needs a long line (base64, URL), add `<!-- lint-ignore-length -->` on the preceding line as part of this task — `pre-commit run --all-files md-line-length` must be
   green before commit.
3. Tests: a path under `docs/archive/` is skipped; a path under `.claude/` is checked; the existing cap + ignore-marker tests still pass.

**Commit:** `chore(hooks): DFM-6 — md-line-length covers the whole tree`

---

## DFM-7 — gate modified folders, not just newly-added

**Files to change:**
- `scripts/dev/hooks/check_story_structure.py` — add a `--staged` mode: the union of added and modified folders under `docs/plan/`. Keep `--staged-added` working (or alias it). Add a
  `_LEGACY_ALLOWLIST` constant (folder slugs still permitted to be non-canonical); in `--staged` mode a folder on the allowlist warns, off the allowlist errors.
- `.pre-commit-config.yaml` — `entry:` `--staged-added` → `--staged`.
- `tests/unit/scripts/dev/hooks/test_check_story_structure.py` — `--staged` picks up a modified (not added) folder; allowlisted folder warns, non-allowlisted errors.

**Before any code:**
- `get_code_snippet("main")` won't disambiguate — read `scripts/dev/hooks/check_story_structure.py` `main()` directly (shell/`sed`); note how it derives folders for `--staged-added` and the `# --all
  grandfathers legacy shapes` block.
- Confirm with `plan-folders/` status: if every folder converted, `_LEGACY_ALLOWLIST = []` from the start.

**What to implement:**

1. `--staged`: collect `git diff --cached --name-only` → parent `docs/plan/<folder>` set → check each.
2. Allowlist gate: `folder in _LEGACY_ALLOWLIST` → findings are warnings (exit 0); else warnings for a canonical-but-imperfect folder stay warnings, but a *missing required file* or a *legacy
   filename* is an error (exit 1). Keep `--all` behaviour unchanged (grandfather everything, warn-only).
3. Tests as above.

**Commit:** `chore(hooks): DFM-7 — check_story_structure gates modified folders`

---

## DFM-8 — wire check_checkbox_consistency into pre-commit

**Files to change:**
- `.pre-commit-config.yaml` — new `local` hook `check-checkbox-consistency`, `language: system`, `entry: python scripts/dev/hooks/check_checkbox_consistency.py`, `files: '^docs/(plan|bugs)/.*\.md$'`,
  `pass_filenames: true` (or `false` + `--staged` if the script wants that — read its `main()` first).
- `tests/unit/scripts/dev/hooks/test_check_checkbox_consistency.py` — add a pre-commit-shape invocation test if not already covered.

**Before any code:**
- Read `scripts/dev/hooks/check_checkbox_consistency.py` `main()` — does it take paths, `--all`, or `--staged`? Match the pre-commit wiring to what it supports; add a `--staged` mode if needed (same
  shape as DFM-7's).
- `python scripts/dev/hooks/check_checkbox_consistency.py --all` — must already be green tree-wide (it will be, post `plan-folders/`). If not, that is a `plan-folders/` gap — file it, do not paper
  over it here.

**What to implement:**

1. Add the hook. 2. Verify `pre-commit run --all-files check-checkbox-consistency` is green. 3. Test.

**Commit:** `chore(hooks): DFM-8 — checkbox-consistency runs pre-commit`

---

## DFM-9 — CI --all gate

**Files to change:**
- `.github/workflows/ci.yml` — new job `docs-format` (parallel to `test`): checkout, setup-python, then `python scripts/dev/hooks/check_md_line_length.py $(git ls-files ':(glob)**/*.md' | grep -vE
  '^(docs/archive/|docs/plan/_TEMPLATE/)')`, `python scripts/dev/hooks/check_story_structure.py --all` **with warnings promoted to failures** (add a `--strict` flag, or grep the output for `WARN` and
  exit 1), `python scripts/dev/hooks/check_checkbox_consistency.py --all`.
- `scripts/dev/hooks/check_story_structure.py` — a `--strict` flag that makes `--all` warnings fail (needed because `--all` currently grandfathers). Tests.
- `.claude/skills/md-organize/SKILL.md` — the audit step now says "local pre-check; CI `docs-format` is the gate".

**Before any code:**
- `git show HEAD:.github/workflows/ci.yml` — the `test` job shape, the `pip install -e ".[dev]"` line to reuse.
- Check whether RDO-11 has landed a `ci.yml` change (`git log --oneline -- .github/workflows/ci.yml`) — if so, rebase the new job onto it.

**What to implement:**

1. `--strict` on `check_story_structure.py` (and `check_checkbox_consistency.py` if it also warn-grandfathers). 2. The `docs-format` job. 3. Confirm the job passes on the current (post-conversion)
   tree by running the exact commands locally. 4. `md-organize` SKILL.md edit.

**Commit:** `ci: DFM-9 — docs-format job gates the canonical format`

---

## DFM-10 — new-folder scaffolding

**Files to change / create:**
- `scripts/dev/new_plan_folder.py` — `--story <slug>` or `--epic <slug>` (+ optional `--title`, `--into <epic-slug>` for a sub-story). Copies `docs/plan/_TEMPLATE/story/` or `/epic/` to
  `docs/plan/<slug>/` (or `docs/plan/<epic>/<slug>/`), strips the `<!-- ... -->` guidance blocks, substitutes `<Story title>` / `<slug>` / `<ID>` placeholders. Refuses if the target exists.
  `_SCRIPT_NAME = "scripts.dev.new_plan_folder"` per `LOGGING.md`.
- `tests/unit/scripts/dev/test_new_plan_folder.py` — story scaffold passes `check_story_structure.py --all`; epic scaffold passes; existing-target refusal; slug validation (kebab-case, no date
  prefix).
- `.claude/skills/new-story/SKILL.md` — thin wrapper: ask story-vs-epic + slug + title, run the script, print the created paths and the "now fill in prompt.md" checklist.
- `docs/plan/README.md` §Conventions *Folder shapes* — replace "Start it by copying `docs/plan/_TEMPLATE/story/`" with "Run `/new-story` (or `python -m scripts.dev.new_plan_folder --story <slug>`)".

**Before any code:**
- Read `docs/plan/_TEMPLATE/story/*` and `epic/*` — the exact placeholder tokens to substitute and comment blocks to strip.
- `search_graph("check_story_structure")` / read its `main()` — what "conforming" means so the scaffold output passes it clean.

**What to implement:**

1. The CLI. 2. Placeholder substitution + comment stripping. 3. The skill. 4. The README edit. 5. Tests — the key assertion is *scaffold output passes `check_story_structure.py --all` with zero
   edits*.

**Commit:** `feat(scripts): DFM-10 — new_plan_folder scaffolds from the template`
