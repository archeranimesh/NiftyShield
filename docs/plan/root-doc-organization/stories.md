# Root doc organization — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, update the story status
> summary in `docs/plan/README.md`, add one line to `TODOS.md`. See `docs/plan/README.md`
> §Conventions.

This story is ~90% shipped. Specs for the shipped tasks (RDO-1..RDO-15, RDO-17.1..17.3) are
**inline in `tasks.md`** — each closed line carries its own design notes, deviations, and
closing SHA, and `TODOS.md` Session Log has the forensic detail. This file specs only the
still-open work: **RDO-11**, **RDO-16**, and the RDO-17 retrofit sub-task **RDO-17.4**.

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
format. 17.1–17.3 shipped the spec, hooks, and `/work` epic-descent. 17.4 retrofits the two
worked-example folders; the other ~25 legacy folders are grandfathered and convert on their
next substantive touch.

**`root-doc-organization/` — single flat story:**
- Add this `stories.md` (covers open tasks only; shipped-task detail stays inline in
  `tasks.md`).
- Add the full `| Owner | Model | Review | SHA` tail to the open lines (RDO-11, RDO-16);
  leave the 14 shipped lines' legacy tails as historical record (grandfathered by
  `check_checkbox_consistency.py`).
- Rename `## Epic done when` → `## Story done when` (single-story folder).
- `plan.md` stays — allowed under §Extra files (shared reference, no checkboxes).

**`telegram-markdown-migration/` — epic:**
- `rm` the untracked `.DS_Store`.
- `git mv TODO.md` + `git mv missing-message-workshop-prompt.md` →
  `docs/archive/plan/telegram-markdown-migration/`. The missing-messages queue (items 1–10)
  is exhausted — every format was confirmed and written back as `strategy-rollout/`
  `ROLL-7..ROLL-16`. The two `| SHA: —` lines (items 5, 7b) map to shipped `ROLL-11` /
  `ROLL-14` specs plus committed scratch scripts, so the queue is genuinely done.
- `README.md` — repoint the `TODO.md` reference to the archived path + one line noting the
  queue completed and archived.
- Keep `message-format-workshop.md` at the epic root (§Extra files — shared, checkbox-free;
  `README.md` documents it).
- No sub-story restructure; historical `TODO.md` mentions inside sub-story `stories.md` /
  `tasks.md` are accurate records, left as-is.

**Verify:** `python scripts/dev/hooks/check_story_structure.py --all` and
`python scripts/dev/hooks/check_checkbox_consistency.py --all` both exit 0 with the two
validation-folder findings (`root-doc-organization/: missing stories.md`,
`telegram-markdown-migration/TODO.md: extra .md carries task checkboxes`) gone.
`python -m pytest tests/unit/scripts/dev/hooks/ --tb=no -q` green.

**Commit:** `docs(plan): RDO-17.4 — retrofit the two format-validation folders`
