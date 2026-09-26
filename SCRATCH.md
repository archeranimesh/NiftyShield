# SCRATCH.md — Guideline for `scratch/` scripts

`scratch/` holds quick POCs: throwaway scripts that prove or disprove an idea fast enough to inform a concrete design, before any production code gets written. They are not held to `src/` or
`scripts/dev/` discipline — no mandatory tests, no Decimal/type-hint enforcement, no requirement to reuse existing production formatting/client libraries. Optimize for speed of proving the point, not
for elegance.

This file exists because scratch/ accumulated ~50 scripts over a few months and two duplication patterns emerged. The rules below are the minimum needed to keep that convergence signal usable instead
of buried.

## Naming

Keep the existing convention: `YYYY-MM-DD_topic_purpose.py` (or `.md` for a question/handoff doc, `.sh` for a one-off shell probe). The date is load-bearing — it's how a future session tells "this
already answered that" from "this is stale."

## The convergence rule

A scratch script answers one of two kinds of question, and they graduate differently:

**"What does the data/API/plumbing look like?"** (a probe) — if you've written the *same* fetch/parse/connect boilerplate in 3 or more scratch scripts, that's proof the plumbing is stable enough to
stop re-deriving. Extract it into `scratch/_lib/` (see below) immediately — don't wait for a 4th rewrite.

**"What should this feature/message/logic look like?"** (a design POC) — if you've reproven the *same* design shape 2 or more times (e.g. five different Telegram alert formatters all rebuilding a
key-value table by hand), check `src/` first before writing a 6th. Two outcomes:
- A production module already solves it (e.g. `src/notifications/formatting.py` already has `build_kv_table`/`build_leg_table`/`escape_markdown`) → stop writing new scratch versions, just call the
  existing module. No promotion needed, nothing to build — the design question is already answered.
- No production module solves it → the convergence itself is the signal to stop proving and start building. Promote to `scripts/dev/<name>.py` (tested CLI) or `src/<module>/<name>.py` (tests, type
  hints, Decimal, Google-style docstrings — full CLAUDE.md discipline) per the normal Step 5 close-out. Do not leave the converged pattern sitting in scratch/ as a 6th near-duplicate.

Do not extract or promote preemptively on a single occurrence — that's speculative abstraction the project's simplicity-first rule (CLAUDE.md "Simplicity First") already forbids. Wait for the actual
2nd/3rd repeat.

## `scratch/_lib/` — abstracted plumbing, not production code

`scratch/_lib/` holds helpers extracted under the convergence rule above. Rules for anything placed here:

- Purpose is to stop re-deriving low-level plumbing (DB connections, HTTP session setup) inside new POCs — not to be a production dependency.
- No test file required, no Decimal enforcement — same relaxed bar as the rest of scratch/.
- Every file must open with a one-line docstring: `"""Scratch-only helper — not for src/ or scripts/dev/ import. Graduate (with tests) before reuse there."""` so nothing accidentally gets imported
  into production code straight from scratch/_lib/.
- When a `_lib/` helper itself gets reused by a 3rd *production-bound* script (i.e. one that's about to graduate per the rule above), that's the trigger to move the helper itself into `scripts/dev/`
  or `src/` alongside the graduating script — with tests, at that point.

## What never needs to change

Cleanup/verify/one-off DB-repair scripts (e.g. `overlay_full_cleanup.py`, `check_stale_flat_legs.py`) are correctly scoped as permanent scratch — each targets a different one-off data state and won't
converge into a reusable pattern. Leave this cluster alone. Note the separate boundary against `scripts/dev/`: bulk/sweep/migration logic that might re-run on other targets goes straight to
`scripts/dev/` as a tested CLI — it never passes through scratch/ first, convergence rule or not.
