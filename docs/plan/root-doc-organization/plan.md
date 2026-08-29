# Root doc organization — file-by-file plan

Current root inventory (2026-08-27), largest first by bytes:

| File | Bytes | Lines | Loaded when | Action |
|---|---|---|---|---|
| `DECISIONS.md` | 330K | 2,203 | structural changes | RDO-3 partial done (7bbfaff); real shrink = **RDO-9 semantic split** |
| `CONTEXT.md` | 10K | 159 | **every session** | RDO-1 done (fd1bd0b) — was 81K/156 |
| `CONTEXT_TREE.md` | 42K | 296 | new modules / survey | Receives module prose from CONTEXT.md |
| `README.md` | 34K | 744 | public overview | Trim overlap with MISSION.md |
| `LITERATURE.md` | 35K | 512 | analytics/ML phases | Keep as-is (well-scoped) |
| `BACKTEST_PLAN_PHASE1.md` | 79K | 968 | Phase 1+ only | Keep; wrap long lines |
| `REVIEW.md` | 25K | 792 | code-reviewer agent | Keep as-is |
| `AGENTS.md` | 21K | 409 | non-Claude tools | **Collapse to pointer / delete** |
| `FORMATTING.md` | 23K | 366 | Telegram formatting | Keep; wrap long lines |
| `INSTRUCTION.md` | 14K | 425 | human operator | Trim agent/skill lists (dup of `.claude/`) |
| `CLAUDE.md` | 22K | 351 | **every session** | Canonical protocol — AGENTS.md points here |
| `LOGGING.md` | 14K | 286 | logging work | Keep as-is |
| `PLANNER.md` | 16K | 203 | feature start | Keep as-is |
| `GLOSSARY.md` | 11K | 194 | rarely | Move to `docs/`, add CLAUDE.md pointer |
| `MISSION.md` | 4K | 92 | rarely | Keep at root (cheap, load-bearing values) |
| `BACKTEST_PLAN.md` | 15K | 225 | Phase 0 work | Keep as-is |
| `DB_REGISTRY.md` | 9K | 70 | DB writes | Keep as-is |
| `REFERENCES.md` | 8K | 130 | instrument keys | Keep as-is |
| `TODOS.md` | — | 83 | every session | Keep; session-close already maintains |
| `BUGS.md` | 3K | 69 | never (legacy) | **Move to `docs/archive/`, stub** |
| `suggestions.md` | — | 12 | session-close only | Keep; skill-owned |

---

## Phase 1 — CONTEXT.md slim (highest value, ~14K tokens/session saved)

**Problem:** the "What Exists (committed and working)" section (lines 12–75) is written as
~15 run-on bullets, each a full paragraph on one logical line. Line 27 is 18,740 chars. This
duplicates the stated purpose of `CONTEXT_TREE.md` ("Module tree — file-level descriptions").

**Changes:**

1. `CONTEXT_TREE.md` — for each module bullet currently in `CONTEXT.md` "What Exists", merge
   any detail not already present into the matching `CONTEXT_TREE.md` entry. This is the new
   home for "what each module does". (Line style: semantic linefeeds, 200-char backstop — see
   RDO-5 and `docs/plan/README.md` §Conventions.)
2. `CONTEXT.md` "What Exists" — replace the prose bullets with a flat one-line-per-module
   list: `` `src/strategy/` — paper-backbone strategy layer → CONTEXT_TREE.md`` . Target the
   whole section ≤ 25 lines.
3. `CONTEXT.md` — keep these sections at root, trim each to essentials:
   - `## Current State (as of DATE)` — date + 3–4 line status paragraph
   - `## What Does NOT Exist Yet` — bullet list, one line each
   - `## Live Data` — table, current
   - `## Current Constraints` — keep (load-bearing)
   - `## Key Decisions` — keep as pointers to DECISIONS.md rows, not restatements
   - `## Immediate TODOs` — 5-line max, points to TODOS.md
   - `## Strategy Definitions` — one line each + pointer to `src/portfolio/strategies/`
   - `## Test Coverage` — count + last-green date only
   - `## Session Log` — last 5 entries, pointer to archive
4. Hard-wrap every remaining line in `CONTEXT.md` to ≤ 200 chars.

**Verify:** `wc -l CONTEXT.md` ≤ 400; `awk '{print length}' CONTEXT.md | sort -rn | head -1`
≤ 200; a fresh `Read CONTEXT.md` returns the whole file without hitting the display cap.

**Commit:** `docs(context): slim CONTEXT.md to always-load core, move module prose to tree`

---

## Phase 2 — AGENTS.md / CLAUDE.md dedup

`AGENTS.md` header structure is `CLAUDE.md` + an appended "Imported Claude Cowork project
instructions" block (Project Overview / Async Model / Data Layer / BrokerClient / … /
Environment Variables). The two protocol halves have already drifted (`CLAUDE.md` has a
"Logging standard (scripts/)" section `AGENTS.md` lacks; section titles differ).

