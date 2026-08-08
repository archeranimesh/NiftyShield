# Telegram Markdown Migration — Formatting Rules — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.

---

## FMT-1 — Formatting Spec (decimals, alignment, sign display)

**No code in this task.** Write the spec itself as a short reference table — either a new
section in `src/notifications/CLAUDE.md` or a standalone `FORMATTING.md` at repo root (decide
which during the task by checking whether `src/notifications/CLAUDE.md` is already long enough
that a standalone file reads better; either is acceptable, just pick one and be consistent with
the rest of this epic's docs).

**Rules** (derived from what was actually validated interactively in
`scratch/2026-08-07_ic_eod_audit_telegram_format.py` across several rounds of user feedback —
not invented fresh; confirm against that script's final version):

| Parameter type | Format | Example | Rationale |
|---|---|---|---|
| Money (premium, credit, margin, P&L) — `format_money` default | `Decimal`, 2dp, `,` thousands sep, `₹` prefix | `₹86.68`, `₹82,628` | Project invariant: monetary fields are always `Decimal`, never `float` (`CLAUDE.md` Data Layer rule). Margin happens to always be whole rupees in practice but format as 2dp for consistency, not a special case. |
| Strike price | Integer, no decimal | `23000` | Strikes are always whole numbers on NSE; a trailing `.0` is visual noise (same rule `format_option_label` already applies in `src/instruments/lookup.py`, TL-1 — reuse that convention, don't reinvent it). |
| Greeks (delta; extend to gamma/theta/vega when those appear in a message) | 2dp, always signed (`+`/`-`), `-` placeholder when not applicable to a leg (e.g. long legs with no delta figure in the source data) | `+0.28`, `-0.03`, `-` | Matches existing Greeks-analyst convention in trading vocabulary; explicit sign disambiguates short/long-side delta at a glance. |
| LTP / Entry — `format_money` default (2dp) | 2dp | `₹9.30` | Matches money default everywhere `format_money` is used directly (kv tables, prose lines). |
| LTP / Entry — **inside `build_leg_table` specifically** | 1dp, locked-in exception | `9.3` | **Resolved 2026-08-07** (confirmed with Animesh): 1dp is a deliberate width-saving override for this one table, not a silent inconsistency — narrow mobile screens can't afford 2dp across 4 numeric columns plus a Δ column in a fenced code block. `build_leg_table` must document this explicitly in its own docstring as an override of `format_money`'s default, not call `format_money` for these two columns — use a local 1dp format instead. Every other caller of LTP/Entry (e.g. a future single-leg close notification, `strategy-rollout/` ROLL-3) uses the 2dp default unless it has the same mobile-table width constraint. |
| DTE, Open legs, quantities | Integer | `18`, `4` | Whole units, no formatting needed. |
| IVR | 2dp, unitless | `0.16` | Matches how it's already displayed in existing option-chain analysis. |
| Percentages (Captured %, ROI %) | 1dp; whole numbers print with no trailing `.0` | `3%`, `2.7%`, `0.2%` | One decimal is enough precision for a percentage-of-credit figure; 2dp reads as false precision on numbers this small. Resolves the ambiguity FMT-2's original docstring flagged ("4" -> "4%" vs "4.0%") — whole-number inputs print bare, fractional inputs get 1dp. Confirmed via `format_pct` in `scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py`. |
| Money — negative values (loss states) | Sign BEFORE the `₹` symbol, not after | `-₹11.08`, not `₹-11.08` | **Added 2026-08-07** (ROLL-1 scratch iteration, `scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py`). A naive `f"₹{value:,.2f}"` puts Python's sign after the literal `₹` prefix for negative `Decimal`s, which reads wrong typographically. FMT-1's original table only had positive examples, so this case was unspecified — worth locking in now, before any message actually shows a loss state, so FMT-2's real `format_money` doesn't ship the naive version and need a follow-up fix. |
| Expiry date — `format_expiry` | `dd Mon yy`, no leading zero on day | `25 Aug 26`, `5 Aug 26` | **Added 2026-08-07** (ROLL-1, `scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py`) — expiry was previously resolved (for DTE) but never displayed anywhere. `strftime("%d %b %y").lstrip("0")`, not `%-d` (platform-dependent, fails on some Windows builds). Source is the `expiry` date object `process_variant()` already resolves via the BOD instrument lookup — DTE is derived FROM it, so never reconstruct expiry from DTE in the real implementation. |

**Tests:** none — docs-only task.

**Commit:** `docs(notifications): Telegram message formatting spec`

---

## FMT-1d — Money — Multi-Strategy Summary Table Exception (confirmed 2026-08-08)

**Not in the original FMT-1 table.** Surfaced during the EOD Paper Summary workshop session
(`message-format-workshop.md`, `scratch/2026-08-08_eod_paper_summary_format.py`) — the same
class of override `build_leg_table`'s 1dp exception already established (FMT-1's LTP/Entry row),
applied to money instead of decimal precision.

| Context | Format | Example | Rationale |
|---|---|---|---|
| Money inside a **multi-strategy summary table** (8+ rows, 3+ numeric columns) | Signed integer, comma thousands sep, **no `₹` prefix per cell** | `+11,024`, `-1,169`, `0` (bare, no sign) | `format_money`'s 2dp + `₹`-per-cell default does not fit 8 strategy rows × 3 numeric columns in a fixed-width monospace block under Telegram's mobile line-wrap limit. `₹` appears exactly once, on the message's Total P&L summary line, not per table cell. |

This is a table-specific override, not a general relaxation of the Decimal/2dp money rule —
`format_money`'s 2dp default with `₹` prefix still applies everywhere else (kv tables, prose
lines, single-value messages). Any new function implementing this exception must document it
explicitly in its own docstring as an override, the same discipline `build_leg_table` already
follows for its 1dp exception — never call `format_money` for these cells and then strip its
output.

**Terminology note (also confirmed 2026-08-08):** column headers for unrealized/realized P&L in
this table use `Flt`/`Bkd` (floating / booked), reusing `ROLL-2`'s "Flt P&L (M)" / "Bkd P&L (I)"
vocabulary rather than inventing new abbreviations for the same underlying values. Any future
message showing unrealized/realized P&L side by side should default to `Flt`/`Bkd` for
consistency, not re-derive its own short forms.

**Commit (when promoted):** fold into whichever commit promotes
`scratch/2026-08-08_eod_paper_summary_format.py`'s table builder into
`src/notifications/formatting.py` (see `strategy-rollout/` ROLL-6).

---

## FMT-1b — Dynamic Status Emojis (confirmed 2026-08-07, surfaced during ROLL-1 scratch iteration)

**Not in the original FMT-1 scope** — added after a Cowork session workshopped the IC EOD audit
message and wanted P&L/alert state reflected visually, not just as static emoji baked into the
template (the original prototype hardcoded `✅`/`⚠️` regardless of the actual data). Two small
helper functions, promoted from `scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py`:

```python
def pnl_emoji(amount: Decimal) -> str:
    """>0 -> '✅', <0 -> '🔻', ==0 -> '➖'."""

def alert_emoji(signals: list[str]) -> str:
    """Empty list -> '🟢', non-empty -> '⚠️'."""
```

**Rejected design, and why:** an external suggestion proposed selecting the alert emoji by
substring-matching the signal code (`if "WARN" in signal: ...`). Rejected — this couples display
logic to a naming convention that isn't guaranteed stable (a future code like
`GAMMA_RISK_ACTION` wouldn't contain `"WARN"` but would be a worse severity than one that does).
`alert_emoji` as specified above is presence-based only (any signal present -> warning), which is
correct for what the current message data actually carries.

**Deferred, not resolved:** a real three-tier severity indicator (🟢 info / ⚠️ warn / 🚨 action)
needs the actual `ExitSignalResult.severity` enum value threaded through from
`ExitSignalEngine` into whatever builds the EOD audit message — the current `paper_ic_snapshot.py`
message-building function's data shape does not yet carry that field. Do not fake this by
substring-matching the signal code name as a severity proxy. This is real scope for whichever
task (likely inside `ROLL-1`'s real port, or a follow-on) wires the message-building function to
`ExitSignalEngine`'s output — flag it explicitly if `ROLL-1`'s real implementation turns out not
to have that severity value available, rather than silently downgrading to presence-only forever.

**Files to change (when promoted from scratch, not yet done):**
- `src/notifications/formatting.py` — add `pnl_emoji`, `alert_emoji` alongside FMT-2's other
  formatters
- `tests/unit/notifications/test_formatting.py` — happy-path + edge case per function
  (`pnl_emoji`: positive/negative/zero; `alert_emoji`: empty list/single signal/multiple signals)

**Commit (when promoted):** `feat(notifications): dynamic P&L/alert status emojis`

---

## FMT-1c — Timeframe Color/Emoji Header + Hashtag (confirmed 2026-08-07, on-device verified)

**Problem:** running all five active IC EOD audit variants (V1 weekly/monthly/leaps/yearly + V2
monthly) side by side in one Telegram chat, they were visually near-identical — same `📊` emoji,
same generic header shape — creating real alert-fatigue risk during a busy session (easy to
misread which variant a message belongs to at a glance). Surfaced and confirmed via
`message-format-workshop.md`, built and iterated in
`scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py`, **hashtag auto-detection confirmed
working live on-device 2026-08-07** (the one previously-flagged unverified assumption — MarkdownV2
escaping the `#`/`_` in the hashtag's source text does not prevent Telegram's own hashtag
auto-detection from firing on the de-escaped rendered text).

**Design decision — color/emoji encode TIMEFRAME only, never version.** An external suggestion
proposed 4 distinct colors for 4 example variants, one of which (purple) was assigned specifically
to "v2 monthly" — i.e. color encoding *version*, not timeframe, for that one case. Rejected: this
conflates two independent axes onto one visual channel and doesn't scale — the moment V2 gains a
second expiry bucket (plausible; `CONFIGS_V2` is explicitly scoped "Phase 1, monthly only" per
`src/strategy/ic_expiry_config_v2.py`, implying more phases), you'd need an entirely new color set
rather than reusing the existing timeframe colors. The chosen design instead keeps color+emoji as
a pure timeframe indicator (scales to any number of versions sharing a timeframe) and encodes
version as a separate, orthogonal text badge in the bold title. Also note the original external
proposal's example set only covered 3 of V1's 4 real expiry buckets and omitted `yearly` entirely
(confirmed via `ICExpiryConfig`'s real `weekly`/`monthly`/`leaps`/`yearly` presets,
`src/paper/constants.py`'s `STRATEGY_IC_WEEKLY/MONTHLY/LEAPS/YEARLY`) — an omission that would
have silently recreated the exact ambiguity this scheme exists to fix for that one variant.

**Confirmed timeframe → color/emoji mapping:**

| Timeframe | Color | Emoji | Rationale |
|---|---|---|---|
| Weekly | 🟡 | ⚡ | Fastest-moving, highest gamma risk, needs the most frequent attention. |
| Monthly | 🔵 | 📅 | Standard calendar-cycle expiry — the "default" tier, calmest color. |
| Leaps | 🟢 | 🔭 | Long-dated (46–200 DTE per `ICExpiryConfig`), low day-to-day maintenance. |
| Yearly | 🟠 | 🌌 | Longest horizon (201–420 DTE) — distinct from Leaps, not reused/blended. |

**Version badge (orthogonal to color):** `V1` is implicit (no badge — matches the existing
convention where the common case stays visually quiet); any non-`V1` version appends
`\(V2\)`/etc. to the bold title text, escaped per MarkdownV2. Confirmed hashtag format:
`#IC_{Timeframe}_{Version}` (e.g. `#IC_Weekly_V1`, `#IC_Monthly_V2`) — `Leaps` renders as `LEAPS`
in the hashtag specifically (conventional acronym capitalization), all other timeframes
title-case. **Hashtag must NOT be wrapped in a code span** — Telegram does not parse any entities,
including its own auto-detected hashtags, inside `` ` `` /``` ``` ``` — an earlier draft of the
external proposal showed the hashtag inside backticks, which would have silently made it
non-tappable while looking correct in a screenshot. The existing `` `{strategy_id}` `` code-span
line is kept as a *separate* line below the title — it serves a different job (exact-string
copy/grep for audit trails) than the hashtag (native Telegram tap-to-filter across chat history);
collapsing them into one loses one of the two purposes.

**Confirmed header shape (2 lines, replaces the single-emoji header in `ROLL-1`'s original
confirmed layout):**

```
🔵 📅 *IC EOD Audit — Monthly \(V2\)* \| \#IC\_Monthly\_V2
`paper_ic_nifty_v2_monthly`
```

(Backslash escaping shown as actual MarkdownV2 source; renders as clean bold text + a live
hashtag + a monospace code span.)

**Files to change (when promoted from scratch, not yet done):** this is IC-specific (timeframe
naming, `STRATEGY_IC_*` variants) rather than a generic cross-strategy formatter, so it likely
does **not** belong in `src/notifications/formatting.py` alongside FMT-2/FMT-3's
strategy-agnostic helpers — a judgment call for whoever implements this to make explicitly (e.g.
a new `_build_header()`/`TIMEFRAME_META` inside `scripts/strategies/ic/paper_ic_snapshot.py`
itself, colocated with `process_variant()`, rather than exported as a reusable notifications
helper). Do not default to `src/notifications/formatting.py` without considering this — flag the
decision in the implementation commit either way.
- `scripts/strategies/ic/paper_ic_snapshot.py` — new header-building logic (function name/location
  per the above judgment call), wired into `process_variant()`'s report construction
- `tests/unit/strategies/ic/test_paper_ic_snapshot.py` — one test per timeframe asserting the
  correct color/emoji/hashtag combination, plus one asserting the `V1`-is-implicit /
  non-`V1`-gets-a-badge rule

**Tests:**
- `test_header_weekly_color_emoji` / `..._monthly...` / `..._leaps...` / `..._yearly...` — each
  asserts the exact `(color, emoji)` pair for its timeframe
- `test_header_v1_has_no_version_badge` — title text contains no `\(V1\)` or similar
- `test_header_v2_has_version_badge` — title text contains the escaped `\(V2\)` badge
- `test_hashtag_not_wrapped_in_code_span` — regression test for the exact bug this task's design
  section calls out; assert the hashtag line contains no backtick characters
- `test_hashtag_escapes_reserved_chars` — `#`/`_` in the raw hashtag are backslash-escaped in the
  constructed message (same regression-test shape MD-1/ROLL-1 already use for `mdcode()`)

**Commit (when promoted):** `feat(ic): timeframe color-coded headers + hashtags for EOD audit`

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
    entry — right-aligned numerics via format_greek for Δ. `LegRow` — define as a
    small dataclass/TypedDict here rather than accepting raw dicts, per project
    convention (dataclasses/Pydantic for structured shapes, CLAUDE.md Python Standards).

    LTP/Entry columns: 1dp, NOT format_money's 2dp default — locked-in exception
    (resolved 2026-08-07, see FMT-1's spec table) to fit 4 numeric columns + Δ on a
    narrow mobile screen inside a fenced code block. Use a local `f"{value:.1f}"`
    here, not format_money(), and say so in this function's own docstring so a
    future reader doesn't "fix" it into a money-formatter call. None -> right-aligned
    "-", same convention as format_greek's None handling — do not duplicate that
    logic ad hoc, reuse format_greek's None branch shape for consistency even though
    Entry isn't itself a Greek.

    Caller wraps the return value in a ```fenced block``` — this function does not add
    the fence itself, keeping it reusable for non-Telegram output (e.g. plain console
    printing) too.
    """
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
