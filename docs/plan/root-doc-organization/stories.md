# Root doc organization — story specs

> One task per session. Find the first unchecked item in `tasks.md`; that is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, update the `docs/plan/README.md` status entry, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

This is a docs + tooling story throughout — no `.py` under `src/`. Hook scripts under `scripts/dev/hooks/` were the only code touched (RDO-5, RDO-13, RDO-15, RDO-17.2 → `Review:
code-reviewer`); every other task is `Review: none`. Everything in this story was owned and implemented by Claude on `claude-sonnet-5` — no Antigravity or Animesh implementation in its
history (RDO-17.7 §B is the first Animesh-owned line, and it is a decision, not an implementation).

The **open** tasks (RDO-11, RDO-16) carry a full forward spec below. The **shipped** tasks carry a 2–4 line as-built digest — what changed, the key deviation, the closing SHA —
reconstructed from the (now collapsed) inline `tasks.md` notes plus the `TODOS.md` Session Log. For full forensic detail on a shipped task, read its Session Log entry or `git show <sha>`.

---

## Open tasks — full forward spec

### RDO-11 — graduate the advisory doc-freshness hooks to enforcing

**Gate:** do not start before **2026-09-03**. The observation window opened 2026-08-27 and needs ~1 week of real firings to judge the false-positive rate.

**Files to change:**
- `.claude/hooks/doc_update_gate.sh` — the `exit 0` → `exit 2` flip, iff the false-positive rate is tolerable.
- `.claude/hooks/state_doc_freshness.sh` — apply RDO-10 #5's threshold tuning if not already landed (`CONTEXT_TREE.md` / `DB_REGISTRY.md` / `README.md`
  → 60); confirm signal-not-noise across 3–4 real sessions.
- `CLAUDE.md` §Step 5c + `AGENTS.md` §Step 5c — document the `[skip-docs]` commit-message escape hatch, iff `doc_update_gate.sh` becomes blocking.
- `DECISIONS.md` — one STILL-ENFORCED RULE entry recording the final hook contract (blocking / advisory, the tuned thresholds) so it is documented, not only coded.

**Before any code:**
- `git log --oneline --since=2026-08-27 -- src/ scripts/` — the commits the gate saw.
- `git log --all --grep='\[skip-docs\]' --oneline` — how often the escape hatch was used.
- Read both hook scripts as text (shell, not graph-indexed).

**What to implement:**
1. Review ~1 week of `doc_update_gate.sh` firings; count the false positives (pure refactors, mid-phase multi-commit work where the doc update lands in a later commit).
2. If the false-positive rate is tolerable: flip `exit 0` → `exit 2` and document `[skip-docs]` in both `CLAUDE.md` / `AGENTS.md` §Step 5c. If not:
   tighten the staged-file match, or keep it advisory and re-review after another week.
3. Confirm `state_doc_freshness.sh` thresholds are the RDO-10 #5 values and the flag is signal not noise.
4. Record the outcome as a STILL-ENFORCED RULE entry in `DECISIONS.md`.

**Tests:** the hook scripts have unit coverage under `tests/unit/scripts/` — extend it if the match logic changes. No new domain tests.

**Commit:** `chore(hooks): graduate doc-freshness gate to <blocking|tuned-advisory>`

### RDO-16 — doc-freshness loop-closure check

The end-to-end test of "the docs preserve their state" — not any individual hook. Runs after RDO-6 (`md-organize`), which is shipped.

**Files to change:** none by default — this is a verification task. It produces a one-line `TODOS.md` Session Log entry recording the result and ticks its own box.

**What to verify — one real session, start to finish:**
1. A state doc goes stale under code churn (`src/` / `scripts/` commits accumulate past its threshold in `state_doc_freshness.sh`).
2. `state_doc_freshness.sh` flags it at SessionStart.
3. The flag is acted on — either `CLAUDE.md` Step 5a in that session, or a full `md-organize` run.
4. The flag clears at the next SessionStart.

