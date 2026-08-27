**Root markdown organization — token-efficiency cleanup + maintenance automation.**

Read this file, then `plan.md` (file-by-file changes), then work `tasks.md` top-down.

## Why this story exists

22 markdown files at repo root (~1.05 MB / ~260K tokens total). The conditional-loading
table in `CLAUDE.md` already keeps most of them out of the default session context — that
part works. The problems are narrower:

1. **`CONTEXT.md` is read every session and is ~20K tokens** with pathological single lines
   (line 27 = 18,740 chars). `suggestions.md` row `context-md-full-sequential-read` already
   records that one unscoped `Read` blows the 25K display cap at line 31 of 156.
2. **`AGENTS.md` (409 lines) is a drifted near-duplicate of `CLAUDE.md` (351 lines)** — same
   Rule 0 / Rule 1 / Step 1–5 / Council structure, plus an appended "Imported Claude Cowork
   project instructions" block. Two sources of truth for the same protocol.
3. **`DECISIONS.md` is 336 KB / 2,302 lines** — only loads on structural changes, but when it
   does it is a brick with no index.
4. **No line-length guard** — nothing stops the next long-line regression in any root doc.
5. **No routine keeps the docs current** against the day's commits.

## Scope guard

This is a **docs + tooling** story. No `src/` or `scripts/` behavior changes. The only code
touched is a new pre-commit hook entry and (optionally) a new skill / fork-agent definition
under `.claude/`.

## Working rules

- Every doc edit is a targeted `Edit`, never `Write` on an existing root doc (except files
  being newly created under `docs/archive/`).
- Nothing is deleted. Content that leaves root is relocated to `docs/` or `docs/archive/`
  with a one-line pointer stub left behind where another doc links to it.
- Commit per phase boundary in `plan.md` (§Phasing), format from
  `.claude/skills/commit/SKILL.md`. Docs-only commits skip `code-reviewer`; the pre-commit
  hook phase touches `.pre-commit-config.yaml` + a hook script — still docs-tooling, no
  `code-reviewer`, but run the hook against all root `.md` before committing.
- After each phase: update `docs/plan/README.md` status column for this story.

## Definition of done

- `CONTEXT.md` ≤ 400 lines, no line > 200 chars, session-start cost ≈ 6K tokens.
- `AGENTS.md` is a thin pointer to `CLAUDE.md` (or deleted if no non-Claude tool needs it —
  confirm with Animesh first).
- `DECISIONS.md` root copy holds only decisions from the trailing 6 months + an index;
  older content in `docs/archive/DECISIONS_ARCHIVE_2026H1.md`.
- Pre-commit hook `root-md-line-length` fails any staged root `.md` with a line > 200 chars.
- `md-organize` skill exists and its "must stay at root" table matches reality.
- Either the session-close fork or a dedicated `doc-sync` fork reports doc staleness against
  `git log` for the session. Report-only — no unattended commits.
