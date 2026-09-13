# Telegram message unification — epic index

> A structured, fenced house style for every paper-strategy Telegram message. Today entry cards exist only for IC, exit cards come in five divergent hand-rolled shapes, and the S9 "NiftyBees vs
> overlays" digest is a sixth ad-hoc format with a data bug. This epic builds `src/notifications/entry_message.py` and `exit_message.py`, migrates every strategy (IC v1/v2, CSP, CC, PP, Collar) and
> every path (strategy classes, `auto_close.py`, `record_paper_trade.py`, the three-track bootstrap, `pre_market_brief.py`) onto them, adds cycle + inception P&L and win-rate context to the close
> card, and fixes + fenced-formats the overlay recovery digest. Four sub-stories: the first three share one renderer lineage (the exit renderer mirrors the entry renderer's structure and the
> sign-aware net line) and land strictly in order; the fourth is independent but closes the epic.

## Why this epic exists

Animesh asked (2026-09-10) to make the paper-trading Telegram messages uniform. The audit that followed found: only Iron Condor has a structured entry card (`ic_entry_message.py`, ROLL-17 `26527c2`);
CSP has no entry notification at all; the three overlays build entry text ad-hoc; and the close side has drifted into five shapes across `ic_nifty_v1/v2`, `csp_nifty_v1`, the three `*_overlay_v1`
classes, and `auto_close.py` — four headline conventions, P&L shown in two of five, leg prices absent from CSP entirely. The IC entry renderer already decomposes into parts common to every credit
structure (headline, kv row, fenced leg table, net line), so the difference between strategies is leg count and sign, which is data, not layout.

Three chained stories were authored (docs-only) on 2026-09-10 and grouped into this epic on the same day: `unified-entry-message/` (UEM-1..3), `overlay-entry-message/` (OEM-1..5),
`unified-exit-message/` (UXM-1..8). A fourth, `overlay-recovery-digest/` (ORD-1..4), was added 2026-09-10 after Animesh saw the S9 "NiftyBees vs overlays" digest render `CC No data` on 09 Sep — a
verified defect (`_overlay_type_groups` folds a standalone `overlay_cc` into the collar group, so the CC line vanishes and the Collar figure is inflated by it) — and asked for that message to be
brought onto the house style too.

## Scope decisions

Confirmed with Animesh, 2026-09-10:

- **Order is fixed: entry → overlay → exit → recovery-digest.** The overlay story adds the sign-aware net line the exit renderer depends on; the exit renderer mirrors the entry renderer's part
  structure. `overlay-recovery-digest/` is independent of that lineage (a different message, no shared renderer) but is sequenced last and carries the epic close. A later story must not start before
  every task of the previous one is ticked.
- **`overlay-recovery-digest/` fixes a data bug before it reformats.** ORD-1 investigates whether a standalone CC overlay and a collar genuinely coexist and decides the correct `_overlay_type_groups`
  grouping; ORD-2 fixes it (tracked as BUG-044); only then ORD-3 fenced-formats the digest. A formatting migration must not be built on the broken CC data.
- **No DB schema change anywhere in the epic.** `paper_exit_events` + the `paper_trades` ledger already carry everything the P&L footer needs; cycles are reconstructed, not stored. No sub-story has a
  `schema.md`.
- **The CSP / CC entry card is emitted from the shared recorder behind `--notify`, not a new wrapper script.** `headline_label` and leg `role` are derived from `--strategy` and the option type.
- **`ivr` is optional on `EntryMessage`** (relaxed from ROLL-17, which made it required) — CSP, CC and overlay re-entry have no IVR at record time. `dte` / `spot` / `net_credit` stay required.
- **Decay is on the gross-short-premium basis** (`short_decay_pct` = `100 * (short_credit − short_buyback) / short_credit`), not the net `decay_pct` — the net figure is `None` for a net-debit entry
  and unstable near a zero collar net. `short_decay_pct` is `None` for a pure-long PP. The net `decay_pct` stays on `Cycle` for the report CLI.
