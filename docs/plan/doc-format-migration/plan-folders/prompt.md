# Plan-folder conversion — prompt

> Convert every non-archived `docs/plan/` folder to the canonical story/epic format, tiered by how live the folder is.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The canonical format (`docs/plan/README.md` §Conventions) is fully specified and proven on two POC folders, but ~22 other folders still carry legacy shapes — `<name>_tasks.md` filenames, epic roots
with no `prompt.md` / `README.md`, story folders with no `stories.md`, multi-line task entries with no `| Owner | Model | Review | SHA` tail. `/work` cannot route cleanly through them and
`check_story_structure.py --all` reports a warning per folder. This story clears all of it in one sustained pass so the format becomes universal, not aspirational.

## Scope guard

**In bounds:** every folder directly under `docs/plan/` except `_TEMPLATE/` and anything already archived to `docs/archive/plan/`. Structural edits (file set, task-line format, `stories.md` coverage)
plus the `reflow_md.py` fill-to-≤200 pass on each folder's `.md`.

**Out of bounds:** `docs/bugs/` (different workflow, keeps `**BNNN.x**`), any `.md` outside `docs/plan/` (that is `repo-wide-reflow/`), the hook scripts and CI (that is `enforcement/`), and the
*content* of any spec — this story changes structure and line wrapping, never what a task is asking for. Docs-only, no `src/` behaviour change.

If a folder turns out to be fully shipped and should be archived rather than converted, DFM-1 records that; the archival itself follows `docs/plan/README.md` §Conventions *Completion → archive* as
separate work, not here.

## Session-start load hints

- `docs/plan/README.md` §Conventions — the canonical format is defined there and nowhere else. Re-read *Folder shapes*, *Story-folder file set*, *Epic-folder file set*, *Task-line format*, *Checkbox
  consistency*, *Markdown line style*.
- `docs/plan/_TEMPLATE/story/` and `docs/plan/_TEMPLATE/epic/` — the exact headers to match.
- `docs/plan/root-doc-organization/stories.md` RDO-17.5 and RDO-17.6 as-built digests — the two worked examples of a flat-story and an epic conversion.
- For any folder being converted: `git log --oneline --follow -- docs/plan/<folder>/` to reconstruct shipped task SHAs and dates.

## Task overview

- **DFM-1** — enumerate every non-archived `docs/plan/` folder, classify each into tier A (full conversion) / tier B (structure + reflow only) / tier C (already conforming — reflow only) / tier D
  (should be archived, not converted); record the table in this file's `stories.md`. Docs-only, one commit.
- **DFM-2** — convert every tier-A folder: full structural conversion + `stories.md` covering every task + reflow. One commit per folder; tick DFM-2 when the last tier-A folder lands.
- **DFM-3** — convert every tier-B folder: structure repair + one-line digest per shipped task + reflow. One commit per folder; tick DFM-3 when the last tier-B folder lands.
- **DFM-4** — reflow-only pass on every tier-C folder (structure already canonical). May be a single commit if the diffs are purely whitespace.

## Definition of done

`check_story_structure.py --all` and `check_checkbox_consistency.py --all` report zero findings across `docs/plan/`; every non-archived folder has the canonical file set and canonical task lines;
`reflow_md.py --check docs/plan/` (excluding `_TEMPLATE/`) is clean; every tier-D folder is either converted or has an archival task filed.

## Perspectives not covered

Whether some legacy specs are stale enough that conversion effort is wasted — this story assumes every non-archived folder is worth keeping and converts it as-is. A content review of each spec (is
this task still real? is the DoD still right?) is explicitly *not* part of this story; DFM-1 may flag a folder as "convert, but content looks stale" for a later pass.
