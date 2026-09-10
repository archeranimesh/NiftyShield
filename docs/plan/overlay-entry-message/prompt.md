# Overlay entry message — prompt

> Extend the shared `entry_message.py` renderer (shipped by `unified-entry-message/`) to the
> automated overlay entries — Collar, CC and PP re-entry, plus the three-track bootstrap
> message — none of which emits a structured entry card today.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else.
Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task.
Read that task's full spec in `stories.md` (same task id) before writing any code.
One task per session. Complete it fully. Stop.

## Why this story exists

`unified-entry-message/` (UEM-1..3) built `src/notifications/entry_message.py`
(`EntryMessage` + `format_entry_message`, `headline_label` field, optional
`ivr`/`mode`/`expiry_type`) and wired it into IC (both scripts) and the CSP / CC entry path
through `scripts/record/record_paper_trade.py --notify`. That covered the *manual / selector*
entry paths. The **automated overlay** entries were explicitly left as a follow-up — this
story — because they run through code the UEM scope guard marked out of bounds:

- **Collar re-entry** (`CollarOverlayV1._reenter_collar`, Collar3b) records the two-leg pair
  and returns silently — only *failures* notify (`_send_reentry_failure_notification`). A
  successful re-entry produces no Telegram message at all.
- **CC re-entry** (`CCOverlayV1.apply_action` via `ReEntryMixin`) and **PP re-entry**
  (`PPOverlayV1.apply_action`) — same: a `_send_close_notification` exists, no entry card.
- **Bootstrap** (`auto_cc_bootstrap` / `auto_pp_bootstrap` / `auto_collar_bootstrap` via
  `scripts/strategies/three_track/paper_3track_overlay_entry.py`) emits a hand-rolled
  `📥 Overlay Entry — {TYPE} Bootstrap` line list, not the shared renderer.

Animesh asked (2026-09-10) to bring Collar onto the shared card; CC / PP and the bootstrap
message come along for consistency since they share the strategy classes and the script.

## The one renderer gap this story must close first

The IC `_credit_line` hard-codes `💰 *Net credit:*` and runs the value through
`format_money`. A **collar** is normally a net *debit* (the long put costs more than the
short call brings in) and a **PP** re-entry is a pure debit. `💰 *Net credit:* ₹-25.00/lot`
reads as a bug. OEM-1 makes the net line sign-aware — negative → `💰 *Net debit:* ₹25.00/lot`
(absolute value, label flipped). Positive / zero is byte-identical to today, so IC / CSP / CC
output does not change.

## Scope guard

**In bounds:** `src/notifications/entry_message.py` (sign-aware net line only — no field
renames), `src/strategy/collar_overlay_v1.py`, `src/strategy/cc_overlay_v1.py`,
`src/strategy/pp_overlay_v1.py`, `src/strategy/reentry_mixin.py` (only if the re-entry-success
hook genuinely lives there), `scripts/strategies/three_track/paper_3track_overlay_entry.py`,
and the matching `tests/unit/` files.

**Out of bounds:** `EntryMessage` field renames (`net_credit` stays — only `_credit_line`
logic changes) · `src/notifications/formatting.py` · the IC / CSP / CC call sites shipped by
`unified-entry-message/` (unchanged) · `nifty_track_comparison_v1` (not a credit structure —
stays deferred) · the `_send_close_notification` / re-entry-failure paths (entry only) · any
DB schema (no `schema.md`) · strike-selection / gate / ladder logic in the overlay classes ·
`TelegramGateway` / `TelegramNotifier` internals.

Changes `src/` and `scripts/` behaviour: a successful automated Collar / CC / PP re-entry
sends a new `✅ *… Entry*` card after OEM-2 / OEM-3; the bootstrap message switches to the
shared renderer after OEM-4. IC / CSP / CC output is unchanged throughout.

## Session-start load hints

- `unified-entry-message/` `stories.md` (archived after UEM-3) — the `EntryMessage` field
  list + `_headline` / `_kv_row` / `_credit_line` design this builds on.
- `src/notifications/CLAUDE.md` — auto-loads; §"Instrument Label Formatting" governs the leg
  label; §"kv row omits IVR when absent" note added by UEM-3.
- `FORMATTING.md` §3 — `build_leg_table` 1-dp exception + the escaping-boundary contract.
- `src/strategy/CLAUDE.md` if present, and the `paper` module `CLAUDE.md` — the re-entry tick
  loop, `_notifier` dispatch contract (`send_notification` → `send_plain_message` → `send`).
- TODOS.md session log 2026-09-10 (UEM close) — the `ivr` relaxation rationale carries here:
  overlay re-entry has no IVR at record time either.

## Task overview

- **OEM-1** — Sign-aware net line in `entry_message.py`: negative `net_credit` renders
  `💰 *Net debit:* ₹X/lot  ×65 \= ₹Y` (absolute value, label flipped). Positive / zero
  unchanged → IC / CSP / CC byte-identical. One new test each side of zero.
- **OEM-2** — `CollarOverlayV1._reenter_collar` sends a `✅ *Collar Entry*` card (2 legs:
  `[B]` put, `[S]` call) on a successful two-leg record, via `self._notifier`, non-fatal,
  mirroring the existing failure-notification dispatch. `greeks-analyst` gate (delta fields).
- **OEM-3** — `CCOverlayV1` (`✅ *CC Entry*`, 1 `[S]` call leg) and `PPOverlayV1`
  (`✅ *PP Entry*`, 1 `[B]` put leg) send the same card on a successful automated re-entry.
  `greeks-analyst` gate.
- **OEM-4** — Migrate the `📥 Overlay Entry — {TYPE} Bootstrap` message in
  `paper_3track_overlay_entry.py` to `format_entry_message` for cc / pp / collar;
  `headline_label` from `overlay_type`. The `⚠️ Gate Logged` line stays appended by the
  caller *after* the rendered card — the renderer stays lean, no new field.
- **OEM-5** — Docs close: `CONTEXT.md`, `src/notifications/CLAUDE.md`, `DECISIONS.md`,
  `docs/plan/README.md`, `TODOS.md`; archive the folder.

## Definition of done

`format_entry_message` renders a `💰 *Net debit:*` line for a negative `net_credit` and is
byte-identical for a positive one. A successful automated Collar / CC / PP re-entry sends the
matching `✅ *… Entry*` card; a send failure is logged and never crashes the tick. The
three-track bootstrap message is the shared renderer's output (+ the unchanged gate line).
No hand-rolled `✅ … Entry` / `📥 Overlay Entry` f-string remains in the overlay classes or
the bootstrap script. All unit tests green. Docs updated and the folder archived per
§Conventions *Completion → archive*.

## Perspectives not covered

A message-design perspective on whether the lean common card wants a collar-specific
protection line (max downside above the put strike, cost of carry) that an IC card never
needs — deferred, same assumption as `unified-entry-message/`. And whether the bootstrap
message losing its `Short 65x NIFTY …` per-leg quantity phrasing (the shared table shows
instrument + prices, not lot count) is acceptable — this story assumes yes.
