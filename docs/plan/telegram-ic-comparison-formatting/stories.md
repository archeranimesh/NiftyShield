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

          V1 Monthly         V2 Monthly
───────────────────────────────────────
Legs             4/4              3/4 🔴
Credit           ₹87               ₹129
Captured        -21%                -1%
Put Δ          -0.03              -0.20
Call Δ          0.33               0.27
DTE               19                 19
Flt (M)           ₹0                 ₹0
Bkd (M)           ₹0                ₹58
Bkd (I)       ₹1,204                ₹58
Flt (I)           ₹0                 ₹0
Lock zone        N/A               None
Adj          0 rolls  0 rolls + 0 locks
Signals            —                  —

Edge so far:  V2 +₹58 vs V1
```

**Revision (2026-08-07, same session, before implementation started):** user's target format
restores a `Flt (M)`/`Flt (I)` split — but per an explicit follow-up decision, `Flt (M)` is **not**
a cosmetic duplicate of `Flt (I)`. It is a real calculation: unrealized P&L change since month
start (today's mark minus the mark at the last snapshot before month start), computed from
`paper_nav_snapshots.unrealized_pnl`. See revised TGFMT-3 below — this supersedes the "drop the
split" correction described in the original TGFMT-3 write-up further down; that write-up's
*reasoning* (unrealized is a point-in-time mark, not inherently month-scoped) is still correct,
it just means `Flt (M)` needs a new delta calculation rather than being inferred for free, not
that the row should be dropped.

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

## TGFMT-3 — Add "Bkd (I)" and "Flt (M)"; rename Unrealized "Flt (I)" — real month-delta calc

**Problem / finding (original):** Unrealized P&L is not month-scoped anywhere in the existing
code — `_get_unrealized_pnl()` just reads today's `paper_nav_snapshots.unrealized_pnl` (a
point-in-time mark, never a delta or a cumulative sum). Only realized P&L had a free month-vs-
inception split, because `paper_nav_snapshots.realized_pnl` is cumulative-as-of-date.

**Revised decision (2026-08-07, after this story was first drafted):** the fix is not to drop the
`Flt` month/inception split — it's to compute it properly. `Flt (M)` is a genuine new
calculation: unrealized P&L **change since month start**, not a copy of today's mark.

**Correct field set:**
- `Bkd (M)` — realized this calendar month. **No change** — existing `realized_pnl_month` /
  `_get_monthly_realized_pnl()`.
- `Bkd (I)` — realized since inception. **New.** Add `_get_inception_realized_pnl()`, mirroring
  `_get_monthly_realized_pnl()`'s query shape but without the prior-month subtraction:
  `SELECT realized_pnl FROM paper_nav_snapshots WHERE strategy_name=? ORDER BY snapshot_date DESC LIMIT 1`
  — the latest cumulative value *is* the since-inception figure, because the table's first row for
  a strategy functions as its zero baseline. No backfill needed; this reads data that already
  exists.
- `Flt (I)` — unrealized, today's mark. **Rename only** (`(I)` suffix, no calc change) — existing
  `unrealized_pnl` / `_get_unrealized_pnl()`, unchanged.
- `Flt (M)` — unrealized P&L **change since month start**. **New.** Add
  `_get_unrealized_pnl_month_change()`: today's `unrealized_pnl` minus the `unrealized_pnl` value
  from the last `paper_nav_snapshots` row strictly before the first day of the current month
  (same "find the last snapshot before period start" query shape `_get_monthly_realized_pnl()`
  already uses for `realized_pnl` — reuse that pattern, don't invent a new one). If there is no
  snapshot before month start (strategy started mid-month), treat the month-start baseline as
  `Decimal("0")`, not `None` — unlike `Bkd (I)`, a missing prior-month baseline here is a normal
  "started this month" case, not a data-integrity gap, so it should not degrade to "N/A".

**Fix:** `ICMonthlyStats` gains `realized_pnl_inception: Decimal` and
`unrealized_pnl_month_change: Decimal`. Row labels: "Unrealized P&L" → "Flt (I)" (existing calc),
plus a new "Flt (M)" row (new calc) — two rows, not one, and they are **not** expected to show the
same value except by coincidence. `build_comparison_report()` row order becomes: `Legs, Credit,
Captured, Put Δ, Call Δ, DTE, Flt (M), Bkd (M), Bkd (I), Flt (I), Lock zone, Adj, Signals` (matches
the revised approved format block above).

**Tests required:**
- Happy path: multi-day `paper_nav_snapshots` fixture spanning a month boundary → `Bkd (I)`
  returns the latest row's `realized_pnl`; `Flt (M)` returns `today.unrealized_pnl -
  last_row_before_month_start.unrealized_pnl`, and that value is asserted to differ from `Flt (I)`
  in the fixture (regression guard against silently re-copying `Flt (I)`'s value)
- Edge case: strategy with zero `paper_nav_snapshots` rows entirely → `Bkd (I)` and `Flt (I)`
  return `None`/"N/A", not a crash or a silently-wrong `Decimal("0")`
- Edge case: strategy with rows only *after* month start (started mid-month, no pre-month-start
  snapshot) → `Flt (M)` baseline is `Decimal("0")` per the spec above, not `None`/"N/A" — assert
  this explicitly, since it's the opposite convention from the zero-rows case above and easy to
  conflate

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

---

## Scope extension (2026-08-07, same session) — broader formatting sweep

**Trigger:** user asked to extend this story beyond the single IC comparison report — "most
messages" have the same class of formatting problem. A repo-wide survey of every
`notifier.send(...)` call site found the hand-counted-fixed-width bug (the one TGFMT-1 fixes)
independently reproduced in 6 other message builders. TGFMT-1..3 above are unchanged — they stay
scoped to `build_comparison_report()` and its financial-field additions. TGFMT-4 onward generalize
the TGFMT-1 fix into a shared helper and retrofit the other sites.

| File | Function | Class | Task |
|---|---|---|---|
| `scripts/strategies/ic/paper_ic_monthly_comparison.py` | `build_comparison_report` | broken (fixed by TGFMT-1) | TGFMT-1 (unchanged) |
| `src/portfolio/formatting.py` | `_format_combined_summary` | broken | TGFMT-5 |
| `src/strategy/auto_close.py` | `_send_close_notification` | broken | TGFMT-6 |
| `scripts/strategies/three_track/paper_3track_snapshot.py` | P&L table prints | broken | TGFMT-7 |
| `scripts/strategies/three_track/paper_3track_overlay_entry.py` | trade-log table | broken | TGFMT-7 |
| `scripts/strategies/three_track/paper_3track_entry.py` | strike-candidate table | broken | TGFMT-7 |
| `scripts/dev/paper_track_snapshot.py` | pnl-line builder | broken | TGFMT-7 |
| _(8 more files — see note below the table)_ | various | prose only, no column alignment | out of scope — nothing to fix |

Out-of-scope files (prose only, no column alignment, nothing to fix):
`src/strategy/collar_overlay_v1.py` / `cc_overlay_v1.py` / `pp_overlay_v1.py`, `paper_3track_roll.py`, `overlay_closer.py`, `position_health_check.py`, `healthcheck.py`, `paper_ic_entry_v2.py`

---

## TGFMT-4 — Extract shared dynamic-width table formatter

**Context:** TGFMT-1 fixes `build_comparison_report()` inline, following the pattern proven in
`scratch/2026-08-07_telegram_ic_comparison_format_repro.py`'s `_build_side_by_side_report()`.
Retrofitting 6 more call sites with independent copies of that logic reintroduces the exact
maintenance problem this story exists to fix — a shared helper is required before any retrofit.

**Sequencing constraint:** run this *after* TGFMT-1 lands (so the extraction is a refactor of
working, tested code, not a parallel implementation that TGFMT-1 then has to reconcile with).

**Files to change:**
- `src/notifications/table_format.py` — new module
- `tests/unit/notifications/test_table_format.py` — new test file
- `scripts/strategies/ic/paper_ic_monthly_comparison.py` — refactor `build_comparison_report()`
  to call the new helper instead of its own inline TGFMT-1 logic (behavior-preserving; existing
  TGFMT-1 tests must stay green unmodified — if they don't, the extraction changed behavior and
  that's a bug in the extraction, not a reason to edit the tests)

**Before any code:**
```
get_code_snippet("build_comparison_report")   # the post-TGFMT-1 implementation to extract from
git log --oneline -10 src/notifications/
```

**Functions to add (module: `src/notifications/table_format.py`):**

```python
def column_width(header: str, cells: list[str]) -> int:
    """Widest of a header and its cell values, for a right-aligned value column.

    Args:
        header: Column header text.
        cells: Rendered cell values for that column (already including any suffix,
            e.g. a warning emoji).

    Returns:
        max(len(header), max(len(c) for c in cells)) — the minimum width that avoids
        truncation or misalignment for this column's actual content.
    """


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a monospace-safe table with dynamically computed column widths.

    Args:
        headers: Column headers; first entry is the (typically blank) label-column
            header.
        rows: Each row is a list of cell strings, same length as headers. First cell
            per row is the row label (left-aligned); remaining cells right-align.

    Returns:
        Newline-joined table text: header row, a `─`-rule row sized to the total
        width, then one line per data row. Never raises. No column width is ever a
        literal — every width comes from `column_width()`.
    """
```

**Tests:**
- `test_column_width_header_wider_than_cells`
- `test_column_width_cell_wider_than_header` — the exact class-A failure mode
- `test_format_table_happy_path`
- `test_format_table_empty_rows`
- `test_format_table_long_label_no_collision` — regression using `"Unrealized(inception)"` /
  `"Realized (inception)"`-length labels, mirroring TGFMT-1's own regression test
- `test_build_comparison_report_unchanged_after_refactor` — run TGFMT-1's existing happy-path
  test byte-for-byte against the refactored function; must still match the approved format block

**Commit:** `refactor(notifications): extract dynamic-width table formatter, used by IC comparison report`

---

## TGFMT-5 — Fix Portfolio Combined Summary (`daily_snapshot.py`)

**Context:** `_format_combined_summary` in `src/portfolio/formatting.py` hardcodes a 14-char
label column and 16-char value column (L164-214, L239, L245); `"├ Nuvama Bonds"` /
`"└ Dhan Equity"` sit right at the edge already. Feeds `scripts/portfolio/daily_snapshot.py`,
which runs daily via cron — a broken layout here recurs every day, not once.

**Files to change:**
- `src/portfolio/formatting.py` — `_format_combined_summary`
- test file covering it — confirm exact filename via `search_code("_format_combined_summary")`
  before assuming; do not guess

**Before any code:**
```
get_code_snippet("_format_combined_summary")
search_code("_format_combined_summary")
git log --oneline -10 src/portfolio/formatting.py
```

**Change:** replace the hardcoded `:<14` / `:>16` literals with a `format_table()` call
(TGFMT-4). Tree-branch prefixes (`├`, `└`) are part of the label string — `column_width()`
measures the final rendered string, so no special-casing needed.

**Tests:**
- `test_format_combined_summary_long_source_name` — a source name longer than 14 chars doesn't
  collide with the value column
- Update existing formatting tests in place to match corrected (still-equivalent for current
  data) output

**Commit:** `fix(portfolio): dynamic-width table fixes daily snapshot label collision`

---

## TGFMT-6 — Fix Auto-Close Notification Alignment

**Context:** `_send_close_notification` in `src/strategy/auto_close.py` fakes a colon column
with hand-counted literal spaces (`"Short Call: "` vs `"Long Put:   "`, `"Signal    :"`,
`"Net P&L   :"`, `"Leg P&L:"`). Highest-consequence site in this scope extension —
`auto_close.py` fires on real capital-affecting close events, not paper/dev tooling.

**Files to change:**
- `src/strategy/auto_close.py` — `_send_close_notification`
- `tests/unit/strategy/test_auto_close.py`

**Before any code:**
```
get_code_snippet("_send_close_notification")
git log --oneline -10 src/strategy/auto_close.py
```

**Change:** this site is a label:value list, not a header+rows table — check whether
`format_table(headers=["", "Value"], rows=...)` renders it correctly before adding any second
helper function to `table_format.py`. Only add a new function if that reuse genuinely doesn't
fit; do not add a near-duplicate out of convenience.

**Tests:**
- `test_send_close_notification_alignment` — one artificially long label (e.g.
  `"Overlay Call Leg"`) alongside short ones in the same message, assert columns/colons still
  line up
- Update existing notification-content tests to match corrected output

**Commit:** `fix(strategy): dynamic-width alignment in auto-close Telegram notification`

---

## TGFMT-7 — Fix Three-Track / Dev Snapshot Table Prints

**Context:** Four call sites share the same hardcoded-width pattern in paper-trading dev
tooling (not live order flow): `paper_3track_snapshot.py` (`:<20`, `:<28`, `:<40`, `:<6`),
`paper_3track_overlay_entry.py` (`:<24`, `:<22`, `:>4`, `:>10`), `paper_3track_entry.py`
(`:<22`, `:<18`, `:>6`), `paper_track_snapshot.py` (`:<22`). Bundled since each is an
independent swap to `format_table()` — no cross-file coupling.

**Files to change:**
- `scripts/strategies/three_track/paper_3track_snapshot.py`
- `scripts/strategies/three_track/paper_3track_overlay_entry.py`
- `scripts/strategies/three_track/paper_3track_entry.py`
- `scripts/dev/paper_track_snapshot.py`
- Corresponding test files under `tests/unit/scripts/` — confirm exact names via `search_code`
  first

**Before any code:**
```
search_code(":<20")   # repeat per file for the specific literal found in the survey
git log --oneline -10 scripts/strategies/three_track/paper_3track_snapshot.py
```

**Change:** same substitution as TGFMT-5/TGFMT-6 — swap each hardcoded print for a
`format_table()` call, file by file. If any one doesn't map cleanly to header+rows, stop and
flag it as a follow-up rather than forcing a bad fit into this commit.

**Tests:** one regression test per file (4 total) — a long-label row doesn't collide with its
value column.

**Commit:** `fix(three-track): dynamic-width table fixes in dev/paper-trading snapshot prints`

---

## TGFMT-8 — Fold Standard Into Existing Docs (no new files)

**Context:** Without a written-down standard, `format_table()` only lives in code, and the next
hand-rolled table reproduces the same bug class again — same rationale as `telegram-leg-labels`
TL-4. Fold into `src/notifications/CLAUDE.md` and add one trigger row to root `CLAUDE.md`.

**Files to change (both existing, targeted `Edit` only — never `Write`):**
- `src/notifications/CLAUDE.md` — add a new section
- `CLAUDE.md` (project root) — add one row to "Additional files to read when relevant"

**Check first:** if `telegram-leg-labels` TL-4 has already landed an "Instrument Label
Formatting" section in `src/notifications/CLAUDE.md`, add this section alongside it, not
replacing it.

**`src/notifications/CLAUDE.md` — new section:**
```
## Tabular Message Formatting

Any Telegram message that renders a label/value table (comparison reports, P&L summaries,
close notifications with multiple fields) must use `format_table()`
(`src/notifications/table_format.py`) — never hand-count column widths with a literal
`:<N`/`:>N` format spec or manual space padding. Column widths must be derived from actual
content via `column_width()`, never assumed from current label lengths.

**Why:** `build_comparison_report()`'s original implementation hand-counted a 20-char label
budget and broke silently the first time a label (`"Unrealized(inception)"`) grew past it — no
error, just misaligned output in production. `format_table()` is correct-by-construction for
any row/label set.

Origin: `docs/plan/telegram-ic-comparison-formatting/` — IC monthly comparison report
misalignment identified 2026-08-07, generalized after a repo-wide survey found the same bug
class in 6 other message builders.
```

**Root `CLAUDE.md` — trigger row to add:**
```
- Building or editing any Telegram message with a label/value table (comparison reports, P&L
  summaries, multi-field close notifications) → also read `src/notifications/CLAUDE.md`
  §"Tabular Message Formatting" — dynamic-width table rule
```

**Commit:** `docs: tabular Telegram formatting standard folded into notifications CLAUDE.md`

---

## TGFMT-9 — Docs Close

**Goal:** Confirm docs updated, add `TODOS.md` session log entry. No further code changes.

**Verify:**
- `CONTEXT.md` — add one clause noting `src/notifications/table_format.py` exists and which
  call sites use it (targeted `Edit`, never rewrite the whole file)
- `CONTEXT_TREE.md` — add the new module
- `TODOS.md` — add one line confirming `telegram-ic-comparison-formatting` TGFMT-1..TGFMT-8
  complete
- `DECISIONS.md` — add one row: dynamic-width table formatting (`format_table()`) is now the
  standard for all tabular Telegram messages, superseding ad hoc per-site hand-counted widths
- `docs/plan/README.md` — update the status column for this story

**Commit:** `docs: telegram-ic-comparison-formatting TGFMT-1..TGFMT-8 session close`

---

## Extended sequencing

TGFMT-1 → TGFMT-2 (parallel-ok) → TGFMT-3 (financial-data change, lands last on stable layout)
→ **TGFMT-4** (extract shared helper, refactor TGFMT-1's fix onto it) → TGFMT-5, TGFMT-6, TGFMT-7
(independent of each other, any order) → TGFMT-8 (docs) → TGFMT-9 (docs close).

TGFMT-6 (`auto_close.py`) carries the financial-logic gate from root `CLAUDE.md`'s AutoTrigger
table (capital-affecting close notification) — same `@code-reviewer` substitution pattern as
TGFMT-3, documented explicitly in the commit message. TGFMT-5 and TGFMT-7 do not touch financial
calculations, only message text — no gate.
