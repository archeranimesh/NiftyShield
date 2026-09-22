# Plan-folder conversion — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the epic `README.md` status column, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## DFM-1 — enumerate and tier every non-archived plan folder

**Files to change / create:**
- this `stories.md` — replace the *Provisional tier table* below with the confirmed one, and expand each folder row into the specific work DFM-2 / DFM-3 / DFM-4 will do.

**Before any code:**
- `for d in docs/plan/*/; do ...` — list every folder, its `.md` files, its sub-dir count.
- `python scripts/dev/hooks/check_story_structure.py --all` — the current per-folder findings.
- `python -m scripts.dev.reflow_md --check docs/plan/<each>` — which folders need reflow.
- `git log --oneline --follow -- docs/plan/<folder>/` per folder — is it active, or has nothing touched it in months?
- `docs/plan/README.md` status lines + `TODOS.md` `## Feature Backlog` — which folders are live.

**What to implement:**

1. Build the definitive table: one row per non-archived `docs/plan/` folder → `{ folder, shape (flat/epic/legacy), current findings, tier, work needed }`.
2. Tier rules:
   - **A — full conversion.** Folder is in the `TODOS.md` Feature Backlog or marked `🔄` / `⬜` in `docs/plan/README.md`. Reconstruct every historical task line's `SHA` / `Owner` / `Model` /
     `Review` from git; `stories.md` gets a forward spec for open tasks and an as-built digest for shipped ones.
   - **B — structure + reflow.** Folder is shipped or nearly so, still referenced, but not actively worked. Repair the file set and task-line format; each shipped task gets a one-line digest
     and its real SHA — no deep git archaeology, no full forward specs.
   - **C — reflow only.** Structure already canonical (`root-doc-organization/`, `telegram-markdown-migration/` are done; others may qualify). Just `reflow_md.py`.
   - **D — archive, do not convert.** Folder is 100% shipped and should move to `docs/archive/plan/`. DFM-1 records this; a separate archival task is filed under the epic (or `TODOS.md`).
3. Put the tier split to Animesh before DFM-2 starts — the A/B line is a judgement call on effort vs. value.

**Tests:** none — docs-only.

**Commit:** `docs(plan): DFM-1 — tier every plan folder for conversion`

### Confirmed tier table (DFM-1, 2026-09-22)

Rebuilt against the live tree — `for d in docs/plan/*/`, `check_story_structure.py --all`, `reflow_md.py --check docs/plan`, `git log --oneline --follow` per folder, `docs/plan/README.md` §Active
Epics, `TODOS.md` §Feature Backlog. Several folders in the old provisional pass (`paper-store-position-granularity/`, `root-doc-organization/`, `signals/`, `telegram-ic-comparison-formatting/`,
`telegram-markdown-migration/`, `eod-pt-summary/`, `ic-yearly-expiry-fix/`) have since been archived to `docs/archive/plan/` and are out of scope — dropped from this table. `ic-payoff-charts/` and
`portfolio-snapshot-slimdown/` are new epics (2026-09-09, 2026-09-10) not seen in the earlier pass — added below. 19 folders remain in `docs/plan/` outside this epic and `_TEMPLATE/`.

| Folder | Shape now | Finding | Tier | Work needed | Status |
|---|---|---|---|---|---|
| `backtest-engine/` | epic, 4 phase subdirs OK | root missing `prompt.md`+`README.md` | A | add router; reflow 12 files. Backlog #7. | ✅ 150fab9 |
| `backtest-eval-core/` | flat, 4 files | none | A | reflow 4 files; verify tasks. Backlog #9 (blocked). | ✅ 7fcdba2 |
| `broker-abstraction/` | flat, `stories/BA-N.md` layout | missing `stories.md` | B\* | consolidate to `stories.md`; reflow 18 files. See note below. | ⬜ |
| `chain-decay-analysis/` | flat, 3 files | none | A | task-line format + reflow 3 files. Backlog #16. | ✅ 8b1c5df |
| `dev-foundation/` | epic, stray root `README.md`, 2/3 subs archived | root missing `prompt.md` | D | see note below — archive move, not a conversion. | ⬜ |
| `entry-event-filter/` | flat, 2 files | missing `stories.md` | A | add `stories.md`; reflow 2 files. Backlog #18. | ✅ b22052a |
| `full-repo-review/` | flat, 3 files | none | B | Complete, superseded — structure + reflow 13 files, digests. | ⬜ |
| `full-repo-review-followups/` | epic, 9 subs OK | root missing `prompt.md` | A | add router; reflow 28 files. Backlog #12/13/14. | ✅ 4dc1ed1 |
| `greeks-bs-fallback/` | flat, 3 files | none | A | task-line format + reflow 3 files. Backlog #2. | ✅ 0a2838a |
| `historical-data-abstraction/` | flat, `stories/HD-N.md` layout | missing `stories.md` | B\* | consolidate to `stories.md`; reflow 13 files. See note below. | ⬜ |
| `ic-payoff-charts/` | epic, 2 subs OK | none | A | already canonical — reflow 8 files; verify coverage. | ✅ 500c290 |
| `mvp/` | flat, `mvp_*.md` names | legacy filenames | A | `git mv` to canonical names; reflow 1 file. Backlog #4. | ✅ 8455d50 |
| `options_income/` | flat, `options_income_*.md` | legacy filenames | A | `git mv`; `_strategy.md`->`plan.md`; reflow 4 files. Backlog #6. | ✅ ddf0964 |
| `phase2-integrations/` | flat, 3 files | none | B\* | reflow 3 files; verify task-line format. See note below. | ⬜ |
| `portfolio-snapshot-slimdown/` | epic, 2 subs OK | none | A | already canonical + reflow-clean — verify coverage only. | ✅ no-op (already canonical) |
| `risk-gamma-phase-a/` | flat, 3 files | none | A | task-line format + reflow 3 files. Backlog #11. | ✅ 1f0a6cd |
| `signals-eval-core/` | flat, 4 files | none | A | reflow 4 files; verify tasks. Backlog #10 (blocked). | ✅ 6a9c87e |
| `technical-debt/` | flat, 3 files, 10 open/7 closed | none | A | opportunistic backlog, actively fed — reflow 3 files. | ✅ b1bf839 |
| `variance-gate/` | flat, `variance_gate_*.md` | legacy filenames | A | `git mv`; `_spec.md`->`spec.md`; reflow 4 files. Backlog #5. | ✅ 0b8d897 |