- **Inception P&L is the store number, not the cycle sum.** `get_strategy_realized_pnl(store, strategy_name)` drives the headline number; reconstructed cycles drive only the stats.
- **`nifty_track_comparison_v1` stays deferred** — not a credit structure, no short premium, out of scope for every sub-story.
- **The lean common layout is assumed sufficient** for a 1-leg CSP / CC as well as a 4-leg IC — no per-strategy max-loss / assignment / protection line. A workshop session could revisit before OEM-2.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `unified-entry-message/` | Shared `entry_message.py` renderer; IC migrated onto it; CSP + CC entry card via `record_paper_trade.py --notify` (UEM-1..3) | 🔄 In progress (UEM-1, UEM-2 done) | — | — |
| `overlay-entry-message/` | Sign-aware net line; Collar / CC / PP automated re-entry cards; three-track bootstrap migrated onto the renderer (OEM-1..5) | ⬜ Not started | `unified-entry-message` | — |
| `unified-exit-message/` | Shared `exit_message.py` close renderer + P&L / win-rate / decay footer; `pre_market_brief.py` redesign (UXM-1..8) | ⬜ | `overlay-entry-message` | — |
| `overlay-recovery-digest/` | Fix the standalone-CC-vanishes-into-Collar bug (BUG-044) in the S9 digest, then fenced-format it (ORD-1..4) | ⬜ | `unified-exit-message` | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`.

## Cross-cutting constraints

- **Every send is non-fatal.** A Telegram send failure is logged and never crashes a strategy tick, the `auto_close.py` daemon, or a `record_paper_trade.py` recording.
- **The entry table helper is frozen.** `src/notifications/formatting.py::build_leg_table` and `LegRow` are reused verbatim by the entry renderer and are not touched. The exit story adds a *separate*
  `build_close_leg_table`; it does not modify `build_leg_table`.
- **Escaping-boundary contract.** The fenced block is emitted literally; every interpolated value is pre-escaped for MarkdownV2 per `FORMATTING.md` §3 and `src/notifications/CLAUDE.md`.
- **IC / CSP / CC output stays byte-identical** through OEM-1 (positive / zero `net_credit` renders exactly as before) and through every exit migration for structures already carrying a card.
- **One commit per task.** Never bundle two sub-stories' work, and never bundle a renderer change with a caller migration — Model → renderer → per-strategy caller are separate commits.
- **Sub-stories are not individually archived.** Each sub-story close flips its row in this file's **Stories** table; the whole epic folder is archived in one move at `overlay-recovery-digest/` ORD-4.

## Supersession / coordination

- Built directly on the `telegram-markdown-migration/` epic (archived 2026-09-06) — the MarkdownV2 parse-mode switch, `FORMATTING.md`, and ROLL-17's IC entry card are its output. This epic generalizes
  ROLL-17's renderer and finishes the job for the close side and the overlays.
- `pre_market_brief.py` (UXM-7) still carries `<b>` HTML from before the markdown migration — UXM-7 completes that file's migration as part of the redesign.
- The S9 recovery digest (`_build_recovery_digest`) is one of the callers BUG-042 lists as broken by the `721daf9` MarkdownV2 switch — `overlay-recovery-digest/` ORD-3 fixes its send path as part of
  the fenced-format migration, so BUG-042's per-caller list shrinks by one when the epic closes.

## Epic done when

- **`unified-entry-message`** — `src/notifications/entry_message.py` renders both a 4-leg IC card (byte-identical to the pre-refactor `format_ic_entry_message`) and a 1-leg CSP / CC card; both IC
  entry scripts and `record_paper_trade.py --notify` call it; no `ic_entry_message` / `ICEntryMessage` / `format_ic_entry_message` reference remains.
- **`overlay-entry-message`** — `format_entry_message` renders `💰 *Net debit:*` for a negative `net_credit` and is byte-identical for a positive one; a successful automated Collar / CC / PP re-entry
  and the three-track bootstrap all emit the shared card; no hand-rolled `✅ … Entry` / `📥 Overlay Entry` f-string remains in the overlay classes or the bootstrap script.
- **`unified-exit-message`** — `format_exit_message` renders the Act/Instrument/Entry/Exit/P&L table + the this-exit / cycle / inception / win-rate footer; all six strategies and both paths
  (strategy-class + `auto_close.py`) plus `record_paper_trade.py --close --notify` emit it; win rate shown only at `closed_count >= 5`; `pre_market_brief.py` sends a MarkdownV2 fenced table with the
  overlay split into CC / Collar / PP and a portfolio total; no hand-rolled `✅ … closed` / `📤 Closed:` f-string remains in `src/strategy/`.
- **`overlay-recovery-digest`** — when a standalone CC overlay is open the S9 digest shows a real `CC` line and the `Collar` figure excludes it; `protection_recovery.overlay_source_missing` no longer
  fires for a CC that has a leg snapshot; `_build_recovery_digest` returns one fenced MarkdownV2 block and sends without a 400; BUG-044 is `✅ Fixed`.
