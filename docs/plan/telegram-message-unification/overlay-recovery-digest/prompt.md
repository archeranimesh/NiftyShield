# Overlay recovery digest — prompt

> Fix the CC data that silently vanishes from the S9 "NiftyBees vs overlays" recovery digest,
> then migrate that digest onto the MarkdownV2 fenced house style — the last hand-rolled
> paper-strategy Telegram message outside a structured renderer.

Sub-story 4 (last) of the `telegram-message-unification/` epic. `/work` routes here via the
epic `prompt.md`.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else.
Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task.
Read that task's full spec in `stories.md` (same task id) before writing any code.
One task per session. Complete it fully. Stop.

## Why this story exists

The daily S9 digest (`_build_recovery_digest` in
`scripts/strategies/three_track/paper_3track_snapshot.py`) compares NiftyBees' 1-day P&L
against each standalone overlay's recovery. On 2026-09-09 it rendered:

```
📊 NiftyBees vs overlays — 09 Sep
NiftyBees: -10724
  PP     +6627 (62%)
  Collar +5694 (53%)
  CC     No data
Best: PP
```

`CC     No data` is a **defect**, verified against `logs/`:

- `cc_entry.log` 2026-09-09 10:30:21 — `trade.INSERTED strategy=paper_nifty_overlay
  leg=overlay_cc` (CC bootstrap, SELL @ 53.90).
- `paper_snapshot.log` 2026-09-09 15:35:08 — `Overlay leg snapshot saved: overlay_cc
  2026-09-09` (the `paper_leg_snapshots` row *was* written).
- The same run's printed comparison table shows `paper_nifty_overlay / CC  ₹+793 / ₹+5,957 /
  ₹+6,750` — CC P&L *is* computed.
- Then: `WARNING protection_recovery.overlay_source_missing … overlay_type=cc
  date=2026-09-09` (also fires 2026-09-08).

**Root cause** — `_overlay_type_groups` (~line 1157), the BUG-030 fix:

```python
elif has_cc and has_put:
    groups["collar"] = ["overlay_cc", "overlay_collar_put"]
```

On 09 Sep the open roles were `{overlay_cc, overlay_pp, overlay_collar_put}` → this branch
folds `overlay_cc` **into the collar group**, so no standalone `cc` `OverlayPnLSnapshot` row
is written and the digest reads back nothing. Worse: `_compute_overlay_pnl_snapshots` sums
`groups["collar"]` across both roles, so the standalone CC's P&L is **silently added to the
digest's `Collar` line** — `Collar +5694` is inflated by the CC.

The BUG-030 fix assumed `overlay_cc` *is* the collar's shared call leg (the entry code dedups
a collar call against an existing CC). It does not handle a **standalone CC bootstrap
coexisting with a collar** — the current live state.

Two goals: (1) fix the grouping so CC data reaches the digest and the Collar figure is
correct; (2) migrate the digest onto the fenced house style, consistent with
`pre_market_brief.py`'s `unified-exit-message/` UXM-7 redesign, and fix its BUG-042 send path.

## Scope guard

**In bounds:** `scripts/strategies/three_track/paper_3track_snapshot.py` —
`_overlay_type_groups`, `_compute_overlay_pnl_snapshots`, `_build_protection_recovery_snapshot`,
`_build_recovery_digest`, and the digest's `notifier.send()` call site · matching
`tests/unit/` · `docs/bugs/bugs.md` (BUG-044) · `CONTEXT.md` / `DECISIONS.md` / the epic
`README.md`.

**Out of bounds:** `paper_3track_overlay_entry.py` entry / dedup logic — **read-only** for
ORD-1's investigation, not modified · `src/paper/store.py` schema and the
`paper_overlay_pnl_snapshots` / `paper_leg_snapshots` table shapes (no `schema.md`) · the
`PaperStore` P&L math · the entry/exit renderers from the other three sub-stories · the
printed comparison table logic beyond confirming it stays consistent with the fixed digest.

Changes `scripts/` behaviour: the digest gains a real `CC` line when a standalone CC overlay
is open, the `Collar` figure no longer absorbs it, and the whole message switches to a
fenced block.

## Session-start load hints

- `logs/paper_snapshot.log` + `logs/cc_entry.log` — the 2026-09-08/09 evidence above.
- The `_overlay_type_groups` docstring + the BUG-030 / BUG-028 / BUG-032 comments in
  `paper_3track_snapshot.py` — the overlay-attribution bug history this sits in.
- `paper_3track_overlay_entry.py` `build_overlay_trades()` / `_record_collar_trades()` — the
  dedup guard ("the existing CC serves as the collar call") ORD-1 must understand.
- `unified-exit-message/` `stories.md` UXM-7 — the `pre_market_brief.py` fenced-table target
  ORD-3 mirrors.
- `docs/bugs/bugs.md` BUG-042 — the send-path class this digest is a member of.
- `src/notifications/CLAUDE.md` + `FORMATTING.md` §3 — the fenced-block escaping contract.

## Task overview

- **ORD-1** — Investigate: from `paper_3track_overlay_entry.py` and the leg-snapshot history,
  determine whether a standalone `overlay_cc` bootstrap and a collar genuinely coexist (vs.
  `overlay_cc` always being the collar call when a collar put is present). Decide the correct
  `_overlay_type_groups` behaviour. File BUG-044 with the finding + decision.
- **ORD-2** — Fix `_overlay_type_groups` + `_compute_overlay_pnl_snapshots` per ORD-1: a
  standalone CC gets its own `cc` `OverlayPnLSnapshot` row; the collar total stops absorbing
  it. Keep the genuine collar-call-tagged-`overlay_cc` case working. Verify the printed
  comparison table and the digest agree.
- **ORD-3** — Migrate `_build_recovery_digest` to a single MarkdownV2 fenced block (no
  per-line `escape_markdown`), matching the `pre_market_brief.py` house style; fix the
  BUG-042 send path for this caller.
- **ORD-4** — Epic close: docs + `git mv` the whole `telegram-message-unification/` folder to
  `docs/archive/plan/`; collapse the `docs/plan/README.md` epic entry; move the `TODOS.md`
  line to `TODOS_ARCHIVE.md`.

## Definition of done

When a standalone CC overlay is open, the S9 digest shows a real `CC` line with its 1-day
recovery figure, and the `Collar` line reflects only the collar's legs. The
`protection_recovery.overlay_source_missing` WARNING no longer fires for a CC that has a leg
snapshot. The digest renders as one fenced MarkdownV2 block and sends without a 400. BUG-044
is filed and marked fixed with the closing SHA. All unit tests green. The epic is archived
per §Conventions *Completion → archive*.

## Perspectives not covered

A paper-trading-accounting perspective on what "recovery %" should mean for a CC that is
economically part of a collar vs. a standalone income overlay — ORD-1 settles the grouping,
but if the two structures share a physical short call, attributing its P&L cleanly to one
"recovery" bucket may be genuinely ambiguous and worth a workshop before ORD-2.
