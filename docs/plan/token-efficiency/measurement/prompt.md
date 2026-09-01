# Token Efficiency — Measurement — prompt

> Build the tool that attributes a session's token cost by bucket, and establish the baseline
> every later task in this epic measures its saving against.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find
the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in
`stories.md` (same task id) before writing any code. One task per session. Complete it fully.
Stop.

## Why this story exists

The 2026-09-01 ROLL-7 token audit was done by hand — reading subagent completion
notifications for their `subagent_tokens` figures, watching the `<total_tokens>` counter
drift, and estimating the rest. That is not repeatable, and the epic's cross-cutting
constraint (every fix quotes a real before/after number) needs a tool, not an estimate.

This story delivers `scripts/dev/token_audit.py` and a written baseline. Nothing else in the
epic can be measured until it exists, which is why it is story 1 and blocks the other two.

## Scope guard

**In bounds:** `scripts/dev/token_audit.py` (new), its test file, and the `README.md`
Baseline section (epic root). Read-only against session transcript JSONL files — the tool
parses them, never writes them.

**Out of bounds:** any change to `CLAUDE.md`, skills, hooks, or `src/`. This story only
measures; `fixed-overhead/` and `suggestions-sweep/` act on what it finds.

## Session-start load hints

- `LOGGING.md` — the tool is a new entrypoint script under `scripts/`; the
  `_SCRIPT_NAME = "scripts.dev.token_audit"` explicit-logger-name rule applies (pre-commit
  hook `no-script-main-logger` enforces it).
- The repo's transcript location: session JSONL lives under the Claude Code project state
  directory. `stories.md` MEAS-1 names how to locate a transcript path; confirm the actual
  shape by opening one before writing the parser.
- No `schema.md` — no DB work.

## Task overview

- `MEAS-1` — `scripts/dev/token_audit.py`: parse a transcript JSONL, attribute tokens to
  buckets, print a compact table + a machine-readable `--json` mode.
- `MEAS-2` — run it on 4–5 recent real sessions; write the epic `README.md` Baseline section
  with the numbers and the two or three largest line items.

## Definition of done

`token_audit.py` takes a transcript path (or a session id it can resolve) and reports tokens
by bucket — system prompt, `CLAUDE.md` + `AGENTS.md` + `MEMORY.md`, tool results grouped by
tool name, subagent report payloads, and subagent-internal usage lifted from task-completion
records — as a compact table and as `--json`. The epic `README.md` carries a Baseline
section: per-bucket numbers from 4–5 recent sessions and a one-line call-out of the biggest
avoidable items. Every public function has a happy-path and an edge/error test; no network,
no real session required at test time (fixture transcript).

## Perspectives not covered

- **Cost vs. wall-clock.** The tool measures tokens only. Whether a change that saves tokens
  also saves or costs latency (e.g. an extra subagent round-trip) is not modelled here — a
  reviewer weighing a fix should consider it separately.
- **Cross-model token accounting.** Subagents run on different models (Haiku test-runner,
  Opus code-reviewer). The tool reports raw token counts, not cost-weighted-by-model figures;
  if pricing weight matters for a decision, that is a follow-up.
