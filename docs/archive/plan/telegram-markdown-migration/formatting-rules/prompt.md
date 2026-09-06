# Telegram Markdown Migration — Formatting Rules — prompt

> The canonical per-parameter-type formatting spec (`FORMATTING.md`) and the tested value / table-builder helpers in `src/notifications/formatting.py` that every `strategy-rollout/` message reuses.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The scratch prototypes built ad hoc formatters (`_kv_table`, `_side_by_side_kv`, `_leg_table`, money / Greek / strike / percent helpers) through several rounds of on-device feedback. Without a single
canonical spec and one tested implementation, every `strategy-rollout/` message would re-derive its own decimal precision, sign display, and column-width logic — which is exactly how the original
`build_comparison_report()` hand-counted-width bug (TGFMT-1) happened. FMT-1 writes the spec (root `FORMATTING.md`); FMT-2/FMT-3 promote the scratch helpers into `src/notifications/formatting.py` with
content-derived widths; FMT-1b–1f capture the emoji / header / summary-table rules that surfaced during later workshop sessions.

## Scope guard

`FORMATTING.md` (repo root) and `src/notifications/formatting.py` + its tests. This story defines and implements the reusable formatting layer — it does **not** migrate any actual message (that is
`strategy-rollout/`) and does **not** change the transport (that is `backbone/`). FMT-1b's and FMT-1c's *code* promotion happens in `strategy-rollout/` ROLL-1a / ROLL-1b, not here.

## Session-start load hints

- Root `FORMATTING.md` — FMT-1's output; §§ 3 / 4 / 7 / 8 / 10 / 11 carry the corrections and the audit of all 14 scratch-script formatters. Read it before touching any FMT-* task.
- `scratch/2026-08-07_ic_eod_audit_telegram_format.py` (final version) — working reference implementations of the table builders. Port and generalize; do not redesign.
- Epic `README.md` — the `backbone/` dependency (FMT-2/FMT-3 need `escape_markdown()` / `mdcode()` from `src/notifications/markdown.py`).
- No `schema.md` — this story changes no DB schema.

## Hard constraints

- **Depends on `backbone/` complete** — every table helper that interpolates a dynamic value needs the MD-1 escaping helpers. FMT-1 (the spec doc) has no code dependency and could start earlier.
- **Every column width is `max(len(...))`, never a hand-counted constant** — the `build_comparison_report()` bug this story exists to prevent.
- **Graph-before-Read** for any `src/` / `scripts/` file.
- **Test gate (blocking):** `python -m pytest tests/unit/ --tb=no -q` — all green before committing.
- **Test helpers:** `get_code_snippet('<ModelClassName>')` before writing any fixture that constructs a domain model.

## Task overview

One line per task id (detail in `stories.md`): FMT-1 formatting spec → `FORMATTING.md` · FMT-1f signed-money + spread labels · FMT-1b status-emoji spec · FMT-1c timeframe-header spec · FMT-1d
summary-table money exception · FMT-1e emoji-presentation-glyph rule · FMT-2 value formatters · FMT-3 table builders · FMT-4 docs close.

## Definition of done

Mirrors `tasks.md` §"Story done when". In short: `FORMATTING.md` is the canonical spec, `src/notifications/formatting.py` carries the value formatters and table builders with content-derived widths
and documented exceptions, and every FMT-1x rule is recorded in `FORMATTING.md`.

## Perspectives not covered

- **`FORMATTING.md` §4 / §7 unresolved conflicts.** FMT-1d's zero-as-`-` collides with `-` meaning "not applicable" elsewhere, and FMT-1e's ASCII-only-in-fences rule currently outlaws the `Δ` header
  ROLL-1 already ships. Both are flagged in `stories.md`'s header note to resolve at `strategy-rollout/` implementation time; whether they were actually resolved cleanly is not verified here.
- **Whether `build_compare_table` should have shipped in FMT-3.** It was left as a design reference and promoted much later in ROLL-2a — a formatting-layer addition riding inside a strategy-rollout
  commit, the exact shape FMT-3 was meant to prevent.