**No tier-D conversions needed** beyond `dev-foundation/`'s incomplete archive move — every other folder here is either active (A) or shipped-but-referenced (B); nothing else is 100% shipped and
un-archived.

**Confirmed with Animesh, 2026-09-22:** `broker-abstraction/`, `historical-data-abstraction/`, and `phase2-integrations/` are converted, not archived — tier B stands. They are fully-unstarted specs (0
tasks shipped) absent from both `docs/plan/README.md` §Active Epics and `TODOS.md` §Feature Backlog, so there is no shipped-task digest content; DFM-3 gives each a structure-repair pass (consolidate
`stories/*-N.md` → one `stories.md` for the two with that legacy layout, canonical task-line format, reflow) with no per-task digests to write.

---

## DFM-2 — convert every tier-A folder

**Per folder (one commit each):**

1. **Shape.** Flat story → ensure `prompt.md` + `tasks.md` + `stories.md` (+ `schema.md` iff DB). Epic → root `prompt.md` (router) + `README.md`, one sub-story folder per story. Copy missing files
   from `docs/plan/_TEMPLATE/`. Rename `<name>_tasks.md` → `tasks.md` etc. with `git mv` (history). A `<name>_strategy.md` / `<name>_spec.md` becomes `plan.md` / `spec.md` (an *Extra file* per
   §Conventions — no checkboxes).
2. **`prompt.md`.** Match `_TEMPLATE/story/prompt.md` (or `_TEMPLATE/epic/prompt.md`) headers. Fill *Why this story exists*, *Scope guard*, *Session-start load hints*, *Task overview*, *Definition of
   done*, *Perspectives not covered*.
3. **`tasks.md`.** Every task → one `- [ ]` / `- [x]` line with `| Owner: … | Model: … | Review: … | SHA: …`. Shipped tasks keep `[x]` + their real SHA (`git log --oneline --follow`); reconstruct
   `Owner` (Claude unless notes say otherwise), `Model` (`claude-sonnet-5` / `claude-opus-5` / `n/a`), `Review` (the gate token or `none`). Descriptions terse — one physical line ≤200.
4. **`stories.md`.** A section per task. Open tasks: full forward spec (files, before-any-code graph queries, what to implement, tests, commit message). Shipped tasks: 2–4 line as-built digest (what
   changed, key deviation, closing SHA) rebuilt from the `TODOS.md` Session Log + `git show`.
5. **Reflow.** `python -m scripts.dev.reflow_md docs/plan/<folder>` then `--check` and `git diff --word-diff` (reflow hunks: zero word changes).
6. **Verify.** `check_story_structure.py --all` and `check_checkbox_consistency.py` show no finding for this folder; `md-line-length` clean.
7. **Docs + commit.** Update `docs/plan/README.md` status line; `TODOS.md` Session Log; tick the folder's row in the DFM-1 progress table. `docs(plan): DFM-2 — convert <folder>/ to canonical format`.

Tick **DFM-2** only when the last tier-A folder is done.

**Commit (per folder):** `docs(plan): DFM-2 — convert <folder>/ to canonical format`

---

## DFM-3 — convert every tier-B folder

Same as DFM-2 steps 1–7 but **step 4 is light**: shipped tasks get a single-line digest (`### <ID> — <title> (SHA <sha>)` + one sentence), no forward specs, no `git show` deep-dive. The folder is not
being actively worked, so `stories.md` just needs to be structurally complete and cover every task id, not be a working spec.

Tick **DFM-3** only when the last tier-B folder is done.

**Commit (per folder):** `docs(plan): DFM-3 — restructure <folder>/ (shipped)`

---

## DFM-4 — reflow-only pass on tier-C folders

Structure is already canonical. For each tier-C folder: `python -m scripts.dev.reflow_md docs/plan/<folder>`, `--check`, `git diff --word-diff` (must be whitespace-only). May be one commit covering
all tier-C folders if every diff is purely whitespace; split if any folder needs a judgement call.

**Commit:** `docs(plan): DFM-4 — fill-to-≤200 the already-canonical plan folders`
