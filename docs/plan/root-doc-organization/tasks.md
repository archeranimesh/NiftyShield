# Root doc organization — tasks

Work top-down. Each phase = one commit. See `plan.md` for the file-by-file detail.
RDO-1 and RDO-2 are done. RDO-3 is closed as a partial (remainder → RDO-9); it is not a
blocker. RDO-4, 5, 7, 8, 11 are independent. RDO-6 comes last (encodes final state). RDO-8
was spun out of the RDO-2 audit and feeds RDO-5/RDO-6. RDO-5 expanded 2026-08-27 — covers
`docs/plan/**` + `docs/bugs/**` and defines the semantic-linefeed prose style. RDO-9
replaces RDO-3's unworkable date cutoff. RDO-10 reconciles RDO-7 with the freshness hooks a parallel epic shipped the
same day; RDO-11 decides whether those hooks become blocking. RDO-12 spins the unified
`/work` session entry point into its own story (`docs/plan/session-entry-point/`). RDO-13
makes `docs/plan/README.md` §Conventions enforceable (template + audit) and cuts `TODOS.md`
back to pointer-only items. RDO-14 restructures `TODOS.md`'s priority list into one
priority-ordered bug+feature queue — the list `/work` reads to build its menu.

**Open: RDO-6, 7, 9, 10, 11, 14, 15.** Epic completion criteria at the bottom of this file.

- [x] **RDO-1** — Slim `CONTEXT.md` to ≤400 lines, no line >200 chars; move module prose to
  `CONTEXT_TREE.md`. Verify: fresh `Read CONTEXT.md` returns whole file, no display-cap hit.
  Done 2026-08-27: 159 lines, max 199 chars, ~2.6K tokens (was ~20K). Full-file `Read` clean.
  Old prose archived verbatim → `docs/archive/CONTEXT_WHAT_EXISTS_2026-08.md`; `CONTEXT_TREE.md`
  enriched with the missing structural facts (`overlay_coverage.py`, `notifications/formatting.py`,
  Developer + Research tooling sections). Note: `CONTEXT_TREE.md` still has pre-existing >200-char
  lines — full re-wrap deferred to RDO-5/RDO-6 (RDO-1 DoD gates `CONTEXT.md` only). | SHA: fd1bd0b
- [x] **RDO-2** — AGENTS.md decision + action. Animesh 2026-08-27: Antigravity autoloads
  `AGENTS.md` by name; it must stay a full standalone protocol equivalent to `CLAUDE.md` — do
  not delete. Action taken: rewrote `AGENTS.md` as a faithful, Antigravity-adjusted mirror of
  the current `CLAUDE.md` (agent identity → Antigravity; broken `.Codex/…` paths → `.claude/…`;
  module refs corrected to `CLAUDE.md`), added back the ~6 sections `CLAUDE.md` gained since the
  fork (Logging-standard/`no-script-main-logger`, Step 2b authoritative-mechanism, Step 3b
  independence note, full Quick-ref rows, `docs/plan/README.md` in 5a, Step 5d, review-rules
  trio), and replaced the stale 120-line "Imported Claude Cowork" appendix with a trimmed
  "Antigravity Reference" — Decimal/TEXT + UTC + async invariants inline, everything else
  (env vars, BrokerClient impl table, exception hierarchy) as pointers to `src/config.py` /
  `src/client/CLAUDE.md` / `ANTIGRAVITY.md` to avoid re-drift. Long-line wrap deferred to
  RDO-5/6 (mirror stays line-for-line with the un-wrapped `CLAUDE.md`; wrap both together).
  Follow-up `5a9c4f5`: audit pass fixed a non-existent `UpstoxSandboxClient`, an incomplete
  hand-maintained env table, and a restated exception list — all → pointers; added async
  conventions Antigravity can't see from the global `~/.claude/CLAUDE.md`. Open items the
  audit surfaced → **RDO-8**. Docs-only, no code-reviewer. | SHA: 5c25742
