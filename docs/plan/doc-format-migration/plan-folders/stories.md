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

### Provisional tier table (DFM-1 confirms / corrects this)

First pass from `docs/plan/README.md` status + folder shape. **Not authoritative** — DFM-1 rebuilds it.

| Folder | Shape now | Findings | Prov. tier | Work |
|---|---|---|---|---|
| `backtest-engine/` | epic, 4 subdirs, no `prompt.md`/`README.md` | epic root incomplete | A | add router + README; convert 4 phase sub-stories |
| `backtest-eval-core/` | flat, 4 files (+schema) | ok? | A/C | reflow; verify task lines |
| `broker-abstraction/` | flat, no `stories.md`, 1 subdir | missing `stories.md` | A | add `stories.md`; resolve the stray subdir |
| `chain-decay-analysis/` | flat, 3 files | — | A | task-line format + reflow |
| `dev-foundation/` | epic-ish, 1 subdir, only `README.md` | epic root incomplete; README says ✅ Shipped/Archived | D | archive to `docs/archive/plan/` |
| `entry-event-filter/` | flat, no `stories.md` | missing `stories.md` | A | add `stories.md` |
| `eod-pt-summary/` | flat, 3 files | ⬜ not started | A | task-line format + reflow |
| `full-repo-review/` | flat, 3 files | ✅ Complete | B | structure + reflow, digests |
| `full-repo-review-followups/` | epic, 9 subdirs, only `README.md` | epic root incomplete | A | add router; convert 9 finding sub-stories |
| `greeks-bs-fallback/` | flat, 3 files | 🔄 partially scoped | A | task-line format + reflow |
| `historical-data-abstraction/` | flat, no `stories.md`, 1 subdir | missing `stories.md` | A | add `stories.md`; resolve subdir |
| `ic-yearly-expiry-fix/` | flat, 3 files | 🔄 partially superseded | A | task-line format + reflow |
| `mvp/` | flat, `mvp_*.md` names | legacy filenames | A | rename to `tasks.md`/`stories.md`/`schema.md` + reflow |
| `options_income/` | flat, `options_income_*.md` | legacy filenames | A | rename (+ `options_income_strategy.md` → `plan.md` extra file) + reflow |
| `paper-store-position-granularity/` | flat, 3 files | — | A/C | reflow; verify |
| `phase2-integrations/` | flat, 3 files | — | A/C | reflow; verify |
| `risk-gamma-phase-a/` | flat, 3 files | 🔄 in progress; README calls it "the model" | C | reflow only, verify |
| `root-doc-organization/` | flat, 4 files | converted RDO-17.5 | C | done — skip |
| `signals/` | flat, `signals_*.md` names | legacy filenames | A | rename + reflow |
| `signals-eval-core/` | flat, 4 files (+schema) | — | A/C | reflow; verify |
| `technical-debt/` | flat, 3 files | — | A/C | reflow; verify |
| `telegram-ic-comparison-formatting/` | flat, 3 files | 🔄 TGFMT-1 shipped, rest superseded | B | structure + reflow, digests |
| `telegram-markdown-migration/` | epic, 3 subdirs | converted RDO-17.6 | C | done — skip |
| `variance-gate/` | flat, `variance_gate_*.md` | legacy filenames | A | rename (+ `variance_gate_spec.md` → `spec.md`) + reflow |

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
