# Telegram IC Comparison Formatting — Story Specs

**Trigger:** 2026-08-07 Cowork session. User flagged that the "IC Monthly Comparison" Telegram
message (`build_comparison_report()`, `scripts/strategies/ic/paper_ic_monthly_comparison.py`)
renders misaligned in the actual Telegram app. Confirmed via a diagnostic scratch script
(`scratch/2026-08-07_telegram_ic_comparison_format_repro.py`, real sends to the configured
Telegram chat using the real `TelegramNotifier`) that the current implementation hand-counts
literal spaces to hit a fixed 20-char label budget plus fixed-width value columns — this breaks
silently the moment a label is longer than what was counted by hand at write time (reproduced
live with "Realized (inception)" / "Unrealized(inception)" colliding directly into the value
column).

Iterated on format directly against real Telegram sends (not guesses) and converged on: a
side-by-side layout with **dynamically computed** label width and column widths (derived from
`max(len(...))` over the actual header + cell contents, never hand-counted), values **right-aligned**
within each column, plus two new fields (open-leg count, since-inception realized P&L) and a
naming correction (see TGFMT-3). Final approved format, confirmed on-device:

```
📊 IC Monthly Comparison — 2026-08-06

          V1 Monthly      V2 Monthly
────────────────────────────────────
Legs             4/4         3/4 🔴
Credit           ₹87            ₹129
Captured        -21%             -1%
Put Δ          -0.03           -0.20
Call Δ          0.33            0.27
DTE                19              19
Flt               ₹0              ₹0
Bkd (M)           ₹0             ₹58
Bkd (I)       ₹1,204             ₹58
Lock zone        N/A            None
Adj          0 rolls  0 rolls + 0 locks
Signals            —               —

Edge so far:  V2 +₹58 vs V1
```

**Important finding surfaced during this investigation:** there are **two separate** snapshot
tables in play, and this story only depends on one of them:

- `paper_leg_snapshots` — per-leg daily snapshots. Zero rows for every IC variant (this is what
  `docs/plan/paper-ic-daily-snapshot/` SNAP-2 fixes). Not needed for this story.
- `paper_nav_snapshots` — per-strategy daily cumulative `realized_pnl` / `unrealized_pnl` /
  `total_pnl`. **Already has data** for every IC variant (10 rows each, 2026-07-21 → 2026-08-05)
  and for `paper_csp_nifty_v1` (57 rows, 2026-05-11 → 2026-08-05) and the three-track strategies.
  `_get_monthly_realized_pnl()` and `_get_unrealized_pnl()` (both already in
  `paper_ic_monthly_comparison.py`) already read from this table.

**Confirmed semantics of `paper_nav_snapshots`** (read directly from the two existing query
functions, not assumed): `realized_pnl` is **cumulative-as-of-date** (the existing month calc
subtracts the last pre-month-start value from the latest value — that pattern only works if the
field is cumulative). `unrealized_pnl` is a **same-day point-in-time mark** — it is never
accumulated or delta'd anywhere in the existing code. This second point directly shapes TGFMT-3
below: since unrealized P&L isn't month-scoped in the first place, a `Flt (M)` vs `Flt (I)` split
is not a real distinction — both would always read identically. **This story corrects that** before
it ships, rather than shipping a duplicated field pair discovered live in the scratch script.

**Not blocked by `docs/plan/paper-ic-daily-snapshot/`** — that story's SNAP-1/SNAP-2/SNAP-4 are
about per-leg breakdowns from `paper_leg_snapshots`, a genuinely separate and still-needed effort.
This story's since-inception figure reads the already-populated `paper_nav_snapshots` table
instead.

---

## TGFMT-1 — Fix `build_comparison_report()` alignment: dynamic widths, right-aligned columns

**Problem:** Current implementation hand-counts literal spaces per label to hit a fixed 20-char
budget, and uses fixed `:<15`-style value-column widths. Both break silently the moment a label or
value exceeds what was counted/assumed by hand — reproduced live in this session.

**Fix:** Replace the hand-padded f-string block in `build_comparison_report()` with the
dynamic-width approach proven in `scratch/2026-08-07_telegram_ic_comparison_format_repro.py`'s
`_build_side_by_side_report()`:
- `label_width = max(len(label) for label in rows) + 1`
- `col1_width = max(len("V1 Monthly"), max(len(v1_cell) for v1_cell in rows))` (same pattern for
  col2 against `"V2 Monthly"`)
- Values right-aligned within their column (`f"{cell:>{col_width}}"`); header and separator sized
  from the same computed widths — never a hand-typed literal.