- [~] **RDO-3** — ~~Create `docs/archive/DECISIONS_ARCHIVE_2026H1.md`, move pre-2026-06-01
  entries, add date-descending `## Index`.~~ **Unworkable as specified (2026-08-27).**
  `DECISIONS.md` has no pre-2026 entries (earliest 2026-04-01), so "trailing 6 months" is the
  whole file; it is grouped by thematic `##` sections, not by date, with 2026-04/05 and
  2026-06/07/08 entries interleaved paragraph-by-paragraph inside several sections; and some
  historical-looking sections carry undated still-enforced rules (`§7.3` risk caps, `NT-2`
  Futures+CC block). Partial done — 5 fully-historical self-contained sections lifted to
  `docs/archive/DECISIONS_pre-2026-07.md` behind a one-line index (336 KB → 330 KB,
  2302 → 2203 lines; `PLANNER.md` + `BACKTEST_PLAN_PHASE1.md` cross-refs repointed). | SHA: 7bbfaff
  **Status: closed as partial — no further work on RDO-3 itself.** Remaining shrink is a
  different approach entirely, tracked as **RDO-9**.
- [x] **RDO-4** — Move `BUGS.md` → `docs/archive/BUGS_LEGACY.md` (3-line stub at root);
  move `GLOSSARY.md` → `docs/GLOSSARY.md` (no stub, add `CLAUDE.md` Quick-reference row).
  Fix all inbound links.
  Done 2026-08-27: `git mv` both (history preserved). Root `BUGS.md` stub → `docs/bugs/` +
  archive. Archive banner added to `BUGS_LEGACY.md`; its two `docs/bugs/` links repointed
  `../bugs/`. Glossary Quick-ref row added to `CLAUDE.md` **and** `AGENTS.md` (mirror
  invariant). Live links fixed: `TODOS.md:3` (`[BUGS.md]` → `[docs/bugs/]`),
  `docs/plan/README.md:6` (`../../BUGS.md` → `../archive/BUGS_LEGACY.md`), `docs/bugs/bugs.md`
  "Relationship to root `BUGS.md`" note rewritten to point at the archive. Historical
  references left as accurate records of past state: `DECISIONS.md:738` (dated 2026-07-02
  decision, prose not a link), `docs/plan/dev-foundation/**` (CH-3 completed-story records),
  `docs/plan/full-repo-review/findings/**` + `stories.md:263` (root-inventory audit
  snapshots), `docs/archive/**` (already archived). Docs-only, no code-reviewer.
  | Owner: Claude | Model: claude-sonnet-5 | SHA: 5bb5848
- [x] **RDO-5** — Add `scripts/hooks/check_md_line_length.py` + `.pre-commit-config.yaml`
  entry `md-line-length` (renamed from `root-md-line-length` — scope is wider now). Hard cap
  **200 chars**, a backstop for table rows + fenced code; the check enforces only this
  ceiling. Scope: root `.md` **plus `docs/plan/**` + `docs/bugs/**` `.md`** — the story docs
  hand-wrapped at ~90 cols are the main offenders, not the root files.
  **Prose style (decided 2026-08-27, recorded in RDO-13 §Conventions): semantic linefeeds**
  — one sentence/clause per line, no fixed-width hand-wrap for prose; ~120 is a soft target,
  not gated. `.py` stays at ruff's `line-length = 100` (unchanged; ruff already excludes
  `docs/`). Also delete the contradictory "Hard-wrap to ≤100 chars" instruction in `plan.md`
  Phase 1 step 1, and update the `files:` regex + `id` in `plan.md` Phase 5's yaml block.
  Done 2026-08-27 (tooling-only per Animesh): hook + `check_md_line_length.py`
  (`<!-- lint-ignore-length -->` escape on the preceding line) + 3 unit tests in
  `tests/unit/scripts/hooks/`; `plan.md` Phase 1 "≤100" contradiction removed, Phase 5 yaml
  block updated; semantic-linefeed + 200-cap style recorded in `docs/plan/README.md`
  §Conventions. The hook enforces on **staged** files only (standard pre-commit) — the
  ~800-line pre-existing backlog across ~18 files is not an RDO-5 gate; it is cleared
  opportunistically (any later commit touching a file trips the hook on that file) and in
  batch by RDO-6's `md-organize` skill + RDO-9's `DECISIONS.md` split.
  Verify: `pre-commit run md-line-length --files <clean .md>` passes; `--files
  docs/plan/mvp/prompt.md` fails with per-line `file:line: N chars` output;
  `pytest tests/unit/scripts/hooks/ -q` green.
  | Owner: Claude | Model: claude-sonnet-5 | SHA: 7c78799
