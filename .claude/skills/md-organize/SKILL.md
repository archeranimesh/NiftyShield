# NiftyShield — Root Markdown Organize Skill

> Invoke to organize the repo's markdown: archive completed work, relocate one-off plans,
> reflow prose to the house style, and reconcile the protocol docs against reality — so that
> only current, cheaply-loadable context lives at root.
>
> **Trigger phrases:** "organize the markdown", "optimize the docs", "clean up the markdown",
> "do a markdown cleanup", "archive completed TODOs", "md-organize".

---

## What This Skill Does

Keeps the project root to markdown that carries _live, session-relevant context_. Completed
work, one-off plans, and reusable tool prompts get archived or moved — nothing useful is
deleted, only relocated with a pointer stub where another doc links to it. It also enforces
the line-style convention (prose filled to ≤200 chars per line) and keeps `CLAUDE.md` /
`AGENTS.md` / `.agents/` / `.claude/skills/work/` in sync.

This is an on-demand maintenance pass, not a per-session step. Folders and root docs churn
only ~monthly; run it when the drift has accumulated or when a large doc change just landed.

---

## Step 1 — Survey root markdown files

Run: `ls *.md`

**Files that must stay at root (never archive):**

| File | Why it must stay |
|---|---|
| `CLAUDE.md` | Auto-loaded project protocol — canonical |
| `AGENTS.md` | Antigravity's autoload protocol — standalone mirror of `CLAUDE.md` |
| `CONTEXT.md` | Authoritative codebase state — read every session |
| `CONTEXT_TREE.md` | File-level module tree — referenced by `CONTEXT.md` |
| `DECISIONS.md` | Still-enforced rules + archive index — read on structural changes |
| `README.md` | Public-facing project overview |
| `MISSION.md` | Immutable mission + grounding principles |
| `PLANNER.md` | Multi-sprint roadmap — read at feature start |
| `TODOS.md` | Feature Backlog + Open Bugs pointers + session log — read every session |
| `REFERENCES.md` | Instrument keys, AMFI codes, API quirks |
| `DB_REGISTRY.md` | SQLite table registry — read before any DB write |
| `BACKTEST_PLAN.md` | Phase 0 backtest → paper → live plan |
| `BACKTEST_PLAN_PHASE1.md` | Phase 1+ plan (load only after the Phase 0.8 gate) |
| `LITERATURE.md` | Concept reference (LIT-XX codes) for analytics/ML phases |
| `REVIEW.md` | Python review checklist — loaded by the `code-reviewer` agent |
| `LOGGING.md` | Canonical logging standard (line shape, event naming, entrypoint rule) |
| `FORMATTING.md` | Canonical Telegram value/table formatting standard |
| `INSTRUCTION.md` | Session workflow guide for the human operator |
| `suggestions.md` | Cross-session efficiency tally — owned by `session-close` Step 4b |

Anything else at root is a candidate to move:

- `*-plan.md` / `*-implementation-plan.md` whose phase is complete → `docs/archive/`
- `*.prompt.md` or reusable tool prompts at root → `docs/`
- task-specific `.claude/agents/*.md` whose task is done → `docs/archive/`

---

## Step 2 — Archive completed TODOs + session log

`TODOS.md` is two pointer-only lists (`## Feature Backlog`, `## Open Bugs`) plus a
`## Session Log`. Per `docs/plan/README.md` §Conventions:

- A fully-done story/bug has its `TODOS.md` line **deleted** (moved to
  `docs/archive/TODOS_ARCHIVE.md`), its folder moved to `docs/archive/plan/<slug>/`, and its
  `docs/plan/README.md` row collapsed to a pointer — all in the completion commit. If Step 5b
  below finds a done-but-not-archived story, do that move here.
- Session-log entries older than the current session move to
  `docs/archive/TODOS_ARCHIVE.md` (append; keep newest-first within a date).
- Backlog items must stay pointer-only: title, `docs/plan/<slug>/` or `docs/bugs/` path, next
  unchecked task id, one line of why. Multi-paragraph detail or per-task progress in an item
  is a hygiene violation — push it into the story's own `tasks.md`.

Archive header, if `docs/archive/TODOS_ARCHIVE.md` does not exist:

```markdown
# NiftyShield — Completed Work Archive

> Completed TODO items and historical session log. Active open work lives in
> [TODOS.md](../../TODOS.md).
```

---

## Step 3 — Re-slim CONTEXT.md if it regressed

Targeted `Edit` only — never `Write` on `CONTEXT.md`.

