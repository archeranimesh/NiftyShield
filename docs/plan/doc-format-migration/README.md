# Doc format migration — epic index

> Bring every `docs/plan/` folder onto the canonical story/epic format and every other Markdown file in the repo onto the fill-to-≤200 line style, then harden the pre-commit and CI gates so new docs
> cannot drift back. One epic because the conversion pass and the enforcement changes are a single decision — enforcing before the tree is clean would break CI, and converting without enforcing
> afterwards just lets it rot again.

## Why this epic exists

RDO-17.1..17.7 (`docs/plan/root-doc-organization/`) defined the canonical format — flat-story vs epic folder shapes, the three-file story set, the `| Owner | Model | Review | SHA` task line, the
fill-to-≤200 prose style — and converted two POC folders (`root-doc-organization/`, `telegram-markdown-migration/`) to prove it works. RDO-17.8 was left open as "decide the rule for the remaining ~25
legacy folders". This epic is that decision, answered by Animesh on 2026-08-29: **batch-convert everything now**, tiered by how live each folder is, and make the format self-enforcing so the question
never has to be asked again.

Today the format is only advisory for legacy content. `check_story_structure.py` runs `--staged-added` (new folders only); `check_checkbox_consistency.py` is not wired to pre-commit at all;
`md-line-length` blocks but only on root `.md` + `docs/plan/**` + `docs/bugs/**` staged files; CI runs none of the three. A legacy folder can be edited indefinitely without ever conforming.

## Scope decisions

Confirmed with Animesh, 2026-08-29:

- **Structure conversion is `docs/plan/` only.** The canonical `prompt.md` / `tasks.md` / `stories.md` set and the five-field task line only make sense for story folders. `docs/bugs/` keeps its
  `**BNNN.x**` task workflow unchanged. Everything else under `docs/` and the root `.md` files get the fill-to-≤200 reflow only — they are not stories and have no canonical structure.
- **`docs/archive/**` is excluded from the reflow.** Archived folders and files are frozen historical records; reflowing them rewrites preserved history for no reading benefit. `_TEMPLATE/` is also
  excluded (its `<!-- -->` guidance lines are deliberately short).
- **Conversion depth is tiered by folder state.** An *active* folder (in the `TODOS.md` Feature Backlog, or `🔄` / `⬜` in `docs/plan/README.md`) gets a full conversion: every historical task line
  reconstructed from `git log` / `git show`, `stories.md` covering every task with a forward spec or an as-built digest. A *shipped-but-unarchived* or *archived-adjacent* folder gets structure repair
  (add the missing file, rename `*_tasks.md`, give an epic root its `prompt.md` + `README.md`) plus the reflow, and only a one-line digest per shipped task — no deep `git` archaeology. DFM-1 makes the
  per-folder call and records it.
- **Enforcement lands last.** DFM-6 and DFM-9 would fail CI the moment they merge if the tree were not already clean, so `enforcement/` runs only after `plan-folders/` and `repo-wide-reflow/` are both
  green against `--all`.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `plan-folders/` | Tiered batch conversion of every `docs/plan/` folder to the canonical format | ⬜ Not started | — | — |
| `repo-wide-reflow/` | Fill-to-≤200 every other `.md` in the repo (root + `docs/**` minus `plan/`, `archive/`, `_TEMPLATE/`) | ⬜ Not started | — | — |
| `enforcement/` | Widen the hooks repo-wide, add a CI `--all` gate, add new-folder scaffolding | ⬜ Not started | `plan-folders`, `repo-wide-reflow` | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`.

`plan-folders/` and `repo-wide-reflow/` are independent and may be worked in either order or interleaved; `enforcement/` needs both complete.

## Cross-cutting constraints

- **The reflow never changes words.** `scripts/dev/reflow_md.py` (shipped in RDO-17.7, SHA `526e431`) is the only tool used for the fill-to-≤200 pass. Every conversion commit must show `git diff
  --word-diff` with zero word insert/delete on reflow-only hunks — the only non-whitespace delta permitted is an interior `> ` blockquote-continuation marker consolidating when a multi-line quote
  rewraps. Structural edits (new headings, rewritten task lines) are reviewed as normal content changes.
- **One commit per folder** for `plan-folders/` DFM-2 / DFM-3 — never bundle two folders. Each sub-story's `stories.md` carries a per-folder progress table (folder · tier · closing SHA), prose rows,
  no `- [ ]` checkboxes.
- **Task-line descriptions must fit ≤200 chars on one physical line.** A task line is a list item; `reflow_md.py` will wrap an over-long one onto a hanging-indent continuation, which the checkbox hook
  then reads wrong. Write terse.
- **Shipped `[x]` task lines keep their real SHA.** When reconstructing a legacy folder, never invent or blank a SHA that git history has — `git log --oneline --follow` the folder.
- **Archived folders are not touched by this epic** beyond what DFM-1 explicitly lists. If DFM-1 finds a folder that should simply be archived rather than converted, it records that and the archival
  happens under `docs/plan/README.md` §Conventions *Completion → archive*, not here.

## Supersession / coordination

- **Supersedes RDO-17.8** (`docs/plan/root-doc-organization/`). On this epic's first commit, RDO-17.8's `tasks.md` line is marked `[x]` with a note "superseded by `doc-format-migration/`" and its
  `stories.md` spec points here. RDO-17.8's four open questions (cadence, effort ceiling, old-SHA risk, permanent grandfathering) are all answered by this epic's Scope decisions.
- **Coordinates with RDO-11** (`docs/plan/root-doc-organization/`) — RDO-11 graduates the *doc-freshness* hooks (`doc_update_gate.sh`, `state_doc_freshness.sh`) to blocking. Those are different
  scripts from the three this epic hardens (`check_md_line_length.py`, `check_story_structure.py`, `check_checkbox_consistency.py`); no file collision, but DFM-9 and RDO-11 both edit `ci.yml` —
  whichever lands second rebases onto the other's job block.
- **Absorbs the `md-organize` skill's periodic `--all` audit.** That skill runs the three sweeps advisorily today; DFM-9 makes them a hard CI gate. After DFM-9, `md-organize`'s audit step becomes a
  local pre-check, not the enforcement point — update its `SKILL.md` accordingly in DFM-9.

## Epic done when

- **`plan-folders`** — `check_story_structure.py --all` and `check_checkbox_consistency.py --all` report zero findings across `docs/plan/`; every non-archived folder has the canonical file set and
  canonical task lines; `reflow_md.py --check docs/plan/` is clean.
- **`repo-wide-reflow`** — `reflow_md.py --check` is clean on every `.md` in the repo except `docs/archive/**` and `docs/plan/_TEMPLATE/`; each commit's reflow hunks are word-diff clean.
- **`enforcement`** — the three doc hooks run repo-wide (`--all`) in a CI job that fails on any finding; `check_checkbox_consistency` is in `.pre-commit-config.yaml`; `check_story_structure` gates
  modified (not only newly-added) folders; `scripts/dev/new_plan_folder.py` + the `/new-story` skill scaffold a conforming folder from `_TEMPLATE/`; `docs/plan/README.md` §Conventions documents that
  the format is now enforced, not advisory.