- [ ] **RDO-6** — Rename `.claude/skills/md-cleanup/` → `md-organize/`, rewrite `SKILL.md`:
  broaden triggers, fix the "must stay at root" table, add CONTEXT.md re-slim + DECISIONS
  roll + line-length (200 cap) + semantic-linefeed prose reflow (RDO-5) + `CLAUDE.md`
  pointer-reconciliation steps. **Owns the RDO-5 backlog:** the `md-organize` run does
  `pre-commit run md-line-length --all-files` and clears every reported line (prose →
  semantic linefeeds, long table rows → restructured), for everything except `DECISIONS.md`
  (RDO-9). This is what makes `--all-files` eventually green. **Add (RDO-2):** an
  "AGENTS.md ← CLAUDE.md re-sync" step — diff the two protocol bodies and re-apply the
  Antigravity deltas whenever `CLAUDE.md` changed since the last sync.
  **Add (RDO-12):** include `.claude/skills/work/SKILL.md` in the re-sync scope — its
  Feature/Bug routing text duplicates `CLAUDE.md` Step 1 and must not drift.
  **Add (RDO-8):** `.agents/skills/` (kept — Antigravity autoloads it) is a drifted mirror of
  `.claude/skills/` with stale `.Codex/` paths + "Codex" identity language from `16821d6`;
  bring it into the re-sync scope and re-point it to `.claude/` on the first `md-organize` run.
  (`.codex/` was deleted in RDO-8 — dead, nothing read it.)
  **Add (RDO-13):** while wrapping `CLAUDE.md` + `AGENTS.md` long lines, also add a one-line
  Step 5a pointer to `docs/plan/README.md` §Conventions for the `| Owner | Model | SHA`
  task-line format + the `TODOS.md` pointer-only rule. Deferred from RDO-13 because staging
  either file pre-wrap trips `md-line-length` on its whole pre-existing backlog.
  Also add `scripts/hooks/check_story_structure.py --all` as a periodic audit step (RDO-13 §3)
  and pick the final `md-cleanup` → `md-organize` name (coordinate with RDO-10 #4).
- [ ] **RDO-7** — Add report-only `DOC STALENESS` section to
  `.claude/skills/session-close/SKILL.md` (Option A in `plan.md`). Report only — no
  unattended commits.
- [x] **RDO-8** — Protocol-doc consistency cleanup (surfaced by the RDO-2 audit,
  2026-08-27). Independent of RDO-3..7; can be done in any order. Each bullet is a small
  targeted fix — one commit for the lot is fine since they are all protocol/doc consistency.
  Done 2026-08-27: (1) `ANTIGRAVITY.md` step 2 docs/config-only bullet aligned to "skip
  `code-reviewer` entirely" — matches `CLAUDE.md` / `AGENTS.md` 5c. (2) `.codex/` deleted
  (`git rm -r` — dead, only self-referenced by its own `hooks.json`); `.agents/` kept per
  Animesh (Antigravity autoloads it) → added to RDO-6's re-sync scope with a note about its
  stale `.Codex/` refs. (3) `src/paper/` `src/nuvama/` `src/gamma/` rows added to the module
  table in both `CLAUDE.md` and `AGENTS.md`; `AGENTS.md`'s "Also present on disk" note folded
  into the table so the two match line-for-line. (4) `src/client/CLAUDE.md` heading + the
  `src/client/` module-table row in both files reworded to "implementations (2 built + 1
  variant + 1 planned)". (5) `CLAUDE.md`'s embedded "Rules for any review" lifted into a
  standalone `## Rules for any review or handoff` section matching `AGENTS.md`; both bodies
  set to identical full text. Docs/config-only, no code-reviewer.
  | Owner: Claude | Model: claude-sonnet-5 | SHA: bf26d81
  1. **Docs-only commit gate conflict.** `ANTIGRAVITY.md` §"Commit Protocol" step 2 requires a
     `code-reviewer.md` + `REVIEW.md` persona review even for a docs/config-only commit;
     `CLAUDE.md` 5c and `AGENTS.md` 5c both say docs-only → skip `code-reviewer` entirely.
     Pick one rule and make all three files agree (recommend: keep the skip, it is the lighter
     and more-used path — align `ANTIGRAVITY.md` to it).
  2. **Dead `.agents/skills/` + `.codex/hooks/` trees.** Created by commit `16821d6`
     ("Codex protocol scaffolding"). `AGENTS.md` and `ANTIGRAVITY.md` now both point only at
     `.claude/…`. Confirm nothing reads `.agents/` or `.codex/` (grep configs, ask Animesh
     whether any Codex/Antigravity runner still references them), then delete both trees or
     leave a one-line pointer stub. If kept, add them to the `md-organize` re-sync scope.
  3. **`CLAUDE.md` module table stale.** Lists 5 `src/<module>/CLAUDE.md` rows; 8 exist on
     disk (missing `paper`, `nuvama`, `gamma`). Add the 3 missing rows to `CLAUDE.md`; then
     the `AGENTS.md` "also present on disk" note can be folded back into the main table so the
     two match line-for-line again. (Overlaps RDO-6's `CLAUDE.md` pointer-reconciliation step
     — do whichever lands first, then drop the dup from the other.)
  4. **`src/client/CLAUDE.md` "Four Implementations" heading.** Only 2 concrete `BrokerClient`
     classes are built (`UpstoxLiveClient`, `MockBrokerClient`); the table's other 2 rows are
     a token-variant and an unbuilt `ReplayMarketStream`. Reword the heading/table so the
     count is not misleading (e.g. "Implementations (2 built + 1 variant + 1 planned)").
  5. **`AGENTS.md` ↔ `CLAUDE.md` structural divergence for re-sync.** RDO-2 pulled CLAUDE.md's
     embedded "Rules for any review" (points 1–3, inside its AI-Collaboration section) into a
     standalone `## Rules for any review or handoff` section in `AGENTS.md`. Either lift
     `CLAUDE.md` to the same structure or document the delta in the RDO-6 re-sync step so the
     diff stays predictable.

