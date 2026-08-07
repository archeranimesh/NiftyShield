# Telegram Markdown Migration — Formatting Rules — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.

---

## FMT-1 — Formatting Spec (decimals, alignment, sign display)

**No code in this task.** Write the spec itself as a short reference table — either a new
section in `src/notifications/CLAUDE.md` or a standalone `FORMATTING.md` at repo root (decide
which during the task by checking whether `src/notifications/CLAUDE.md` is already long enough
that a standalone file reads better; either is acceptable, just pick one and be consistent with
the rest of this epic's docs).

**Proposed rules** (derived from what was actually validated interactively in
`scratch/2026-08-07_ic_eod_audit_telegram_format.py` across several rounds of user feedback —
not invented fresh; confirm against that script's final version, then resolve the one open
inconsistency noted below before finalizing):

| Parameter type | Format | Example | Rationale |
|---|---|---|---|
| Money (premium, credit, margin, P&L) | `Decimal`, 2dp, `,` thousands sep, `₹` prefix | `₹86.68`, `₹82,628` | Project invariant: monetary fields are always `Decimal`, never `float` (`CLAUDE.md` Data Layer rule). Margin happens to always be whole rupees in practice but format as 2dp for consistency, not a special case. |
| Strike price | Integer, no decimal | `23000` | Strikes are always whole numbers on NSE; a trailing `.0` is visual noise (same rule `format_option_label` already applies in `src/instruments/lookup.py`, TL-1 — reuse that convention, don't reinvent it). |
| Greeks (delta; extend to gamma/theta/vega when those appear in a message) | 2dp, always signed (`+`/`-`), `-` placeholder when not applicable to a leg (e.g. long legs with no delta figure in the source data) | `+0.28`, `-0.03`, `-` | Matches existing Greeks-analyst convention in trading vocabulary; explicit sign disambiguates short/long-side delta at a glance. |
| LTP | 2dp | `₹9.30` | **Open inconsistency to resolve in this task:** the scratch script used 2dp in the key/value table version but 1dp (`9.3`) in the final compact fenced-table version, purely to save horizontal width on a narrow mobile screen. Pick one canonical default (2dp, matching money) for `format_money`-driven LTP; the compact table MAY still override to 1dp locally as a deliberate width-saving exception IF `strategy-rollout/` decides that table needs it — document that as an explicit exception in the table-builder's docstring (FMT-3), not a silent inconsistency. |
| DTE, Open legs, quantities | Integer | `18`, `4` | Whole units, no formatting needed. |
| IVR | 2dp, unitless | `0.16` | Matches how it's already displayed in existing option-chain analysis. |
| Percentages (Captured %, ROI %) | 1dp | `4%`, `0.2%` | One decimal is enough precision for a percentage-of-credit figure; 2dp reads as false precision on numbers this small. |

**Tests:** none — docs-only task.

**Commit:** `docs(notifications): Telegram message formatting spec`

---

## FMT-2 — Value Formatters

**Files to change:**
- `src/notifications/formatting.py` — new module
- `tests/unit/notifications/test_formatting.py` — new test file

**Before any code:** re-read FMT-1's finalized spec (this task implements it, does not
redefine it). If FMT-1 left the LTP inconsistency unresolved for any reason, resolve it now —
do not implement two silently-different LTP formatters.

**Functions to add** (signatures — implement per FMT-1's finalized table):

```python
def format_money(value: Decimal) -> str:
    """Format a monetary value per project convention: 2dp, comma thousands, ₹ prefix.

    Args:
        value: Decimal amount. Never accepts float — see CLAUDE.md Data Layer rule;
               a float argument should raise TypeError, not silently coerce.

    Returns:
        e.g. Decimal("82628") -> "₹82,628.00", Decimal("86.68") -> "₹86.68".
    """


def format_greek(value: float | None, *, width: int | None = None) -> str:
    """Format a Greek value: 2dp, always signed, '-' placeholder for None.

    Args:
        value: Greek value (e.g. delta), or None if not applicable to this leg.
        width: Optional right-align width for use inside a fixed-width table column
               (see build_leg_table in FMT-3 — this lets the table helper avoid
               reimplementing the signed-format logic itself).

    Returns:
        e.g. -0.03 -> "-0.03", 0.28 -> "+0.28", None -> "-".
    """


def format_strike(value: float | int) -> str:
    """Format a strike price as an integer string, no decimal.

    Args:
        value: Strike price. Always a whole number for NSE options but may arrive
               as float from upstream data — this function is the single place
               that decision gets made, not scattered across callers.

    Returns:
        e.g. 23000.0 -> "23000".
    """


def format_pct(value: float) -> str:
    """Format a percentage value at 1dp.

    Args:
        value: Percentage as a plain number (4 means 4%, not 0.04).

    Returns:
        e.g. 4 -> "4%" (no decimal shown when the value is a whole number — confirm
        this against FMT-1's example row "4%" vs "0.2%"; if inconsistent, 1dp always
        shown, e.g. "4.0%", is the simpler and more defensible default — resolve
        during implementation and update FMT-1's doc to match whichever is chosen).
    """
```

**Tests (happy-path + edge case per function, per project standard):**
- `format_money`: `Decimal("86.68")` happy path; `Decimal("0")` edge case; float argument raises `TypeError`
- `format_greek`: `0.28` happy path (positive sign shown); `None` edge case (`"-"`); `-0.03` (negative sign)
- `format_strike`: `23000.0` happy path; `0` edge case (unlikely in practice but must not crash)
- `format_pct`: whole-number happy path; `0.0` edge case

**Commit:** `feat(notifications): value formatters for Telegram messages`

---

## FMT-3 — Table-Builder Helpers

**Files to change:**
- `src/notifications/formatting.py` — extend with table builders
- `tests/unit/notifications/test_formatting.py` — extend

**Before any code:** read the final versions of `_kv_table`, `_side_by_side_kv`, and
`_leg_table` in `scratch/2026-08-07_ic_eod_audit_telegram_format.py` — these are working,
user-validated reference implementations (went through several rounds of feedback: dynamic
width computation, blank-row padding for mismatched row counts, plain-text `[S]`/`[B]` badges
instead of emoji because colour-circle emoji are double-width and break monospace alignment).
Port and generalize, do not redesign.

**Functions to add** (promote from scratch, generalize signatures, use FMT-2's formatters
internally rather than ad hoc f-string formatting):

```python
def build_kv_table(title: str, rows: list[tuple[str, str]]) -> str:
    """Bordered two-column label/value table, dynamic width, 'Value' header."""


def build_side_by_side_kv_table(
    title_a: str, rows_a: list[tuple[str, str]],
    title_b: str, rows_b: list[tuple[str, str]],
) -> str:
    """Two kv tables side by side joined with ' | '. Pads the shorter side with
    blank rows so both columns stay aligned when row counts differ."""


def build_leg_table(legs: list[LegRow]) -> str:
    """Fenced-code-block-ready position table: [S]/[B] badge, instrument, Δ, LTP,
    entry — right-aligned numerics via format_greek/format_money. `LegRow` — define
    as a small dataclass/TypedDict here rather than accepting raw dicts, per project
    convention (dataclasses/Pydantic for structured shapes, CLAUDE.md Python Standards).
    Caller wraps the return value in a ```fenced block``` — this function does not add
    the fence itself, keeping it reusable for non-Telegram output (e.g. plain console
    printing) too."""
```

**Known bug class this must not repeat:** `build_comparison_report()`
(`scripts/strategies/ic/paper_ic_monthly_comparison.py`) hand-counts a fixed 20-char label
budget, which broke the first time a label was longer than counted. Every width here MUST be
`max(len(x) for x in ...)`, never a literal constant.

**Tests:**
- `build_kv_table`: happy path (3+ rows, varying label lengths); empty rows list edge case
  (should not crash — decide and document the correct degenerate output, e.g. header + separator
  with no data rows, or raise `ValueError` — pick one, don't leave it undefined)
- `build_side_by_side_kv_table`: mismatched row counts (4 vs 5, matching the real Snapshot/P&L
  case) pad correctly; equal row counts (no padding needed)
- `build_leg_table`: happy path with mixed short/long legs (some with delta/entry, some
  without — `None` handling via `format_greek`); single-leg edge case

**Commit:** `feat(notifications): table-builder helpers for Telegram messages`

---

## FMT-4 — Docs Close

**Files to change (targeted `Edit`, never `Write`):**
- `src/notifications/CLAUDE.md` — document the new `formatting.py` module and its functions
- `CONTEXT.md` — module tree: add `src/notifications/formatting.py`
- `TODOS.md` — session log entry

**Commit:** `docs(notifications): record formatting-rules module`
