# Root doc organization — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, update the story status
> summary in `docs/plan/README.md`, add one line to `TODOS.md`. See `docs/plan/README.md`
> §Conventions.

This story is ~90% shipped. Specs for the shipped tasks (RDO-1..RDO-15, RDO-17.1..17.4) are
still **inline in `tasks.md`** — each closed line carries its own design notes, deviations,
and closing SHA, and `TODOS.md` Session Log has the forensic detail. This file currently
specs the open work: **RDO-11**, **RDO-16**, **RDO-17.5**, **RDO-17.6**, **RDO-17.7** (plus
the as-built note for the shipped **RDO-17.4**). RDO-17.5 rewrites this file to cover *every*
task — forward spec for the open ones, a short as-built digest for each shipped one.

This is a docs + tooling story throughout — no `.py` under `src/`. `Review: none` on every
open line except where a hook script under `scripts/` is edited (RDO-17.2 was the only such
task and is shipped).

---

## RDO-11 — graduate the advisory doc-freshness hooks to enforcing

**Gate:** do not start before **2026-09-03** — the observation window opened 2026-08-27 and
needs ~1 week of real firings to judge the false-positive rate.

**Files to change:**
- `.claude/hooks/doc_update_gate.sh` — the `exit 0` → `exit 2` flip, iff the false-positive
  rate is tolerable.
- `.claude/hooks/state_doc_freshness.sh` — apply RDO-10 #5's threshold tuning if not already
  landed (`CONTEXT_TREE.md` / `DB_REGISTRY.md` / `README.md` → 60); verify signal-not-noise
  across 3–4 real sessions.
- `CLAUDE.md` §Step 5c + `AGENTS.md` §Step 5c — document the `[skip-docs]` commit-message
  escape hatch, iff `doc_update_gate.sh` becomes blocking.
- `DECISIONS.md` — one STILL-ENFORCED RULE entry recording the final hook contract
  (blocking / advisory, the tuned thresholds), so the contract is documented not only coded.

**Before any code:**
- `git log --oneline --since=2026-08-27 -- src/ scripts/` — the commits the gate saw.
- `git log --all --grep='\[skip-docs\]' --oneline` — how often the escape hatch was used.
- Read both hook scripts as text (tooling, not graph-indexed).

**What to implement:**

1. Review ~1 week of `doc_update_gate.sh` firings — count the false positives (pure
   refactors, mid-phase multi-commit work where the doc update lands in a later commit).
2. If the false-positive rate is tolerable: flip `exit 0` → `exit 2`, document `[skip-docs]`
   in both `CLAUDE.md` / `AGENTS.md` §Step 5c. If not: tighten the staged-file match, or keep
   it advisory and re-review after another week.
3. Confirm `state_doc_freshness.sh` thresholds are the RDO-10 #5 values and the flag is
   signal not noise.
4. Record the outcome as a STILL-ENFORCED RULE entry in `DECISIONS.md`.

**Tests:** the hook scripts have unit coverage under `tests/unit/scripts/` — extend it if the
match logic changes. No new domain tests.

**Commit:** `chore(hooks): graduate doc-freshness gate to <blocking|tuned-advisory>`

---

## RDO-16 — doc-freshness loop-closure check

The end-to-end test of "the docs preserve their state" — not any individual hook. Runs
**after RDO-6** (`md-organize`) is shipped, which it now is.

**Files to change:** none by default — this is a verification task. It produces a one-line
`TODOS.md` Session Log entry recording the result, and ticks its own box.

**What to verify — one real session, start to finish:**

1. A state doc goes stale under code churn (`src/` / `scripts/` commits accumulate past its
   threshold in `state_doc_freshness.sh`).
2. `state_doc_freshness.sh` flags it at SessionStart.
3. The flag is acted on — either `CLAUDE.md` Step 5a in that session, or a full `md-organize`
   run.
4. The flag clears at the next SessionStart.

If any link breaks (flag never fires, threshold wrong, `md-organize` doesn't touch the
flagged doc, flag persists after the fix), file the gap as a new RDO task and leave RDO-16
open.

**Commit:** `docs(plan): close RDO-16 — doc-freshness loop verified end to end`

---

## RDO-17.4 — retrofit the two RDO-17 validation folders

RDO-17 (`~/.claude/plans/woolly-honking-tarjan.md`) standardized the `docs/plan/` story/epic
format. 17.1–17.3 shipped the spec, hooks, and `/work` epic-descent.

**As-built (35d9f42 + close 8e7273c) — partial retrofit, since superseded.** 17.4 brought
`root-doc-organization/` (added this `stories.md` for open tasks only; `| Review:` tail on
open lines; `## Epic done when` → `## Story done when`) and `telegram-markdown-migration/`
(dropped `.DS_Store`; archived the exhausted missing-messages queue `TODO.md` +
`missing-message-workshop-prompt.md` → `docs/archive/plan/`; `README.md` repointed) into
*structural* conformance, grandfathering the shipped task lines. Both hooks `--all` went
14 → 12 warnings. **Superseded 2026-08-29** by RDO-17.5 / 17.6, which fully convert both
folders (see below).

---

## RDO-17.5 — full-convert `root-doc-organization/` to the canonical format

The POC conversion of the harder of the two validation folders. If this converts cleanly and
bounded, the same recipe scales to the other ~25 legacy flat-story folders (RDO-17.7).