- [ ] **RDO-9** — DECISIONS.md **semantic split** (replaces RDO-3's dead date-cutoff).
  Root `DECISIONS.md` is big because it is append-only and verbose inside a ~4-month window,
  not because it is old — a date archive can't shrink it. Split by *kind* instead:
  1. Classify every remaining entry as **STILL-ENFORCED RULE** (a constraint code or process
     obeys today) or **COMPLETED-WORK LOG** (records that a change landed + why; value is
     historical). Keep the thematic `##` grouping.
  2. Move the COMPLETED-WORK-LOG entries to `docs/archive/DECISIONS_worklog_2026.md`, same
     headers, newest-first within each; leave the one-line topic index in root (extend the
     `## Archived — pre-2026-07 reference sections` block RDO-3 started).
  3. Root `DECISIONS.md` keeps only STILL-ENFORCED RULES + the index. Undated rule sections
     (`§7.3` risk caps, `## Developer Tooling`'s `NT-2` block) stay. Target ≤ 800 lines.
  4. Verify inbound `DECISIONS.md` / `DECISIONS.md#` refs repo-wide still resolve or are
     redirected in the index.
  **Council/advisory:** archiving an entry that is actually load-bearing is the failure mode.
  Split into 9a (classify + `options-strategist` advisory pass on the risk/greeks/exit-rule
  entries + Animesh sign-off on the STILL-ENFORCED list) then 9b (execute the move). 9b does
  not start until 9a's list is signed off.
  Verify: `wc -l DECISIONS.md` ≤ 800; fresh full-file `Read` under the display cap;
  `pre-commit run md-line-length --files DECISIONS.md` green (RDO-5's ~300 long lines here
  are the split's responsibility — wrap surviving rule entries to semantic linefeeds).

- [ ] **RDO-10** — Reconcile RDO-7 / Phase 7 with the doc-freshness mechanisms the parallel
  "round-2 workflow token-optimization" epic shipped 2026-08-27 (`TODOS.md ### 2026-08-27`):
  - `758dd6b` — `.claude/hooks/state_doc_freshness.sh`, `SessionStart`: per-state-doc flag
    when `src/`|`scripts/` commits since its last change exceed a threshold. Informational.
  - `7dae8e3` — `.claude/hooks/doc_update_gate.sh`, `PreToolUse`/`Bash` on `git commit`:
    stderr reminder when a `.py` commit under `src/`|`scripts/` stages no state-doc change.
    Advisory now; slated to flip to `exit 2` after a week's false-positive observation.
  - `TODOS.md #4` (deferred) — `/schedule` a weekly `md-cleanup` cloud routine, which Phase 7
    explicitly rejected ("unattended writes to source-of-truth docs is the wrong risk trade").
  Task:
  1. Decide if RDO-7's session-close `DOC STALENESS` report is still wanted on top of the
     SessionStart hook, or redundant. If kept, scope it to what the hook can't see (per-entry
     `CONTEXT_TREE.md` / `docs/plan/README.md` gaps, not per-file commit counts).
  2. Add both shipped hooks to this epic's inventory (`plan.md` table) and to RDO-6's
     `md-organize` re-sync scope.
  3. Resolve `#4` against Phase 7's "no unattended doc writes" — drop it, or narrow to a
     read-only Telegram staleness report (Phase 7 said that would be acceptable).
  4. `md-cleanup` vs RDO-6's planned `md-organize` rename — `#4` still references the old
     name; pick the final name once, here.
  5. Tune `state_doc_freshness.sh` thresholds — `DB_REGISTRY.md` trips at 36/35 with a
     2-day-old edit (known false positive).

- [ ] **RDO-11** — Graduate the advisory doc-freshness hooks to enforcing. Observation
  window opened 2026-08-27; **first review on/after 2026-09-03.**
  1. `doc_update_gate.sh` (`7dae8e3`) — review ~1 week of firings: grep `git log` for
     `[skip-docs]` escapes and for `.py`-under-`src/`|`scripts/` commits where the reminder
     was a false positive (pure refactor, mid-phase multi-commit work). If the false-positive
     rate is tolerable, flip `exit 0` → `exit 2` (blocking) and document the `[skip-docs]`
     escape in `CLAUDE.md` 5c + `AGENTS.md` 5c. If not, tighten the staged-file match or keep
     it advisory and re-review after another week.
  2. `state_doc_freshness.sh` (`758dd6b`) — apply RDO-10 #5's threshold tuning, then confirm
     the flag is signal not noise across 3–4 real sessions.
  3. Record the final behaviour (blocking / advisory / tuned thresholds) as a STILL-ENFORCED
     RULE entry in `DECISIONS.md`, so the hook contract is documented, not only coded.
  Depends on RDO-10 #5 for the threshold values; otherwise independent.

- [x] **RDO-12** — Unified session entry point (`/work` skill). Spun out of the 2026-08-27
  workflow-suggestion triage; full spec in `docs/plan/session-entry-point/` (SEP-1..4).
  **Closed 2026-08-27** — `session-entry-point` epic complete (SEP-1..4); both `/work`
  branches demonstrated end-to-end. `md-organize` re-sync scope already named the skill
  (RDO-12 triage into RDO-6).
  1. Manual `/work` skill routes a task-shaped session to **Feature** (first 5 of `TODOS.md`
     "Priority-Ordered Open Work") or **Bug** (`docs/bugs/` open entries), then loads that
     prompt + first unchecked task + `CONTEXT.md` and hands to `CLAUDE.md` Step 2b.
  2. `CLAUDE.md` Step 1 + `AGENTS.md` point at `/work`; the scattered per-work-type load
     hints collapse into the skill (one source of truth).
  3. Feeds RDO-6 — `md-organize` re-sync scope gains `.claude/skills/work/SKILL.md`.
  No SessionStart hook — manual invocation only (decided 2026-08-27).
  Verify: `/work` in a real session reaches a loaded prompt on both branches; see
  `docs/plan/session-entry-point/tasks.md` "Epic done when".

- [x] **RDO-13** — `docs/plan/` + `TODOS.md` convention enforcement. From the 2026-08-27
  workflow-suggestion triage. `docs/plan/README.md` §Conventions is the single source of
  truth; `docs/archive/plan/README.md` §Conventions is dead (old per-story-file scheme) —
  delete the "Full conventions" pointer to it.
  1. **Canonical story-folder spec.** Rewrite `docs/plan/README.md` §Conventions to fix the
     exact file set — `prompt.md` + `tasks.md` required, `stories.md` + `spec.md` optional;
     no `<slug>_` filename prefix. Add `docs/plan/_TEMPLATE/` (copyable skeleton). Record the
     MD wrapping style here too — semantic linefeeds, 200-char backstop (see RDO-5).
  2. **Task-line format.** Every `tasks.md` checkbox, when completed, carries
     `| Owner: <Claude|Antigravity|Animesh> | Model: <model|n/a> | SHA: <sha>` — records the
     Step 3b routing outcome + the commit per task (Model = implementing model when
     Owner=Claude, `n/a` otherwise — confirm during build). Document in the same §Conventions
     block and in `CLAUDE.md` "After each task".
  3. **`check_story_structure.py`.** `scripts/hooks/` script: every non-archived
     `docs/plan/*/` folder has the required files; flags stray/empty folders (sweeps the
     empty `monitor-and-close-hardening/` + `paper-ic-daily-snapshot/`). Wired into RDO-6's
     `md-organize` as a periodic audit step — not pre-commit (folders churn ~monthly).
     Optional: pre-commit on added folders only (`git diff --diff-filter=A`).
  4. **`TODOS.md` hygiene rule.** Priority-list items are pointer-only: title + story/bug
     path + next task + one-line why. No inline multi-paragraph detail (items 14/22/29 are
     the current offenders — retrofit). Task-level progress is marked ONLY in the story's
     `tasks.md` / `docs/bugs/task.md`, never mirrored into `TODOS.md`. When a story/bug is
     fully done, its `TODOS.md` line is deleted (moved to `docs/archive/TODOS_ARCHIVE.md`),
     not just ticked. Add a header pointer in `TODOS.md` to `docs/plan/` + `docs/bugs/` as
     the task-tracking homes. Encode in `CLAUDE.md` §Step 5a + the `session-close` /
     `md-organize` skills.
  5. Grandfather existing folders — the audit lists offenders; retrofit opportunistically,
     not in one big bang.
  Feeds RDO-6 (audit step) and RDO-12 (clean first-5 `TODOS.md` items). Independent otherwise.
  Verify: `_TEMPLATE/` exists; `check_story_structure.py` green after retrofit; a freshly
  ticked `tasks.md` task shows the `Owner|Model|SHA` tail; `docs/plan/README.md` §Conventions
  is self-contained (no archive pointer).
  **Done 2026-08-28 (Claude, 3 commits):**
  13a `0712b49` — `docs/plan/README.md` §Conventions rewritten canonical + self-contained
  (archive pointer removed), all 17 pre-existing >200-char table rows reflowed into compact
  per-story status entries, `docs/plan/_TEMPLATE/{prompt,tasks}.md` added.
  13b `a0d255d` — `scripts/hooks/check_story_structure.py` (story-vs-epic detection; `--all`
  audit / `--staged-added` pre-commit / path modes; legacy `*_tasks.md` warning) + 11 tests
  + `.pre-commit-config.yaml` wiring; two empty stray folders removed.
  13c `<this commit>` — structure-audit + pointer-only steps added to `md-cleanup` +
  `session-close` skills; `TODOS.md` header pointer + pointer-only note.
  **Deferred to RDO-6** (item 3 add + this task's §2): the `CLAUDE.md` / `AGENTS.md` Step 5a
  pointer to the task-line format. Both files carry ~13 pre-existing >200-char lines RDO-2
  deferred wrapping to RDO-6; staging either trips `md-line-length` on the whole backlog, and
  RDO-2 mandates wrapping the two mirrors together. `docs/plan/README.md` §Conventions is the
  canonical home (§1) and is complete; RDO-6 adds the one-line CLAUDE.md/AGENTS.md pointer
  when it wraps + re-syncs those files. Retrofit of `TODOS.md` items 14/22/29 stays with
  RDO-14 (any `TODOS.md` edit forces the full reflow anyway).
  | Owner: Claude | Model: claude-sonnet-5 | SHA: 3c50826

- [ ] **RDO-14** — Restructure `TODOS.md` "Priority-Ordered Open Work" into one unified,
  priority-ordered queue covering **both** `docs/plan/` stories and `docs/bugs/` open entries.
  Today it is feature-only with rotted numbering (`0e.` then jumps to `9.`, item 14 listed
  twice, `TGFMT-2..9` still present though superseded by item 29); bugs are absent except
  BUG-030 wedged in as `0e`/`3`. This is the list `/work` (SEP) reads to build its first-5
  menu, so its incoherence is a live problem, not cosmetic.
  1. Single contiguous `1..N` numbering. Each item pointer-only per RDO-13 §4 — title,
     `docs/plan/<story>/` or `docs/bugs/` path, next unchecked task id, one-line why; no
     inline multi-paragraph detail.
  2. Interleave bugs and features by actual priority — one queue, not two sections.
  3. Drop superseded / duplicate entries; replace the internal `"Blocked by item N"`
     number-refs with story-folder names so they stop rotting on every renumber.
  4. Coordinate with SEP: once the queue is unified, `/work`'s separate Feature / Bug branches
     can collapse to a single "top N of the queue" presentation — file a follow-up SEP task in
     `docs/plan/session-entry-point/`; do not rework the skill here.
  Feeds RDO-12 (a coherent first-5). Best done right after RDO-13 §4's pointer-only rule is
  written, so both land consistent.
  Verify: `TODOS.md` priority list is `1..N` contiguous; every item resolves to a live
  `docs/plan/*/` or `docs/bugs/` path; no superseded items; bugs and features interleaved by
  priority.

- [ ] **RDO-15** — Same-id checkbox duplication audit + drift guard. From the 2026-08-27
  observation that `docs/plan/session-entry-point/tasks.md` (and by pattern most story
  `tasks.md`) tracks each task id with **two** checkboxes — one in the working task list, one
  in the trailing `## Epic done when` summary — plus a third state signal in
  `docs/plan/README.md` and any `stories.md` DoD box. Ticking one and forgetting the others
  silently desyncs; a reader/agent can then treat a stale box as authoritative. Same class as
  `TODOS.md` mirroring (RDO-13 §4) and `AGENTS.md` ↔ `CLAUDE.md` divergence (RDO-8 #5) —
  duplicated state with no reconciliation.
  1. **Sweep.** Script (extend RDO-13's `check_story_structure.py`, or a sibling
     `check_checkbox_consistency.py`): for every non-archived `docs/plan/*/tasks.md` and
     `docs/bugs/task.md`, parse `- [ ] / - [x] **<ID>**` lines, group by `<ID>`, flag any id
     whose checkbox state is not identical across all its occurrences in the file.
  2. **Decide the model per file.** Either (a) one checkbox per id — the working list is the
     sole source of truth, the `Epic done when` block becomes an unchecked *criteria* list
     (prose, no `- [ ]`), or (b) keep the summary but mark it "mirror — do not hand-edit" and
     have the script enforce equality. Pick one convention, record it in
     `docs/plan/README.md` §Conventions, retrofit `_TEMPLATE/`.
  3. **Cross-file.** `tasks.md` id-state vs `docs/plan/README.md` "next task" column vs
     `stories.md` DoD box — document which is canonical (tasks.md) and that the others are
     derived; the sweep script warns on `README.md` "next task" pointing at an already-ticked
     id.
  4. Wire the check into RDO-6's `md-organize` periodic audit (same cadence as
     `check_story_structure.py`), not pre-commit.
  5. Grandfather — the sweep lists offenders; retrofit opportunistically. Fix
     `session-entry-point/tasks.md` as the worked example.
  Feeds RDO-6 (audit step) and RDO-13 (shares the checker script + §Conventions block).
  Verify: the sweep script runs clean across `docs/plan/**` + `docs/bugs/` after retrofit;
  §Conventions names the one-checkbox-per-id convention; `_TEMPLATE/tasks.md` follows it.

## Epic done when

All boxes checked:
- [x] **RDO-4** — `BUGS.md` / `GLOSSARY.md` relocated, all inbound links fixed.
- [x] **RDO-5** — `md-line-length` hook (200-char cap) added + enforcing on staged files;
      `check_md_line_length.py` + 3 unit tests; semantic-linefeed prose style recorded in
      `docs/plan/README.md` §Conventions; `plan.md` Phase 1's "≤100" contradiction removed,
      Phase 5 yaml updated. Full-repo `--all-files` green is **not** an RDO-5 gate (Animesh,
      2026-08-27) — backlog cleared by RDO-6 (`md-organize`) + RDO-9 (`DECISIONS.md` split).
- [ ] **RDO-6** — `md-organize` skill exists; "stay at root" table matches reality; includes
      CONTEXT re-slim / DECISIONS roll / line-length / `CLAUDE.md` pointer-reconcile /
      `AGENTS.md` ↔ `CLAUDE.md` re-sync steps.
- [ ] **RDO-7** — session-close `DOC STALENESS` report added, or explicitly dropped as
      redundant per RDO-10 #1.
- [x] **RDO-8** — all 5 protocol-doc consistency fixes landed. Done 2026-08-27 (SHA `bf26d81`).
- [ ] **RDO-9** — `DECISIONS.md` ≤ 800 lines; work-log entries split to
      `docs/archive/DECISIONS_worklog_2026.md`; 9a STILL-ENFORCED list signed off by Animesh.
- [ ] **RDO-10** — both hooks in `plan.md` inventory + RDO-6 re-sync scope; `#4` resolved;
      final skill name picked.
- [ ] **RDO-11** — hook enforcement decision made and recorded in `DECISIONS.md`.
- [x] **RDO-12** — `/work` skill exists and routes Feature/Bug; `CLAUDE.md` + `AGENTS.md`
      point at it; see `docs/plan/session-entry-point/` "Epic done when". Closed 2026-08-27 —
      `session-entry-point` epic (SEP-1..4) complete; both branches demonstrated end-to-end.
- [x] **RDO-13** — `docs/plan/README.md` §Conventions is canonical + self-contained;
      `_TEMPLATE/` + `check_story_structure.py` exist; ticked task lines carry
      `Owner|Model|SHA`; `TODOS.md` pointer-only rule encoded; empty story folders swept.
      Done 2026-08-28 (13a `0712b49`, 13b `a0d255d`, 13c). CLAUDE.md/AGENTS.md 5a pointer
      folded into RDO-6; `TODOS.md` items 14/22/29 retrofit stays with RDO-14.
- [ ] **RDO-14** — `TODOS.md` priority list is one `1..N` contiguous bug+feature queue;
      no superseded/duplicate items; internal cross-refs use folder names not item numbers.
- [ ] **RDO-15** — checkbox-consistency sweep script runs clean across `docs/plan/**` +
      `docs/bugs/`; one-checkbox-per-id convention recorded in §Conventions + `_TEMPLATE/`;
      `session-entry-point/tasks.md` retrofitted as the worked example.
- [ ] **`prompt.md` DoD rewritten** to the delivered design — drop the dead pre-2026H1
      date-cutoff line, state the hook + semantic-split reality.
- [ ] **Loop-closure check** — one real session, start to finish, confirms the mechanism
      works end to end: a state doc goes stale under code churn → `state_doc_freshness.sh`
      flags it at SessionStart → the flag is acted on (Step 5a or `md-organize`) → the flag
      clears the next session. This is the actual test of "the docs preserve their state,"
      not any individual hook.

RDO-1, RDO-2 done. RDO-3 closed as partial (remainder = RDO-9).

## After each task
Tick the box, append `| SHA: <sha>`, update `docs/plan/README.md` status column for this
story, add one line to `TODOS.md` Session Log.