If any link breaks (flag never fires, threshold wrong, `md-organize` doesn't touch the flagged doc, flag persists after the fix), file the gap as a new RDO task and leave RDO-16 open.

**Commit:** `docs(plan): close RDO-16 — doc-freshness loop verified end to end`

### RDO-17.7 §B — legacy-folder conversion rule (Owner: Animesh)

Once RDO-17.5 and RDO-17.6 land, decide the rule for the remaining ~25 legacy `docs/plan/` folders: convert-on-next-touch vs. a scheduled batch, the per-folder effort ceiling, the
reconstruction risk for old SHAs, and whether some folders stay grandfathered permanently. §A (the fill-to-≤200 line style) is finalized and shipped inside RDO-17.5 — see the digest below.

---

## Shipped tasks — as-built digests

### RDO-1 — slim CONTEXT.md (SHA `fd1bd0b`)
CONTEXT.md 156 → 159 lines but ~20K → ~2.6K tokens; the run-on "What Exists" paragraphs became a one-line-per-package list pointing at `CONTEXT_TREE.md`. Old prose archived verbatim to
`docs/archive/CONTEXT_WHAT_EXISTS_2026-08.md`; `CONTEXT_TREE.md` enriched with the structural facts that would otherwise have been lost. Deviation: `CONTEXT_TREE.md`'s own >200-char lines
left for the RDO-5/6 sweep (RDO-1's DoD gates CONTEXT.md only).

### RDO-2 — AGENTS.md as a CLAUDE.md mirror (SHA `5c25742`)
Animesh ruled AGENTS.md must stay a full standalone protocol (Antigravity autoloads it by name). Rewritten as a faithful Antigravity-adjusted mirror: agent identity → Antigravity, broken
`.Codex/…` paths → `.claude/…`, the ~6 sections CLAUDE.md gained since the fork re-added, the stale 120-line Cowork appendix replaced with a trimmed reference (invariants inline, the rest as
pointers). Follow-up `5a9c4f5` fixed a non-existent `UpstoxSandboxClient` and a restated exception list → pointers. Open items the audit surfaced → RDO-8.

### RDO-3 — DECISIONS.md date archive (SHA `7bbfaff`, closed partial)
Original spec (move pre-2026-06-01 entries to a `2026H1` archive) was **unworkable**: DECISIONS.md has no pre-2026 entries, is grouped thematically not chronologically, and interleaves
2026-04/05 with 2026-06/07/08 inside sections. Partial done — 5 fully-historical self-contained sections lifted to `docs/archive/DECISIONS_pre-2026-07.md` behind a one-line index
(336 KB → 330 KB). Closed as a partial; the real shrink is a semantic split → RDO-9.

### RDO-4 — relocate BUGS.md + GLOSSARY.md (SHA `5bb5848`)
`git mv` both (history preserved). Root `BUGS.md` → 3-line stub pointing at `docs/bugs/` + `docs/archive/BUGS_LEGACY.md`; `GLOSSARY.md` → `docs/GLOSSARY.md`, no stub, Quick-reference row
added to CLAUDE.md **and** AGENTS.md (mirror invariant). Live inbound links fixed in `TODOS.md`, `docs/plan/README.md`, `docs/bugs/bugs.md`; historical references left as accurate records of
past state.

### RDO-5 — md-line-length pre-commit hook (SHA `7c78799`, `Review: code-reviewer`)
`check_md_line_length.py` (200-char hard cap, all line kinds; `<!-- lint-ignore-length -->` on the preceding line excuses one unbreakable token) + `.pre-commit-config.yaml` entry
`md-line-length` (scope: root `.md` + `docs/plan/**` + `docs/bugs/**`) + 3 unit tests. Enforces on **staged** files only — the ~800-line pre-existing backlog is not an RDO-5 gate (cleared by
RDO-6 + RDO-9). The `plan.md` "≤100 chars" contradiction removed; semantic-linefeed style recorded in §Conventions (later retired by RDO-17.7 §A).

### RDO-6 — md-cleanup → md-organize skill (SHA `3eb3834`, 3 commits)
`git mv md-cleanup → md-organize` + full `SKILL.md` rewrite (19-file root table; CONTEXT re-slim / DECISIONS roll / repo-wide `md-line-length` sweep / `CLAUDE.md` pointer reconcile /
structure + checkbox audits / RDO-10 hook-drift check; Step 7 mirror re-sync = AGENTS.md + `.agents/skills/` + `work/SKILL.md`). `.agents/skills/` re-synced wholesale, every "Codex" ref gone.
CLAUDE.md + AGENTS.md 11 over-200 lines each wrapped; RDO-13 Step 5a task-line pointer added to both. `3eb3834`: ~700 over-200 lines across ~70 files reflowed by 5 parallel subagents,
`--all-files` green. Deviation: dense synthesis tables became `### N` subsections rather than reflowed rows — row numbers and all cell text preserved.

### RDO-7 — session-close DOC STALENESS report (SHA `d24f15d`)
Added as `Step 3e — Doc staleness (content gaps)` in `session-close/SKILL.md`: report-only, two checks — (a) a `src/<module>/` added this session with no matching `CONTEXT_TREE.md` row;
(b) a story whose code was touched this session but whose `docs/plan/README.md` status column was not advanced. Explicitly does not re-report the SessionStart hook's src-commit counts and
does not commit any fix. `Doc staleness:` line added to the Step 5 report block. Scope was narrowed to content-gaps-only by RDO-10 #1.

### RDO-8 — protocol-doc consistency cleanup (SHA `bf26d81`)
5 fixes in one docs/config-only commit: (1) `ANTIGRAVITY.md` step 2 docs-only bullet aligned to "skip `code-reviewer` entirely"; (2) `git rm -r .codex/` (dead scaffolding), `.agents/` kept
per Animesh and added to RDO-6's re-sync scope; (3) `src/paper/` `src/nuvama/` `src/gamma/` rows added to the module table in both CLAUDE.md + AGENTS.md; (4) `src/client/CLAUDE.md` heading
reworded "2 built + 1 variant + 1 planned"; (5) CLAUDE.md's embedded "Rules for any review" lifted to a standalone section matching AGENTS.md.

### RDO-9 — DECISIONS.md semantic split (SHA `2fb5c5b`, 3 commits)
Split by *kind* not date: 9a classified every entry as STILL-ENFORCED RULE or COMPLETED-WORK LOG (with an `options-strategist` advisory pass on risk/greeks/exit entries + Animesh sign-off);
9b moved the work-log stream to `docs/archive/DECISIONS_worklog_2026.md`, lifted 11 still-enforced fragments into a new `## Risk, Delta & Entry Gates` section, corrected 8 stale entries,
then semantic-linefeed-wrapped to `md-line-length` green. Deviation: 972 lines vs the "≤ 800" target — the line-count target and the wrap requirement conflict; ~84K → ~22K tokens and a clean
full-file `Read` are the goals that hold.

### RDO-10 — reconcile RDO-7 with the shipped freshness hooks (SHA `a4431ec`)
A parallel epic shipped `state_doc_freshness.sh` (SessionStart, informational) + `doc_update_gate.sh` (PreToolUse, advisory) on 2026-08-27. Decisions with Animesh: RDO-7 **kept but
narrowed** to content gaps the hooks can't see; both hooks added to `plan.md` Phase 7 inventory + an RDO-6 verification step; `TODOS.md #4` narrowed to a future read-only Telegram digest
(unattended-write cron stays rejected); final skill name `md-organize` confirmed; `state_doc_freshness.sh` thresholds tuned (`CONTEXT_TREE.md` / `DB_REGISTRY.md` / `README.md` 35 → 60).

### RDO-12 — unified /work session entry point (SHA `42eabb2`)
Spun out of the 2026-08-27 workflow-suggestion triage into its own epic `docs/plan/session-entry-point/` (SEP-1..4), now archived. Delivered a manual `/work` skill that routes a task-shaped
session to Feature (first 5 of `TODOS.md` `## Feature Backlog`) or Bug (`docs/bugs/` open entries), loads the prompt + first unchecked task + `CONTEXT.md`, and hands to `CLAUDE.md` Step 2b.
No SessionStart hook — manual invocation only. Fed RDO-6 (`md-organize` re-sync scope gained `work/SKILL.md`).

### RDO-13 — docs/plan + TODOS.md convention enforcement (SHA `3c50826`, 3 commits, `Review: code-reviewer`)
13a: `docs/plan/README.md` §Conventions rewritten canonical + self-contained (archive pointer dropped), 17 pre-existing >200-char story rows reflowed, `_TEMPLATE/{prompt,tasks}.md` added.
13b: `check_story_structure.py` + 11 tests + pre-commit wiring (story-vs-epic detection; `--all` / `--staged-added` / path modes); two empty stray folders removed. 13c: structure-audit +
pointer-only steps in the `md-cleanup` / `session-close` skills. The `CLAUDE.md` / `AGENTS.md` Step 5a pointer was deferred to RDO-6 (staging either mirror pre-wrap trips the whole backlog).

### RDO-14 — restructure TODOS.md (SHA `e7cecab`)
Design changed by Animesh: *not* one unified queue — two pointer-only lists, `## Feature Backlog` (`1..N` contiguous, `docs/plan/`) and `## Open Bugs` (non-authoritative snapshot + pointer to
`bugs.md`). Dropped completed `session-entry-point`, superseded `telegram-ic-comparison-formatting`, the duplicate "item 14", all `TGFMT-2..9` refs; every internal `"item N"` cross-ref →
story-folder name. Added a `docs/plan/README.md` §Conventions *Completion → archive* subsection + a `session-close` "done-but-not-archived" check. Whole file reflowed.

### RDO-15 — same-id checkbox duplication audit (SHA `5e48451`, `Review: code-reviewer`)
Chose convention (a) (Animesh delegated): `## Epic done when` blocks are prose acceptance criteria with no checkboxes, so drift is structurally impossible. Sibling script
`check_checkbox_consistency.py` (not an extension of `check_story_structure.py` — different scope + exit semantics). `stories.md` DoD box documented as a derived mirror, not swept. Retrofit
trivial (only 2 files used the mirror, zero pre-existing drift). Non-task "loop-closure check" promoted to RDO-16. Wired into the `md-organize` periodic audit.

### RDO-17.1 — standardize the story/epic format spec (SHA `7b6d05f`)
Rewrote `docs/plan/README.md` §Conventions: folder shapes (flat single-story vs epic root = `prompt.md` + `README.md` + sub-story folders, no `stories/` layer), the 3-file story set
(`prompt.md` + `tasks.md` + `stories.md`), the `schema.md` checklist (required only on DB-schema change), the extra-files rule, and the 5-field `| Owner | Model | Review | SHA` task line.
`_TEMPLATE/` restructured into `story/` + `epic/` variants.

### RDO-17.2 — rework the structure hooks (SHA `fe280bd`, `Review: code-reviewer`)
`check_story_structure.py` rewritten for the RDO-17.1 shapes (3-file story, epic root = `prompt.md` + `README.md`, `schema.md` warn-backstop, extra-file checks, legacy shapes grandfathered
under `--all`). `check_checkbox_consistency.py` gained the `| Owner | Model | Review | SHA` tail-shape check (`Review` one of four tokens; `SHA` a placeholder iff unchecked, a real 7–40 hex
SHA iff ticked; legacy tails grandfathered). `SUMMARY_RE` gained `story done when`. Hook unit tests updated — 42 green.

### RDO-17.3 — /work epic-descent + Review-field propagation (SHA `28d0d9c`)
`.claude/skills/work/SKILL.md` gained real epic-descent steps (walk the router's fixed story order, active story = first with an unchecked box) and the epic router body in
`_TEMPLATE/epic/prompt.md` was finalized. The `| Review:` field propagated into `session-close` / `md-organize` skills + `CLAUDE.md` §Step 5a + the `AGENTS.md` mirror. `commit/SKILL.md`
carries no task-line tail — nothing to change there.

### RDO-17.4 — partial retrofit of the two validation folders (SHA `35d9f42`, close `8e7273c`)
Brought `root-doc-organization/` (added `stories.md` for open tasks only; `| Review:` tail on open lines; `## Epic done when` → `## Story done when`) and `telegram-markdown-migration/`
(dropped `.DS_Store`; archived the exhausted `TODO.md` + `missing-message-workshop-prompt.md`; `README.md` repointed) into *structural* conformance, grandfathering the shipped task lines.
Both hooks `--all` went 14 → 12 warnings. **Superseded 2026-08-29** by RDO-17.5 / 17.6 (full conversion).

### RDO-17.5 — full-convert root-doc-organization/ (SHA `5508e41`)
Every `tasks.md` line collapsed to one canonical line with the 5-field tail (shipped lines keep their real SHA + `[x]`; `Owner` / `Model` / `Review` reconstructed from the inline notes +
`git show`). This `stories.md` rewritten to cover every task — forward spec for the open ones, this digest set for the shipped ones. `prompt.md` realigned to `_TEMPLATE/story/prompt.md`.
`plan.md` kept unchanged (D6). Also executes **RDO-17.7 §A** — see below. Both hooks `--all` clean of any `root-doc-organization/` finding afterward.

### RDO-17.7 §A — fill-to-≤200 markdown line style (SHA `7d28d16`, shipped inside RDO-17.5)
Retires RDO-5's "semantic linefeeds" guidance: prose now fills each line to the last word boundary before 200 chars; the `md-line-length` hook (200-char cap) stays the only gated rule.
Changed the *guidance* only — `docs/plan/README.md` §"Markdown line style", both `_TEMPLATE/` sets, `.claude/skills/md-organize/SKILL.md` + its `.agents/` mirror, and the one-line
`INSTRUCTION.md` description. Existing docs reflow opportunistically on next touch — no big-bang pass. §B (the legacy-folder conversion rule) stays open, Owner: Animesh.

---

## Perspectives not covered

- **Reconstruction fidelity of the shipped-task Review field.** `Review: code-reviewer` vs `none` was reconstructed from whether a task's diff touched `scripts/*.py`, not from a recorded
  review artifact — a task that *should* have had a review but didn't would be mislabeled `none` here and this pass would not catch it.
- **Whether `plan.md` should survive at all.** It is kept as a D6 extra file, but its Phase 1–7 structure now overlaps `stories.md` heavily; a future pass could fold its still-useful
  file-by-file inventory into `prompt.md` and drop it. Not evaluated here.