**Decision needed from Animesh:** does any non-Claude tool (opencode, Cursor, Aider, …) read
`AGENTS.md` in this repo? 
- **If no:** delete `AGENTS.md`; move the unique "Imported Claude Cowork" appendix content
  that isn't already in `CLAUDE.md` or a module `CLAUDE.md` into `DECISIONS.md` or the
  relevant module doc.
- **If yes:** replace `AGENTS.md` body with a 5-line pointer: "Protocol is defined in
  `CLAUDE.md`. This file exists only for tools that look for `AGENTS.md` by name and is a
  verbatim pointer — do not add content here." Add a pre-commit check that `AGENTS.md`
  stays under 20 lines.

**Commit:** `docs(protocol): collapse AGENTS.md into CLAUDE.md pointer` (or `remove AGENTS.md`)

---

## Phase 3 — DECISIONS.md archive + index

> **Revised 2026-08-27.** The date-cutoff below is unworkable: `DECISIONS.md` has no entry
> older than 2026-04-01, it is grouped thematically rather than chronologically, and
> 2026-04/05 and 2026-06/07/08 entries are interleaved inside several sections. A partial
> lift of 5 fully-historical self-contained sections landed as `7bbfaff`
> (`docs/archive/DECISIONS_pre-2026-07.md`). The real shrink is a **semantic split** —
> see **RDO-9** in `tasks.md`. Steps 1–4 here are kept only as the record of the abandoned
> approach.

1. ~~Create `docs/archive/DECISIONS_ARCHIVE_2026H1.md` with the standard archive header.~~
2. ~~Move every decision entry dated before 2026-06-01 into it, preserving order.~~
3. ~~`DECISIONS.md` root — add a `## Index` table at the top.~~
4. ~~Target root `DECISIONS.md` ≤ 800 lines.~~ (target carried forward to RDO-9)

**Commit:** ~~`docs(decisions): archive pre-2026H2 entries, add date index`~~ (done: `7bbfaff`)

---

## Phase 4 — Relocations + stubs

| Move | To | Stub left at root? |
|---|---|---|
| `BUGS.md` | `docs/archive/BUGS_LEGACY.md` | Yes — 3 lines pointing to `docs/bugs/` |
| `GLOSSARY.md` | `docs/GLOSSARY.md` | No — add pointer row to `CLAUDE.md` Quick reference |

Update inbound links: `grep -rn 'BUGS.md\|GLOSSARY.md' *.md docs/ .claude/` and fix each.

**Commit:** `docs(root): relocate legacy BUGS.md and GLOSSARY.md out of root`

---

## Phase 5 — Line-length pre-commit hook

Add to `.pre-commit-config.yaml`:

```yaml
- id: md-line-length
  name: "markdown lines must be <=200 chars (root + docs/plan + docs/bugs)"
  entry: python scripts/hooks/check_md_line_length.py
  language: system
  files: '^([^/]+\.md|docs/(plan|bugs)/.*\.md)$'
  pass_filenames: true
```

`scripts/hooks/check_md_line_length.py` — for each passed file, fail if any line > 200 chars,
print `file:line: NNN chars`. Skip fenced code blocks and table rows? No — table rows are the
main offender; keep them short instead. Allow an inline `<!-- lint-ignore-length -->` on the
preceding line for the rare legit case (a base64 blob, a long URL).

**Verify:** `pre-commit run md-line-length --files <a clean .md>` passes and `--files <a
long .md>` fails. Full `--all-files` green is not an RDO-5 gate — the ~800-line pre-existing
backlog is cleared opportunistically (the hook fires on any file a later commit touches) and
in batch by RDO-6's `md-organize` skill + RDO-9's `DECISIONS.md` split.

**Commit:** `chore(hooks): add md-line-length pre-commit guard`

---

## Phase 6 — `md-organize` skill (on-demand maintenance) — ✅ done 2026-08-29 (RDO-6, `3eb3834`)

Rename `.claude/skills/md-cleanup/` → `.claude/skills/md-organize/` and rewrite `SKILL.md`:

- **Trigger phrases:** "organize the markdown", "optimize the docs", "clean up the markdown",
  "do a markdown cleanup", "archive completed TODOs".
- **Fix the stale "must stay at root" table** — current version lists 12 files; real list
  after this story is: `CLAUDE.md`, `AGENTS.md` (stub), `CONTEXT.md`, `CONTEXT_TREE.md`,
  `DECISIONS.md`, `README.md`, `MISSION.md`, `PLANNER.md`, `TODOS.md`, `REFERENCES.md`,
  `DB_REGISTRY.md`, `BACKTEST_PLAN.md`, `BACKTEST_PLAN_PHASE1.md`, `LITERATURE.md`,
  `REVIEW.md`, `LOGGING.md`, `FORMATTING.md`, `INSTRUCTION.md`, `suggestions.md`.