**Files to change:**
- `tasks.md` — rewrite every task line (RDO-1..RDO-17.7) to a single canonical line:
  `- [x] **RDO-N** — <one-line description> | Owner: … | Model: … | Review: … | SHA: <real>`.
  Shipped lines keep their real closing SHA and `[x]`; `Owner` / `Model` / `Review` are
  reconstructed — `Owner: Claude` / `Model: claude-sonnet-5` for all (no Antigravity or
  Animesh implementation in this story's history), `Review: code-reviewer` for the tasks
  whose diff touched a `.py` file under `scripts/` (RDO-5, RDO-13, RDO-15, RDO-17.2),
  `Review: none` for the rest. Keep the `## Story done when` prose block and `## After each
  task`. Collapse the multi-paragraph intro to a short pointer. Target ~505 → ~95 lines.
- `stories.md` — replace the current open-tasks-only content with all-task coverage: a full
  forward spec (Files / Before any code / Implement / Tests / Commit) for the open tasks
  (RDO-11, RDO-16), and a 2–4 line **as-built digest** (what changed · key deviation · SHA)
  for every shipped task, reconstructed from the current inline `tasks.md` notes +
  `TODOS.md` Session Log + `git show`. Target ~280 lines.
- `prompt.md` — realign to `_TEMPLATE/story/prompt.md`: keep "Why this story exists",
  add "Session-start load hints", "Task overview" (one line per RDO id), "Definition of
  done" (mirror `## Story done when`), "Perspectives not covered". Point at `stories.md`,
  not `plan.md`.
- `plan.md` — keep unchanged (D6 extra file — file-by-file historical detail, no checkboxes).

**Before any code:**
- `git log --oneline --all --grep='RDO-' ` and `git show <sha>` per shipped task — confirm
  each SHA and whether its diff touched `scripts/*.py` (sets `Review`).
- Re-read the current `tasks.md` inline notes — the as-built digests are a compression of
  these, not a re-derivation.

**No behaviour change — docs only. `Review: none` for RDO-17.5 itself.**

**Verify:** both hooks `--all` exit 0 with no `root-doc-organization/` finding;
`check_checkbox_consistency.py` clean on the rewritten `tasks.md` (every ticked line a real
7–40 hex SHA, every open line `<—>`); 42 hook tests green; fresh `Read tasks.md` +
`Read stories.md` both well under the display cap.

**Commit:** `docs(plan): RDO-17.5 — convert root-doc-organization/ to canonical format`

---

## RDO-17.6 — full-convert `telegram-markdown-migration/` to the canonical epic format

**Files to change:**
- `prompt.md` (epic root) — replace the hand-built router with the `_TEMPLATE/epic/prompt.md`
  body: Step 1 (fixed story order = README Stories-table row order:
  `backbone/` → `formatting-rules/` → `strategy-rollout/`), Step 2 (owner check), Step 3
  (load sub-story context), Step 4 (implement / verify / record).
- `README.md` (epic root) — add the ordered **Stories** table with a status column
  (⬜ / 🔄 / ✅ + closing SHA) and per-story dependency; keep the scope-decision narrative,
  supersession notes, and the improvement backlog. `backbone/` ✅, `formatting-rules/` ✅,
  `strategy-rollout/` 🔄.
- `backbone/tasks.md`, `formatting-rules/tasks.md`, `strategy-rollout/tasks.md` — every line
  to canonical form: inline `(SHA: …)` / `(62d0172)` / `(Commit: …)` → the `| … | SHA: …`
  tail; `| Blocked by:` folded into the description; `Owner` / `Model` / `Review`
  reconstructed (MD-*/FMT-*/ROLL-* that touched `src/` or `scripts/` `.py` →
  `Review: code-reviewer`, docs-close tasks → `none`). Multi-line descriptions collapsed;
  the as-built prose moves to the sub-story `stories.md` as a digest where it is not already
  there.
- **`ROLL-1a/1b/1c`, `ROLL-2a..c`, `ROLL-3.1..3`, etc. nested sub-checkboxes** — resolve
  against one-checkbox-per-id: promote each to a top-level `ROLL-*` line (renumber or keep
  the dotted id), or drop the parent's checkbox and keep only the leaves. Decide once, record
  in the epic `README.md`, apply to all three sub-stories.
- `backbone/prompt.md`, `formatting-rules/prompt.md`, `strategy-rollout/prompt.md` — realign
  to `_TEMPLATE/story/prompt.md`.
- The three `stories.md` files stay (already spec-shaped) — touch only to receive as-built
  digests displaced from `tasks.md`.

**Before any code:** `git log` each MD-*/FMT-*/ROLL-* SHA; read all three current `tasks.md`
in full (the sub-checkbox structure and the `| Blocked by:` graph must survive the rewrite).

**No behaviour change — docs only. `Review: none` for RDO-17.6 itself.**

**Verify:** both hooks `--all` exit 0 with no `telegram-markdown-migration/*` finding;
`/work` dry-run on the epic still walks `backbone/` → `formatting-rules/` → `strategy-rollout/`
and lands on the first open `ROLL-*`; 42 hook tests green.

**Commit:** `docs(plan): RDO-17.6 — convert telegram-markdown-migration/ to canonical format`

---

## RDO-17.7 — TBD (Animesh to define)

Placeholder. Animesh defines the scope once RDO-17.5 / RDO-17.6 land — expected to be the
rule / recipe for converting the remaining ~25 legacy `docs/plan/` folders, informed by how
cleanly the two POC conversions went (effort per folder, reconstruction risk for old SHAs,
whether it is worth doing at all vs. leaving them grandfathered until next touch).

**Owner: Animesh. No spec until 17.5/17.6 are done.**
