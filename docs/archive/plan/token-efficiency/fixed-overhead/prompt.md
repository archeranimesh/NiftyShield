# Token Efficiency — Fixed Overhead — prompt

> Attack the token cost that is paid every turn or every session regardless of the task: the
> resident `CLAUDE.md`, the auto-injected module `CLAUDE.md` files, the `session-close`
> context clone, and the fingerprint bloat in MCP graph results.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find
the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in
`stories.md` (same task id) before writing any code. One task per session. Complete it fully.
Stop.

## Why this story exists

Per the epic `README.md`: every turn re-sends ~15–20K of tool schemas plus ~400 lines of
project `CLAUDE.md` plus the global `CLAUDE.md`, `MEMORY.md`, and any module `CLAUDE.md`
pulled in by a directory touch. Every task-shaped session then pays a `session-close` fork
that clones the whole conversation (~285K in the ROLL-7 session). And every
`get_code_snippet` / `search_graph` call carries ~500 tokens of `fp` / `sp` / `bt`
fingerprint fields the model cannot use.

This story removes the removable parts of that overhead without dropping a real protocol
gate.

## Scope guard

**In bounds:** `CLAUDE.md`, `AGENTS.md`, `src/*/CLAUDE.md`, `.claude/skills/session-close/`,
a new `.claude/skills/protocol-reference/` skill, and a thin MCP-result wrapper (location
decided in FIX-4's spec). Plus each task's tests and its As-built measured delta.

**Out of bounds:** the `suggestions.md` sweep and its Step 4b escalation logic — that is
`suggestions-sweep/`. FIX-3 changes **how** `session-close` runs; SWEEP-7 changes its Step 4b
content, and rebases onto FIX-3.

## Session-start load hints

- Epic `README.md` — the Baseline section (from `measurement/` MEAS-2) is the number every
  task here quotes its delta against. Read it.
- `docs/plan/full-repo-review/findings/FR-8_practitioner-devex.md` — the surface/model
  routing guide; FIX-1 must not contradict it when moving protocol text.
- `.claude/skills/session-close/SKILL.md` — read fully before FIX-3.
- Whichever module you trim in FIX-2: that module's current `CLAUDE.md` and its code, to
  judge what is genuinely load-bearing vs. reference detail.
- No `schema.md` — no DB work anywhere in this story.

## Hard constraints

- **Measured delta, every task.** The As-built in `stories.md` records a real before/after
  number from `token_audit.py` (`measurement/`). A resident-doc change reports the per-turn
  drop; FIX-3 reports a per-session drop from a before/after session pair; FIX-4 reports the
  per-call drop times a typical calls-per-session count. No hand-waves.
- **No gate dropped.** Anything moved out of the resident `CLAUDE.md` lands in the
  `protocol-reference` skill or a hook that still fires when it matters. The
  `check_story_structure.py` / `check_checkbox_consistency.py` / `commit`-skill gates and the
  `@code-reviewer` / `@greeks-analyst` / `@roll-validator` AutoTriggers stay enforced.
- **`AGENTS.md` stays a full standalone mirror of `CLAUDE.md`** (per the
  `agents-md-mirrors-claude-md` memory) — FIX-1 restructures both together, never leaves
  `AGENTS.md` as a stub.
- **Test gate (blocking):** `python -m pytest tests/unit/ --tb=no -q` — all green before
  committing. FIX-1 / FIX-2 / FIX-3 touch no `.py`; still run the gate to prove nothing
  imported a moved path.
- **Graph-before-Read** for any `src/` / `scripts/` file.

## Task overview

- `FIX-1` — skill-ify `CLAUDE.md`: reference tables + Council Decision Protocol + AI-collab
  prose → `.claude/skills/protocol-reference/SKILL.md`; resident file keeps the load-bearing
  protocol; mirror `AGENTS.md`.
- `FIX-2` — audit + trim the `src/*/CLAUDE.md` module files that auto-inject on a directory
  touch.
- `FIX-3` — `session-close` runs as a transcript-reading subagent, not a `fork`; As-built
  records the measured saving.
- `FIX-4` — strip `fp` / `sp` / `bt` fingerprint fields from `get_code_snippet` /
  `search_graph` results; file the upstream issue.

## Definition of done

Mirrors `tasks.md` "## Story done when". In short: the resident `CLAUDE.md` is under its
target line count with its reference material behind an on-demand skill and `AGENTS.md`
mirrored; the heaviest module `CLAUDE.md` files are trimmed; `session-close` no longer clones
context; MCP snippet results are fingerprint-free; and every task's As-built quotes its
measured token delta.

## Perspectives not covered

- **Whether the tool schemas themselves can shrink.** The ~15–20K of `Artifact` /
  deferred-tool machinery in the system prompt is harness-owned, not repo-owned — out of
  scope here; note it upstream if it dominates the Baseline.
- **Skill-load cost.** Moving text into `protocol-reference` trades a fixed per-turn cost for
  a one-time per-session load when the skill is invoked. FIX-1's measurement must confirm the
  trade is net positive for a typical session, not assume it.
