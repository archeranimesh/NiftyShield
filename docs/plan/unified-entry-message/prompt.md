# Unified entry message — prompt

> One shared lean entry-confirmation renderer for every paper strategy; IC migrated onto it,
> CSP given an entry Telegram card it currently lacks.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else.
Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task.
Read that task's full spec in `stories.md` (same task id) before writing any code.
One task per session. Complete it fully. Stop.

## Why this story exists

Only IC has a structured entry card. `src/notifications/ic_entry_message.py` (`ICEntryMessage` +
`format_ic_entry_message`, shipped ROLL-17 `26527c2`) renders a lean fenced-table confirmation, called
from `scripts/strategies/ic/paper_ic_entry.py` and `paper_ic_entry_v2.py`. CSP, the three overlays, and
the track-comparison strategy each build entry text ad-hoc — and CSP has no entry notification at all:
CSP entries go through the generic `scripts/record/record_paper_trade.py`, which only prints to stdout.

The IC renderer already decomposes into parts common to every credit structure — headline, one-line kv
row, fenced `build_leg_table()`, net-credit line — differing across strategies only in leg count (1 for
CSP, 4 for IC), which is data, not layout. Animesh asked (2026-09-10) to make entry messages uniform.

Scoped to IC + CSP only. The overlays and track-comparison are a deliberate follow-up once the shared
renderer has two real consumers. Format stays lean (no mark / capture / ROI / margin lines — those are
meaningless at entry and belong to the EOD-audit path). CSP's card is emitted from the shared recorder
behind a flag rather than a new wrapper script — decided with Animesh 2026-09-10.

## Scope guard

**In bounds:** `src/notifications/ic_entry_message.py` (renamed to `entry_message.py`),
`scripts/strategies/ic/paper_ic_entry.py`, `scripts/strategies/ic/paper_ic_entry_v2.py`,
`scripts/record/record_paper_trade.py`, `tests/unit/notifications/test_ic_entry_message.py` (renamed).

**Out of bounds:** `src/notifications/formatting.py` (`LegRow` / `build_leg_table` reused verbatim, not
touched) · overlay strategies (`cc_overlay_v1` / `pp_overlay_v1` / `collar_overlay_v1`) ·
`nifty_track_comparison_v1` · the EOD-audit / snapshot renderers · any DB schema (no `schema.md`) ·
`TelegramNotifier` / `TelegramGateway` internals · CSP entry gate / price-drift logic in the recorder.

Changes `src/` and `scripts/` behaviour: IC entry output is byte-identical after UEM-1; CSP gains a new
opt-in Telegram message after UEM-2.

## Session-start load hints

- `src/notifications/CLAUDE.md` — auto-loads; §"Instrument Label Formatting" governs the leg label.
- `FORMATTING.md` §3 — the `build_leg_table` 1-dp LTP/Entry exception and the escaping-boundary contract.
- `docs/archive/plan/telegram-markdown-migration/strategy-rollout/stories.md` — ROLL-17, the IC-entry
  design this generalizes; `scratch/2026-09-06_ic_entry_confirmation_format.py` is its reference impl.
- TODOS.md session log 2026-09-06 ROLL-17 — note `ivr`/`dte`/`spot`/`net_credit` were made **required**
  by `@code-reviewer`; UEM-1 keeps `dte`/`spot`/`net_credit` required and relaxes only `ivr` (+ `mode`,
  `expiry_type`) to optional, since CSP has no IVR in the recorder's scope. Record the reversal rationale.
- No council file. No DECISIONS.md architecture row (renderer refactor, not an architecture decision) —
  but add a DECISIONS.md §P&L & Reporting line at UEM-3 noting the shared entry renderer + CSP card.

## Task overview

- **UEM-1** — Generalize the IC renderer into a strategy-agnostic `EntryMessage` + `format_entry_message`;
  rename the module and its test file; migrate both IC call sites. IC output unchanged.
- **UEM-2** — Emit a lean CSP entry card from `scripts/record/record_paper_trade.py` behind `--notify`,
  on a successful open (SELL, not close / not roll), via `TelegramNotifier`, non-fatal on send failure.
- **UEM-3** — Docs close: `CONTEXT.md` "What Exists", `src/notifications/CLAUDE.md`, DECISIONS.md,
  `docs/plan/README.md`, `TODOS.md`; archive the folder.

## Definition of done

The shared `src/notifications/entry_message.py` renders both a 4-leg IC card (output identical to the
pre-UEM-1 `format_ic_entry_message` for the same inputs) and a 1-leg CSP card. Both IC entry scripts call
`format_entry_message`. `scripts/record/record_paper_trade.py --notify` sends a CSP entry card on a
successful open and is silent (stdout only) without the flag. No reference to `ic_entry_message` /
`format_ic_entry_message` / `ICEntryMessage` remains in `src/`, `scripts/`, or `tests/`. All unit tests
green. Docs updated and the folder archived per §Conventions *Completion → archive*.

## Perspectives not covered

A message-design perspective on whether a single lean layout genuinely serves a 1-leg CSP as well as a
4-leg IC — a naked short put has no wing, no defined risk, and arguably wants a max-loss / assignment-
strike line an IC card would never carry. This story assumes the lean common layout is sufficient and
defers any per-strategy line to the overlay follow-up; a workshop session could revisit before UEM-2.