- **Add steps:** (a) CONTEXT.md line-length + length check and re-slim if regressed;
  (b) DECISIONS.md — roll any entry older than 6 months into the current-year archive,
  refresh the index; (c) run `pre-commit run md-line-length --all-files` and clear any
  reported backlog (semantic-linefeed reflow for prose, restructure long table rows);
  (d) reconcile every `also read X.md` line in `CLAUDE.md` against files that actually exist.
- Keep existing TODOS.md / CONTEXT.md date / README structure steps.

**Commit:** `chore(skills): replace md-cleanup with md-organize, fix root-file table`

---

## Phase 7 — Daily staleness report (report-only automation) — ✅ done 2026-08-29 (RDO-7, `d24f15d`)

> **Revised 2026-08-28 (RDO-10).** A parallel epic shipped two doc-freshness mechanisms on
> 2026-08-27, before this phase was built:
> - `758dd6b` — `.claude/hooks/state_doc_freshness.sh` (`SessionStart`): per-state-doc flag
>   when `src/`|`scripts/` commits since the doc's last change exceed a per-doc threshold.
>   Informational, always `exit 0`. Thresholds tuned in RDO-10 #5
>   (`CONTEXT_TREE.md` / `DB_REGISTRY.md` / `README.md` → 60).
> - `7dae8e3` — `.claude/hooks/doc_update_gate.sh` (`PreToolUse`/`Bash` on `git commit`):
>   stderr reminder when a `.py` commit under `src/`|`scripts/` stages no Step-5a state doc.
>   Advisory (`exit 0`); RDO-11 decides whether it flips to `exit 2`.
>
> These two own the per-file "docs behind code" signal. **Option A below is therefore
> narrowed** (RDO-7): the session-close report covers only the *content gaps* neither hook
> can see — see RDO-7 in `tasks.md`. The nightly-cron idea (`TODOS.md #4`) is narrowed to a
> future *read-only* Telegram staleness digest, out of scope for this epic.

The user's ask was "a sub-agent that keeps these docs latest after each day of work."
A subagent cannot self-schedule. Two safe hooks:

**Option A (recommended) — extend session-close.** `CLAUDE.md` Step 5d already spawns a
`fork` at end of session. Add a `doc-sync` section to `.claude/skills/session-close/SKILL.md`:

- `git log --oneline --since="00:00"` (or since last session-close marker)
- For each file touched today under `src/` / `scripts/`, check whether `CONTEXT.md`,
  `CONTEXT_TREE.md`, `TODOS.md`, or `docs/plan/README.md` was also modified in the same
  window.
- Emit a `DOC STALENESS` block in the session-close report: "src/foo/bar.py changed 3× today,
  no CONTEXT_TREE.md entry updated" — **report only**, the operator decides.

**Option B — dedicated `doc-sync` fork agent.** New `.claude/agents/doc-sync.md` (Haiku),
spawned by session-close Step 5d alongside the efficiency audit. Same logic as Option A,
isolated context. Slightly more moving parts; pick this only if the session-close report is
already crowded.

**Not doing:** a nightly cron cloud agent that edits + commits docs unattended. Unattended
writes to source-of-truth docs is the wrong risk trade. A nightly *read-only* Telegram
staleness digest is the sanctioned form of `TODOS.md #4` (RDO-10 #3) — acceptable as a
post-epic add-on, not built here.

**Commit:** `chore(session-close): add report-only doc staleness check`

---

## Phasing / commit boundaries

Phases 1–7 each get their own commit. 1, 3, 4, 5 are independent and can be done in any
order or parallel. Phase 2 is blocked on the Animesh decision (delete vs stub AGENTS.md).
Phase 6 should come after 1–5 land so the skill encodes the final state. Phase 7 is
independent.

## Estimated token impact

| | Before | After |
|---|---|---|
| Every-session load (CLAUDE.md + CONTEXT.md) | ~25K tok | ~11K tok |
| DECISIONS.md when pulled | ~84K tok | ~20K tok + archive on demand |
| Risk of partial-read cap break on CONTEXT.md | high | none |

## Perspectives not covered

- **Merge conflict cost during the transition** — Phases 1 and 3 rewrite large sections of
  files that Antigravity and other sessions edit frequently (`CONTEXT.md`, `DECISIONS.md`).
  Land them on a quiet day, in one sitting, and warn any parallel session. Not analyzed:
  whether to freeze doc edits repo-wide during the cutover.
- **Whether `INSTRUCTION.md` should exist at all** — it is human-facing and overlaps
  `CLAUDE.md` + `.claude/` definitions heavily. This plan only trims it; a case could be
  made to fold it into `README.md`. Deferred.