1. **Length + line-length check:**
   `wc -l CONTEXT.md` (target ≤ 400) and
   `awk '{print length}' CONTEXT.md | sort -rn | head -1` (must be ≤ 200).
   If either is breached, re-slim: move regrown module prose into the matching
   `CONTEXT_TREE.md` entry, cut the "What Exists" section back to one line per package.
2. **Date header** — `## Current State (as of YYYY-MM-DD)` → today.
3. **"What Does NOT Exist Yet"** — verify each entry with `ls src/<module>/`; drop any module
   that now exists.
4. **Live Data / Test Coverage** — update only on direct evidence (seed ran, DB wiped, a
   fresh `pytest` count).

---

## Step 4 — Roll DECISIONS.md + refresh its index

`DECISIONS.md` root holds **still-enforced rules + the archive index only** (RDO-9 semantic
split). Completed-work-log entries ("fixed X, why") live in
`docs/archive/DECISIONS_worklog_2026.md`.

1. Scan root `DECISIONS.md` for any entry that has become a pure historical record (the
   change landed, nothing enforces it going forward) — move it to the worklog archive, same
   header, newest-first within its section.
2. Roll any archive entry older than ~6 months into the current-year archive file if a new
   year has started; refresh the one-line topic index in root.
3. `pre-commit run md-line-length --files DECISIONS.md` must stay green — wrap any surviving
   rule entry to fill-to-≤200.

---

## Step 5 — Update README.md

**Project Structure block:** every real directory in `src/` and `scripts/` appears;
planned-but-empty modules read `[empty — planned QN YYYY]`; no entries for dirs that don't
exist.

**Roadmap checkboxes:** `[x]` for shipped, `[ ]` for planned, priority label in parens on the
top open item.

---

## Step 5a — Enforce the markdown line style repo-wide

The convention (`docs/plan/README.md` §Conventions → "Markdown line style", RDO-5):

- Prose fills each line to the last word boundary before 200 chars — do not break early at
  a sentence or clause, and do not hand-wrap to a fixed narrow width. (The earlier
  "semantic linefeeds" one-clause-per-line style is retired — RDO-17.7 §A.)
- The hard **200-char ceiling** on every line kind (prose, table rows, fenced code) is the
  only gated rule, enforced by the `md-line-length` pre-commit hook over root `.md` +
  `docs/plan/**` + `docs/bugs/**`.
- `<!-- lint-ignore-length -->` on the immediately-preceding line excuses one unbreakable
  token (a long URL, a base64 blob).

Run `pre-commit run md-line-length --all-files` and clear every reported line:

- Prose → rewrap so each line fills to just under 200 chars.
- Long table rows → shorten cells, or lift a long parenthetical into a sentence below the
  table. Never drop a column or a fact.
- Fenced code → shorten, or mark with `<!-- lint-ignore-length -->`.

`DECISIONS.md` is Step 4's responsibility, not this sweep's. `suggestions.md` is exempt —
it is a wide fixed-column table owned by `session-close` Step 4b; commit it with
`SKIP=md-line-length` and do not reflow its rows.

**Secrets baseline:** a large reflow shifts line numbers, so `detect-secrets` will flag
`.secrets.baseline` line-number drift on the next commit. Refresh it in the same commit:
`detect-secrets scan --baseline .secrets.baseline` (see `chore(root): update secrets
baseline` precedents in the log).

---

## Step 5b — `docs/plan/` structure audit

Run: `python scripts/dev/hooks/check_story_structure.py --all`

Every non-archived `docs/plan/*/` folder must be a flat story (`prompt.md` + `tasks.md` +
`stories.md`, plus `schema.md` iff it touches the DB) or an epic root (`prompt.md` router +
`README.md`, one story sub-folder each). Legacy shapes are grandfathered — the hook warns,
does not block. Act on what it reports:

- **empty folder** — the story shipped and was archived; `rmdir` it.
- **legacy `*_tasks.md`** — rename to bare `tasks.md` only when you are already touching that
  story (do not mass-rename).
- **missing files** — the folder is a stub; flesh it out from `docs/plan/_TEMPLATE/` or
  remove it.

Then check for any story/bug with every `tasks.md` box ticked that was **not** archived — if
found, do the *Completion → archive* move (folder → `docs/archive/plan/`, `TODOS.md` line →
`TODOS_ARCHIVE.md`, README row → pointer). Full rules: `docs/plan/README.md` §Conventions.

---

## Step 5c — Checkbox-consistency sweep

Run: `python scripts/dev/hooks/check_checkbox_consistency.py --all`