- Preserve the existing 🔴 red-flag convention for any cell carrying a warning (currently only
  used for TGFMT-2's leg count, but the mechanism should stay generic).

**Tests required:**
- Happy path: existing row set → matches the approved format above byte-for-byte.
- Edge case: an artificially long label (e.g. 25+ chars) → still aligns correctly, no collision
  with the value column. This is a direct regression test for the bug that triggered this story.

**Files touched:** `scripts/strategies/ic/paper_ic_monthly_comparison.py`,
`tests/unit/strategies/ic/test_paper_ic_monthly_comparison.py`.

---

## TGFMT-2 — Add "Legs" row: open leg count out of 4, red-flag if < 4

**Problem:** No visibility today into whether all 4 IC legs are actually open. A partial-close or
roll-desync state (e.g. one leg closed early, one leg's roll failed) currently shows nowhere in
this report.

**Fix:** `ICMonthlyStats` gains `open_leg_count: int`. `build_stats()` already computes
`open_pos = [p for p in positions if p.net_qty != 0]` — just thread `len(open_pos)` into the
dataclass. No new store/query dependency; this is live data already fetched. Render as `f"{n}/4"`
with a 🔴 suffix when `n < 4` (per TGFMT-1's generic warning-cell mechanism).

**Tests required:**
- Happy path: 4 open legs → `"4/4"`, no emoji.
- Edge case: 3 open legs (or 0) → `"3/4 🔴"` / `"0/4 🔴"`.

**Files touched:** `scripts/strategies/ic/paper_ic_monthly_comparison.py`, same test file.

---

## TGFMT-3 — Add "Bkd (I)" (realized since inception); rename Unrealized to "Flt" (drop M/I split)

**Problem / finding:** Unrealized P&L is not month-scoped anywhere in the existing code —
`_get_unrealized_pnl()` just reads today's `paper_nav_snapshots.unrealized_pnl` (a point-in-time
mark, never a delta or a cumulative sum). A `Flt (M)` / `Flt (I)` split (as drafted in the scratch
script while iterating on this format) would therefore always show two identical numbers — a false
distinction. Only realized P&L has a genuine month-vs-inception split, because
`paper_nav_snapshots.realized_pnl` is cumulative-as-of-date.

**Correct field set (supersedes the scratch script's placeholder Flt(M)/Flt(I) pair):**
- `Bkd (M)` — realized this calendar month. **No change** — existing `realized_pnl_month` /
  `_get_monthly_realized_pnl()`.
- `Bkd (I)` — realized since inception. **New.** Add `_get_inception_realized_pnl()`, mirroring
  `_get_monthly_realized_pnl()`'s query shape but without the prior-month subtraction:
  `SELECT realized_pnl FROM paper_nav_snapshots WHERE strategy_name=? ORDER BY snapshot_date DESC LIMIT 1`
  — the latest cumulative value *is* the since-inception figure, because the table's first row for
  a strategy functions as its zero baseline. No backfill needed; this reads data that already
  exists.
- `Flt` — unrealized. **Rename only** (drop "(M)"/"(I)" entirely) — existing `unrealized_pnl` /
  `_get_unrealized_pnl()`, unchanged calculation.

**Fix:** `ICMonthlyStats` gains `realized_pnl_inception: Decimal`. Row label changes: "Unrealized
P&L" → "Flt" (single row, not two). `build_comparison_report()` row order becomes: `Legs, Credit,
Captured, Put Δ, Call Δ, DTE, Flt, Bkd (M), Bkd (I), Lock zone, Adj, Signals` (matches the approved
format block above).

**Tests required:**
- Happy path: multi-day `paper_nav_snapshots` fixture → `Bkd (I)` returns the latest row's
  `realized_pnl` correctly.
- Edge case: strategy with zero `paper_nav_snapshots` rows (a hypothetical future IC variant not
  yet snapshotted) → returns `None`/"N/A", not a crash or a silently-wrong `Decimal("0")`.

**Files touched:** `scripts/strategies/ic/paper_ic_monthly_comparison.py`, same test file.

**Financial-logic gate:** This reports real, already-persisted P&L to Telegram — per `CLAUDE.md`'s
AutoTrigger table, the real `@code-reviewer` gate is mandatory before commit. Cowork cannot spawn
the local `.claude/agents/code-reviewer` subagent — per the project's documented substitution
pattern (used for BUG-014 and the `paper-ic-daily-snapshot` story), apply `REVIEW.md`'s checklist
directly and state explicitly in the commit message that this is a substitution, not an equivalent
automated gate.

---

## Sequencing

TGFMT-1 → TGFMT-2 (independent of each other, TGFMT-2 can run in parallel with or right after
TGFMT-1) → TGFMT-3 last, since it's the financial-data change and should land against an already-
stable layout rather than needing the alignment code re-touched afterward.

Not blocked by `docs/plan/paper-ic-daily-snapshot/` (SNAP-1 through SNAP-4) — see the finding above.
Cross-reference that story for the still-needed per-leg breakdown work, which this story's
strategy-level aggregate figures do not replace.
