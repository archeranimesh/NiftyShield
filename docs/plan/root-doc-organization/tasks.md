# Root doc organization — tasks

Work top-down. Each phase = one commit. See `plan.md` for the file-by-file detail.
RDO-1 and RDO-2 are done. RDO-3 is closed as a partial (remainder → RDO-9); it is not a
blocker. RDO-4, 5, 7, 8, 11 are independent. RDO-6 comes last (encodes final state). RDO-8
was spun out of the RDO-2 audit and feeds RDO-5/RDO-6. RDO-9 replaces RDO-3's unworkable
date cutoff. RDO-10 reconciles RDO-7 with the freshness hooks a parallel epic shipped the
same day; RDO-11 decides whether those hooks become blocking.

**Open: RDO-4, 5, 6, 7, 8, 9, 10, 11.** Epic completion criteria at the bottom of this file.

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
- [ ] **RDO-4** — Move `BUGS.md` → `docs/archive/BUGS_LEGACY.md` (3-line stub at root);
  move `GLOSSARY.md` → `docs/GLOSSARY.md` (no stub, add `CLAUDE.md` Quick-reference row).
  Fix all inbound links.
- [ ] **RDO-5** — Add `scripts/hooks/check_root_md_line_length.py` + `.pre-commit-config.yaml`
  entry `root-md-line-length`. Verify: `pre-commit run root-md-line-length --all-files` green
  after RDO-1..4.
- [ ] **RDO-6** — Rename `.claude/skills/md-cleanup/` → `md-organize/`, rewrite `SKILL.md`:
  broaden triggers, fix the "must stay at root" table, add CONTEXT.md re-slim + DECISIONS
  roll + line-length + `CLAUDE.md` pointer-reconciliation steps. **Add (RDO-2):** an
  "AGENTS.md ← CLAUDE.md re-sync" step — diff the two protocol bodies and re-apply the
  Antigravity deltas whenever `CLAUDE.md` changed since the last sync.
- [ ] **RDO-7** — Add report-only `DOC STALENESS` section to
  `.claude/skills/session-close/SKILL.md` (Option A in `plan.md`). Report only — no
  unattended commits.
- [ ] **RDO-8** — Protocol-doc consistency cleanup (surfaced by the RDO-2 audit,
  2026-08-27). Independent of RDO-3..7; can be done in any order. Each bullet is a small
  targeted fix — one commit for the lot is fine since they are all protocol/doc consistency.
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
  Verify: `wc -l DECISIONS.md` ≤ 800; fresh full-file `Read` under the display cap.

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

## Epic done when

All boxes checked:
- [ ] **RDO-4** — `BUGS.md` / `GLOSSARY.md` relocated, all inbound links fixed.
- [ ] **RDO-5** — `root-md-line-length` pre-commit hook green on every root `.md`
      (`CONTEXT_TREE.md` long lines from RDO-1 cleared here).
- [ ] **RDO-6** — `md-organize` skill exists; "stay at root" table matches reality; includes
      CONTEXT re-slim / DECISIONS roll / line-length / `CLAUDE.md` pointer-reconcile /
      `AGENTS.md` ↔ `CLAUDE.md` re-sync steps.
- [ ] **RDO-7** — session-close `DOC STALENESS` report added, or explicitly dropped as
      redundant per RDO-10 #1.
- [ ] **RDO-8** — all 5 protocol-doc consistency fixes landed.
- [ ] **RDO-9** — `DECISIONS.md` ≤ 800 lines; work-log entries split to
      `docs/archive/DECISIONS_worklog_2026.md`; 9a STILL-ENFORCED list signed off by Animesh.
- [ ] **RDO-10** — both hooks in `plan.md` inventory + RDO-6 re-sync scope; `#4` resolved;
      final skill name picked.
- [ ] **RDO-11** — hook enforcement decision made and recorded in `DECISIONS.md`.
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