Every task id carries exactly one checkbox (the working-list line); `## Epic done when`
blocks are prose acceptance criteria with no `- [ ]` (RDO-15 convention a). Fix each reported
file — strip a stray summary-block checkbox, reconcile a drifted id to the working-list
state, or repoint a stale README `next:` marker. Full rule: `docs/plan/README.md`
§"Checkbox consistency".

---

## Step 5d — Reconcile CLAUDE.md conditional-load pointers

Every `also read <X>` / "load `<X>` when …" line in `CLAUDE.md` (Rule 0 decision tree, Step 1
conditional-load list, Quick reference table, module `CLAUDE.md` table) must name a file that
exists. `grep -oE '[A-Za-z_/.]+\.md' CLAUDE.md | sort -u | while read f; do [ -e "$f" ] ||
echo "missing: $f"; done`. Fix a stale path, drop a pointer to a deleted doc, add a pointer
for a new always-relevant one.

---

## Step 5e — Verify the doc-freshness hooks (RDO-10)

The two hooks carry **hard-coded** state-doc lists that must stay aligned with `CLAUDE.md`
§Step 5a:

- `.claude/hooks/state_doc_freshness.sh` — per-doc staleness thresholds (SessionStart).
- `.claude/hooks/doc_update_gate.sh` — the "`.py` commit with no state-doc change" reminder
  (`PreToolUse` on `git commit`).

Diff each hook's doc list against `CLAUDE.md` §Step 5a. **Flag any drift — do not auto-edit
the hooks.** Threshold tuning and the advisory→blocking decision are RDO-11's call, not this
skill's.

---

## Step 6 — Commit

```
docs(root): organize markdown — archive done items, reflow, reconcile pointers

Why: completed items accumulating; line-style drift; CLAUDE.md pointers stale.
What:
- TODOS.md: archive done stories/session-log entries → docs/archive/
- docs/archive/…: relocated items
- CONTEXT.md / DECISIONS.md / README.md: re-slim, roll, sync as needed
- <files>: fill-to-≤200 reflow to clear md-line-length
- .secrets.baseline: line-number refresh
Ref: none
```

Docs/config-only → skip `code-reviewer`. Run `pre-commit run --all-files` before committing.

---

## Step 7 — Re-sync the protocol mirrors (only if CLAUDE.md changed this run)

`CLAUDE.md` is canonical. Three copies must not drift from it:

1. **`AGENTS.md`** — Antigravity's autoload protocol, a full standalone mirror. Re-apply each
   `CLAUDE.md` edit to the matching passage. Preserve the intentional deltas: the
   "Antigravity autoload / deltas" header block, every `Edit` → `multi_replace_file_content`
   / `write_to_file` substitution, and the "emit the await-signal instead of spawning
   `@agent`" wording. Confirm only those deltas differ:
   `diff <(sed 's/[[:space:]]*$//' CLAUDE.md) <(sed 's/[[:space:]]*$//' AGENTS.md)`.
2. **`.agents/skills/`** — a mirror of `.claude/skills/` that Antigravity autoloads. Keep the
   skill set and body text in sync with `.claude/skills/`; all paths point at `.claude/`
   (no `.Codex/` / "Codex" identity language — that scaffolding is dead, RDO-8).
3. **`.claude/skills/work/SKILL.md`** — its Feature/Bug routing text duplicates `CLAUDE.md`
   Step 1; keep the two aligned (RDO-12).

Fold every mirror change into the same Step 6 commit.

---

## Quick Checklist

- [ ] `TODOS.md` backlog items are pointer-only; done stories archived; session log trimmed
- [ ] `docs/archive/TODOS_ARCHIVE.md` holds everything removed
- [ ] `CONTEXT.md` ≤ 400 lines, longest line ≤ 200, date header today
- [ ] `DECISIONS.md` root = rules + index only; `md-line-length` green
- [ ] `README.md` structure + roadmap match `src/` / `scripts/`
- [ ] `pre-commit run md-line-length --all-files` green (or every long line ignore-marked)
- [ ] `check_story_structure.py --all` and `check_checkbox_consistency.py --all` clean
- [ ] every `CLAUDE.md` `also read` pointer resolves
- [ ] freshness-hook doc lists checked against `CLAUDE.md` §Step 5a (drift flagged, not edited)
- [ ] if `CLAUDE.md` changed: `AGENTS.md` + `.agents/skills/` + `work/SKILL.md` re-synced
- [ ] commit made in project format; `.secrets.baseline` refreshed if lines shifted
