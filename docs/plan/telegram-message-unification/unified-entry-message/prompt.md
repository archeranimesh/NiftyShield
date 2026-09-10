# Unified entry message — prompt

> One shared lean entry-confirmation renderer for every paper strategy; IC migrated onto it,
> CSP and CC given an entry Telegram card they currently lack.

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
CC (covered-call overlay) is the same: `scripts/strategies/cc_calibration/paper_cc_entry.py` is only a
selector that *prints* a `record_paper_trade.py --strategy <cc-overlay> --strike … --qty 65` command
line — the actual record + (absent) notification also runs through `record_paper_trade.py`.

The IC renderer already decomposes into parts common to every credit structure — headline, one-line kv
row, fenced `build_leg_table()`, net-credit line — differing across strategies only in leg count (1 for
CSP / CC, 4 for IC), which is data, not layout. Animesh asked (2026-09-10) to make entry messages
uniform.

Scoped to IC, CSP and CC. Because CSP and CC entries both funnel through
`scripts/record/record_paper_trade.py`, one `--notify` card behind a flag covers both — `headline_label`
(`"CSP"` / `"CC"`) is chosen from `--strategy`, the leg `role` (`"Short Put"` / `"Short Call"`) from the
option type. The three-track bootstrap message in `paper_3track_overlay_entry.py`, the PP / collar
overlays, and track-comparison are a deliberate follow-up once the shared renderer has real consumers.
Format stays lean (no mark / capture / ROI / margin lines — those are meaningless at entry and belong to
the EOD-audit path). The CSP / CC card is emitted from the shared recorder behind a flag rather than a
new wrapper script — decided with Animesh 2026-09-10.

## Scope guard

**In bounds:** `src/notifications/ic_entry_message.py` (renamed to `entry_message.py`),
`scripts/strategies/ic/paper_ic_entry.py`, `scripts/strategies/ic/paper_ic_entry_v2.py`,
`scripts/record/record_paper_trade.py`, `tests/unit/notifications/test_ic_entry_message.py` (renamed),
`tests/unit/scripts/test_record_paper_trade.py`.

**Out of bounds:** `src/notifications/formatting.py` (`LegRow` / `build_leg_table` reused verbatim, not
touched) · the overlay strategy classes (`cc_overlay_v1` / `pp_overlay_v1` / `collar_overlay_v1`) and
their close-notification paths · `paper_3track_overlay_entry.py`'s `📥 Overlay Entry` bootstrap message ·
`scripts/strategies/cc_calibration/paper_cc_entry.py` (the selector — it only prints a command, not
touched) · `nifty_track_comparison_v1` · the EOD-audit / snapshot renderers · any DB schema (no
`schema.md`) · `TelegramNotifier` / `TelegramGateway` internals · CSP / CC entry gate / price-drift
logic in the recorder.

Changes `src/` and `scripts/` behaviour: IC entry output is byte-identical after UEM-1; CSP and CC gain a
new opt-in Telegram message after UEM-2.

## Session-start load hints

- `src/notifications/CLAUDE.md` — auto-loads; §"Instrument Label Formatting" governs the leg label.
- `FORMATTING.md` §3 — the `build_leg_table` 1-dp LTP/Entry exception and the escaping-boundary contract.
- `docs/archive/plan/telegram-markdown-migration/strategy-rollout/stories.md` — ROLL-17, the IC-entry
  design this generalizes; `scratch/2026-09-06_ic_entry_confirmation_format.py` is its reference impl.
- TODOS.md session log 2026-09-06 ROLL-17 — note `ivr`/`dte`/`spot`/`net_credit` were made **required**
  by `@code-reviewer`; UEM-1 keeps `dte`/`spot`/`net_credit` required and relaxes only `ivr` (+ `mode`,
  `expiry_type`) to optional, since CSP and CC have no IVR in the recorder's scope. Record the reversal
  rationale.
- No council file. No DECISIONS.md architecture row (renderer refactor, not an architecture decision) —
  but add a DECISIONS.md §P&L & Reporting line at UEM-3 noting the shared entry renderer + CSP / CC card.

## Task overview

- **UEM-1** — Generalize the IC renderer into a strategy-agnostic `EntryMessage` + `format_entry_message`;
  rename the module and its test file; migrate both IC call sites. IC output unchanged.
- **UEM-2** — Emit a lean CSP / CC entry card from `scripts/record/record_paper_trade.py` behind
  `--notify`, on a successful open (SELL, not close / not roll), via `TelegramNotifier`, non-fatal on
  send failure. `headline_label` (`"CSP"` / `"CC"`) and leg `role` are derived from `--strategy` and the
  option type.
- **UEM-3** — Sub-story docs close: `CONTEXT.md` "What Exists", `src/notifications/CLAUDE.md`,
  DECISIONS.md, the epic `README.md` Stories table, `TODOS.md` Session Log. No folder archive — the
  epic archives as a whole at UXM-8.

## Definition of done

The shared `src/notifications/entry_message.py` renders both a 4-leg IC card (output identical to the
pre-UEM-1 `format_ic_entry_message` for the same inputs) and a 1-leg CSP / CC card. Both IC entry scripts
call `format_entry_message`. `scripts/record/record_paper_trade.py --notify` sends a `✅ *CSP Entry*` or
`✅ *CC Entry*` card (chosen by `--strategy`) on a successful open and is silent (stdout only) without the
flag. No reference to `ic_entry_message` /
`format_ic_entry_message` / `ICEntryMessage` remains in `src/`, `scripts/`, or `tests/`. All unit tests
green. Sub-story docs updated and its epic `README.md` Stories-table row flipped to ✅ (the epic
folder is archived only after the last sub-story, UXM-8).

## Perspectives not covered

A message-design perspective on whether a single lean layout genuinely serves a 1-leg CSP or CC as well
as a 4-leg IC — a naked short put or a covered call has no wing, no defined risk, and arguably wants a
max-loss / assignment- or cover-strike line an IC card would never carry. This story assumes the lean
common layout is sufficient and defers any per-strategy line to the overlay follow-up; a workshop
session could revisit before UEM-2. Also unaddressed: the current `📥 Overlay Entry — CC Bootstrap`
message carries a per-leg `Short 65x NIFTY …` quantity phrasing and a `⚠️ Gate Logged` line that the
shared lean card drops — accepted for the recorder path, and the three-track bootstrap keeps its own
renderer for now.
