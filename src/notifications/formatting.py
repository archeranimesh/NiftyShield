"""Value formatters for notifications."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


def format_money(value: Decimal) -> str:
    """2dp, comma thousands, ₹ prefix, sign before ₹ on negatives.

    Never accepts float — a float argument must raise TypeError, not silently coerce.
    Decimal("82628") -> "₹82,628.00", Decimal("86.68") -> "₹86.68",
    Decimal("-11.08") -> "-₹11.08".
    """
    if isinstance(value, float):
        raise TypeError("format_money requires Decimal, not float")

    if not isinstance(value, Decimal):
        value = Decimal(value)

    is_negative = value < 0
    abs_val = abs(value)

    formatted_num = f"{abs_val:,.2f}"

    if is_negative:
        return f"-₹{formatted_num}"
    return f"₹{formatted_num}"


def format_greek(value: float | None, *, width: int | None = None) -> str:
    """2dp, always signed, '-' placeholder for None (not-applicable, not zero).

    width: optional right-align width for FMT-3's build_leg_table to reuse later.
    -0.03 -> "-0.03", 0.28 -> "+0.28", None -> "-".
    """
    if value is None:
        base_str = "-"
    else:
        base_str = f"{value:+.2f}"

    if width is not None:
        return f"{base_str:>{width}}"
    return base_str


def format_strike(value: float | int) -> str:
    """Integer string, no decimal, no thousands separator (identifier, not quantity).

    23000.0 -> "23000". Reuse format_option_label's existing strike convention
    (src/instruments/lookup.py) rather than inventing a new one.
    """
    if not float(value).is_integer():
        raise ValueError(f"format_strike requires an integer or whole-number float, got {value}")
    return str(int(value))


def format_pct(value: float) -> str:
    """1dp; value is a plain number where 4 means 4%, not 0.04.

    Whole numbers print bare (no trailing .0): 4 -> "4%".
    """
    if float(value).is_integer():
        return f"{int(value)}%"
    return f"{value:.1f}%"


def format_expiry(value: date) -> str:
    """`%d %b %y`, uppercase, leading zero kept (FMT-1, FORMATTING.md §3).

    25 AUG 26 / 07 JUL 26. Matches the shipped `format_option_label()`
    (`src/instruments/lookup.py`, TL-1) rather than the earlier
    title-case-plus-lstrip("0") draft (`scratch/2026-08-07_ic_eod_audit_v2_
    telegram_format.py::format_expiry`) -- a variable-width day field
    misaligns any fenced column carrying an expiry, and two renderings of
    the same date inside one message reads as a bug to the recipient.
    `%-d` stays banned (platform-dependent); moot here since nothing is
    stripped.
    """
    return value.strftime("%d %b %y").upper()


def pnl_emoji(amount: Decimal) -> str:
    """Presence/sign-based P&L indicator, not a severity tier (FMT-1b, FORMATTING.md §10).

    >0 -> '\u2705', <0 -> '\U0001f53b', ==0 -> '\u2796'. Deliberately does NOT
    substring-match a signal code name (e.g. `if "WARN" in signal`) -- that
    couples display logic to a naming convention that is not guaranteed
    stable (a future code like GAMMA_RISK_ACTION would not contain "WARN"
    but would be a worse severity than one that does).
    """
    if amount > 0:
        return "\u2705"
    if amount < 0:
        return "\U0001f53b"
    return "\u2796"


def alert_emoji(signals: list[str]) -> str:
    """Presence-based alert indicator (FMT-1b, FORMATTING.md §10).

    Empty list -> '\U0001f7e2', non-empty -> '\u26a0\ufe0f'. A real three-tier
    severity indicator (info/warn/action) needs `ExitSignalResult.severity`
    threaded through from `ExitSignalEngine` into the caller's data shape --
    not available yet at any current call site. Do not fake a third tier by
    substring-matching the signal code name; flag it explicitly if a future
    caller needs real severity rather than silently downgrading to
    presence-only forever.
    """
    return "\U0001f7e2" if not signals else "\u26a0\ufe0f"


@dataclass(frozen=True)
class LegRow:
    """One row of input for build_leg_table.

    role: e.g. "Short Put" / "Long Call" — whether it starts with "Short"
        or "Long" determines the [S]/[B] badge; the rest of the string is
        not otherwise used by the table (the option identity lives in
        `instrument`).
    instrument: pre-formatted instrument label, e.g. "23000 PE"
        (typically `f"{format_strike(strike)} {opt_type}"`).
    delta: Greek delta for this leg, or None if not applicable (e.g. a
        naked long leg with no chain-derived delta on hand).
    ltp: last traded price.
    entry: entry price, or None (e.g. legs whose entry fill wasn't
        captured).
    """

    role: str
    instrument: str
    delta: float | None
    ltp: float
    entry: float | None


def build_kv_table(title: str, rows: list[tuple[str, str]]) -> str:
    """Bordered two-column label/value table, dynamic width, 'Value' header.

    Width is computed from the actual label/value strings
    (max(len(x) for x in ...)) — never a hand-counted constant, per
    FMT-3's stories.md (the exact bug class that broke
    build_comparison_report()'s original fixed 20-char budget).

    Degenerate case: an empty `rows` raises ValueError. A kv table with a
    title but nothing to show is a caller bug, not a valid empty table —
    silently rendering just a header/border would hide that.

    Caller wraps the return value in a ```fenced block``` — this function
    does not add the fence itself, same convention as build_leg_table.
    """
    if not rows:
        raise ValueError("build_kv_table requires at least one row")

    label_w = max(len(label) for label, _ in rows)
    value_w = max(len("Value"), *(len(value) for _, value in rows))

    header = f"{'':<{label_w}} {'Value':>{value_w}}"
    rule = "-" * len(header)

    lines = [title, rule, header, rule]
    for label, value in rows:
        lines.append(f"{label:<{label_w}} {value:>{value_w}}")
    lines.append(rule)
    return "\n".join(lines)


def build_side_by_side_kv_table(
    title_a: str,
    rows_a: list[tuple[str, str]],
    title_b: str,
    rows_b: list[tuple[str, str]],
) -> str:
    """Two kv tables side by side, joined with ' | '. Pads the shorter
    side with blank rows so both columns stay aligned when row counts
    differ (the real Snapshot/P&L case — see FMT-3's stories.md).

    Built on top of build_kv_table rather than reimplementing its width/
    border logic, so both stay in sync automatically.
    """
    table_a = build_kv_table(title_a, rows_a).split("\n")
    table_b = build_kv_table(title_b, rows_b).split("\n")

    width_a = max(len(line) for line in table_a)
    width_b = max(len(line) for line in table_b)

    max_len = max(len(table_a), len(table_b))
    table_a += [""] * (max_len - len(table_a))
    table_b += [""] * (max_len - len(table_b))

    return "\n".join(
        f"{a:<{width_a}} | {b:<{width_b}}" for a, b in zip(table_a, table_b, strict=True)
    )


def build_leg_table(legs: list[LegRow]) -> str:
    """Fenced-code-block-ready position table: [S]/[B] badge, instrument,
    Δ, LTP, entry — right-aligned numerics via format_greek for Δ.

    LTP/Entry columns: 1dp, NOT format_money's 2dp default — locked-in
    exception (resolved 2026-08-07, see FORMATTING.md §3) to fit the
    numeric columns on a narrow mobile screen inside a fenced code block.
    Uses a local f"{value:.1f}" here, not format_money() — do not "fix"
    this into a money-formatter call. Entry's None -> right-aligned "-"
    reuses format_greek's None-branch shape for consistency, even though
    Entry isn't itself a Greek.

    Caller wraps the return value in a ```fenced block``` — this function
    does not add the fence itself, keeping it reusable for non-Telegram
    output (e.g. plain console printing) too.
    """
    if not legs:
        raise ValueError("build_leg_table requires at least one leg")

    rows = []
    for leg in legs:
        badge = "[S]" if leg.role.startswith("Short") else "[B]"
        delta_str = format_greek(leg.delta)
        ltp_str = f"{leg.ltp:.1f}"
        entry_str = f"{leg.entry:.1f}" if leg.entry is not None else "-"
        rows.append((badge, leg.instrument, delta_str, ltp_str, entry_str))

    widths = {
        "act": max(len("Act"), *(len(r[0]) for r in rows)),
        "instrument": max(len("Instrument"), *(len(r[1]) for r in rows)),
        "delta": max(len("Δ"), *(len(r[2]) for r in rows)),
        "ltp": max(len("LTP"), *(len(r[3]) for r in rows)),
        "entry": max(len("Entry"), *(len(r[4]) for r in rows)),
    }

    header = (
        f"{'Act':<{widths['act']}} {'Instrument':<{widths['instrument']}} "
        f"{'Δ':>{widths['delta']}} {'LTP':>{widths['ltp']}} "
        f"{'Entry':>{widths['entry']}}"
    )
    lines = [header, "-" * len(header)]
    for act, instrument, delta_str, ltp_str, entry_str in rows:
        lines.append(
            f"{act:<{widths['act']}} {instrument:<{widths['instrument']}} "
            f"{delta_str:>{widths['delta']}} {ltp_str:>{widths['ltp']}} "
            f"{entry_str:>{widths['entry']}}"
        )
    return "\n".join(lines)


# --- ROLL-2a: display-width-aware comparison table (FMT-3 promotion of
# scratch/2026-08-07_ic_monthly_comparison_telegram_format.py's
# build_compare_table, see FORMATTING.md §7 and strategy-rollout/stories.md
# ROLL-2a) ---

_CONFIRMED_NARROW_NON_ASCII = {
    "\u0394",  # Δ — confirmed no alignment break since ROLL-1 (2026-08-07), FORMATTING.md §7
    "\u20b9",  # ₹ — confirmed no alignment break, on-device check 2026-08-26 (ROLL-2a pre-check)
}


def _char_display_width(ch: str) -> int:
    """1 for ASCII and individually-confirmed-safe non-ASCII symbols, 2 otherwise.

    FMT-1e (FORMATTING.md §7): a symbol with a Unicode emoji-presentation
    variant renders double-width inside a Telegram fence and breaks
    len()-based alignment — confirmed for `▶` and, on-device 2026-08-26
    (ROLL-2a's blocking pre-check), for `🔴`. §7 explicitly forbids
    extending the safe list by analogy, so any character NOT in
    `_CONFIRMED_NARROW_NON_ASCII` is treated as width-2 (fail-safe wide)
    rather than assumed narrow — a deliberate default, not a placeholder
    pending future confirmation of more characters.
    """
    if ord(ch) < 128:
        return 1
    if ch in _CONFIRMED_NARROW_NON_ASCII:
        return 1
    return 2


def _display_width(s: str) -> int:
    """Sum of _char_display_width over every character in s."""
    return sum(_char_display_width(ch) for ch in s)


def _pad_display(s: str, width: int, *, align: str) -> str:
    """Pad s to `width` display columns (not characters), left or right.

    `align` is `"<"` (left, pad trails) or `">"` (right, pad leads) —
    mirrors str.format's alignment specifiers, since format specs
    themselves pad by character count and would misalign a cell holding
    a width-2 glyph.
    """
    pad = max(0, width - _display_width(s))
    if align == "<":
        return s + " " * pad
    return " " * pad + s


def build_compare_table(groups: list[list[tuple[str, str, str]]], columns: tuple[str, str]) -> str:
    """Fenced-code-block-ready comparison table, one or more row groups
    separated by a dashed rule (FMT-3 promotion of the scratch reference
    implementation confirmed 2026-08-07 for ROLL-2's IC monthly comparison
    message — see strategy-rollout/stories.md ROLL-2a).

    Args:
        groups: list of row-groups; each row is (label, v1_str, v2_str).
            Every group and the overall groups list must be non-empty —
            a comparison table with a header and nothing else is a caller
            bug, not a valid empty table (same convention as build_kv_table).
        columns: the two column headers (e.g. ("V1", "V2")).

    Width is computed via `_display_width` (max across ALL rows in ALL
    groups), never `len()` and never a hand-counted constant — `len()`
    alone is the exact bug class FMT-3's stories.md flags from
    `build_comparison_report()`'s pre-fix history (hand-counted 20-char
    budget), and would additionally misalign any row holding a
    double-width glyph (see `_char_display_width`) — e.g. ROLL-2c's Legs
    row's `🔴` suffix.

    Caller wraps the return value in a ```fenced block``` — this function
    does not add the fence itself, same convention as build_leg_table.
    """
    if not groups:
        raise ValueError("build_compare_table requires at least one group")
    if any(not group for group in groups):
        raise ValueError("build_compare_table groups must each be non-empty")

    all_rows = [row for group in groups for row in group]

    label_w = max(_display_width("Metric"), *(_display_width(r[0]) for r in all_rows))
    v1_w = max(_display_width(columns[0]), *(_display_width(r[1]) for r in all_rows))
    v2_w = max(_display_width(columns[1]), *(_display_width(r[2]) for r in all_rows))

    header = (
        f"{_pad_display('Metric', label_w, align='<')} "
        f"{_pad_display(columns[0], v1_w, align='>')} "
        f"{_pad_display(columns[1], v2_w, align='>')}"
    )
    rule = "-" * _display_width(header)

    lines = [header, rule]
    for i, group in enumerate(groups):
        for label, v1, v2 in group:
            lines.append(
                f"{_pad_display(label, label_w, align='<')} "
                f"{_pad_display(v1, v1_w, align='>')} "
                f"{_pad_display(v2, v2_w, align='>')}"
            )
        if i < len(groups) - 1:
            lines.append(rule)
    lines.append(rule)
    return "\n".join(lines)


# --- ROLL-6: multi-strategy summary table (FMT-1d, FORMATTING.md §§ 5 / 12 —
# promotion of scratch/2026-08-08_eod_paper_summary_format.py's build_strategy_table
# and format_summary_money) ---


@dataclass(frozen=True)
class StrategyPnLRow:
    """One strategy's floating / booked P&L for build_strategy_table (FMT-1d, §12).

    label: display label, bucket-prefix-free (e.g. "V1 Wkly", not "IC V1 Wkly") —
        the bucket's own total row already establishes context (§12).
    bucket: bucket this row belongs to; must be present in build_strategy_table's
        `bucket_order` argument or the call raises ValueError (a strategy with no
        bucket assignment must fail loudly, not silently drop from the summary).
    floating: unrealized (mark-to-market) P&L.
    booked: realized P&L — since-inception, cycle-safe (the caller must source this
        from get_strategy_realized_pnl(), not paper_nav_snapshots.realized_pnl's
        latest row, which resets to 0 on an open->close->reopen cycle).
    """

    label: str
    bucket: str
    floating: Decimal
    booked: Decimal


def format_summary_money(value: Decimal) -> str:
    """Signed integer, comma thousands, no `₹` — multi-strategy summary cell (FMT-1d).

    A §5 registered context override of the §3 money default (2dp, `₹` prefix):
    the fenced table's width budget forces integer, symbol-free cells. Its own
    local format — never `format_money()`'s output with the `₹` stripped or the
    decimals re-rounded (§5 rule c).

    Zero renders as `-` (§4's resolved zero / not-applicable boundary: inside this
    table `-` means a real measured zero and only that; an unresolved fetch still
    renders `N/A` upstream, never reaches here as `-`).
    """
    rounded = int(value.to_integral_value(rounding=ROUND_HALF_UP))
    if rounded == 0:
        return "-"
    sign = "+" if rounded > 0 else "-"
    return f"{sign}{abs(rounded):,}"


def build_strategy_table(rows: list[StrategyPnLRow], bucket_order: list[str]) -> str:
    """Fenced-code-block-ready multi-strategy P&L table, bucketed, totals-first (FMT-1d §12).

    Layout: `STRATEGY | FLT | BKD | TOTAL`. Rows are grouped by bucket in
    `bucket_order`; each bucket's subtotal row (`"> BUCKET TOTAL"`, all caps,
    never abbreviated) renders ABOVE its member rows — a deliberate scan-speed
    trade-off for a daily-glance message, not a pattern to generalize (§12). A
    double rule (`====`) separates the header from the first bucket; a single rule
    (`----`) separates buckets from each other. Buckets with no members present in
    `rows` are skipped entirely (no empty section).

    Every column width is computed from the actual rendered content
    (`max(len(...))`), never a hand-counted constant — same discipline as
    build_leg_table / build_compare_table (Design decision #5, ROLL-6 spec).

    Args:
        rows: one StrategyPnLRow per strategy with a figure to show. Must be
            non-empty. A row whose `bucket` is not in `bucket_order` raises
            ValueError — an unmapped strategy must fail loudly at build time.
        bucket_order: bucket names, rendered top to bottom.

    Caller wraps the return value in a ```fenced block``` — this function does
    not add the fence itself, same convention as the other builders here.
    """
    if not rows:
        raise ValueError("build_strategy_table requires at least one row")
    unknown = sorted({r.bucket for r in rows} - set(bucket_order))
    if unknown:
        raise ValueError(f"build_strategy_table: bucket(s) not in bucket_order: {unknown}")

    present_buckets = [b for b in bucket_order if any(r.bucket == b for r in rows)]

    def _cells(flt: Decimal, bkd: Decimal) -> tuple[str, str, str]:
        return format_summary_money(flt), format_summary_money(bkd), format_summary_money(flt + bkd)

    member_labels: list[str] = []
    total_labels: list[str] = []
    num_values: list[str] = []
    for bucket in present_buckets:
        members = [r for r in rows if r.bucket == bucket]
        total_labels.append(f"> {bucket.upper()} TOTAL")
        num_values.extend(
            _cells(
                sum((m.floating for m in members), Decimal("0")),
                sum((m.booked for m in members), Decimal("0")),
            )
        )
        for m in members:
            member_labels.append(f" {m.label}")
            num_values.extend(_cells(m.floating, m.booked))

    name_col = max(len("STRATEGY"), *(len(x) for x in member_labels + total_labels))
    num_col = max(len("TOTAL"), *(len(v) for v in num_values))

    def _line(label: str, flt: Decimal, bkd: Decimal) -> str:
        c_flt, c_bkd, c_tot = _cells(flt, bkd)
        return f"{label:<{name_col}}|{c_flt:>{num_col}} |{c_bkd:>{num_col}} |{c_tot:>{num_col}}"

    header = (
        f"{'STRATEGY':<{name_col}}|{'FLT':>{num_col}} |{'BKD':>{num_col}} |{'TOTAL':>{num_col}}"
    )
    double_rule = f"{'=' * name_col}|{'=' * (num_col + 1)}|{'=' * (num_col + 1)}|{'=' * num_col}"
    single_rule = f"{'-' * name_col}|{'-' * (num_col + 1)}|{'-' * (num_col + 1)}|{'-' * num_col}"

    lines = [header, double_rule]
    for i, bucket in enumerate(present_buckets):
        if i > 0:
            lines.append(single_rule)
        members = [r for r in rows if r.bucket == bucket]
        lines.append(
            _line(
                f"> {bucket.upper()} TOTAL",
                sum((m.floating for m in members), Decimal("0")),
                sum((m.booked for m in members), Decimal("0")),
            )
        )
        for m in members:
            lines.append(_line(f" {m.label}", m.floating, m.booked))
    return "\n".join(lines)


# --- ROLL-7: display labels for standalone message headlines
# (docs/plan/telegram-markdown-migration/strategy-rollout/stories.md ROLL-7;
# reference scratch/2026-08-08_reentry_notice_format.py) ---

# strategy_id -> fuller-form human label. DELIBERATELY SEPARATE from
# scripts/eod_summary.py's _STRATEGY_META, whose labels ("V1 Mth", "Fut") are
# sized for a narrow fenced-table column and read badly as a standalone headline
# ("RE-ENTRY BLOCKED: V1 Mth"). Same 12 strategy_ids, longer text. The
# "id -> {short, long}" consolidation of the two tables is flagged, not done
# (ROLL-7 spec).
STRATEGY_LABELS: dict[str, str] = {
    "paper_nifty_futures": "Futures Track",
    "paper_nifty_proxy": "Proxy Track",
    "paper_nifty_spot": "Spot Track",
    "paper_ic_nifty_v1_weekly": "IC V1 Weekly",
    "paper_ic_nifty_v1_monthly": "IC V1 Monthly",
    "paper_ic_nifty_v1_leaps": "IC V1 Leaps",
    "paper_ic_nifty_v1_yearly": "IC V1 Yearly",
    "paper_ic_nifty_v2_monthly": "IC V2 Monthly",
    "paper_collar_v1": "Collar V1",
    "paper_covered_call_v1": "Covered Call V1",
    "paper_protective_put_v1": "Protective Put V1",
    "paper_csp_nifty_v1": "CSP V1",
}

# leg_role -> display label. Explicit dict, not `.title()` — `"covered_call".title()`
# is "Covered Call" by luck, but the CC/PP acronym cases this epic handles elsewhere
# (FMT-1c badges, ROLL-6 CC/PP names) need curated text. Scoped to the values
# actually reachable as `ReEntryMixin.reentry_leg_role` across the four subclasses
# (CSPNiftyV1 / CCOverlayV1 / CollarOverlayV1 / PPOverlayV1) — verified against
# each class body, NOT the guessed set in the scratch reference. Downstream
# reusers (ROLL-8, ROLL-12) extend this dict for the roles they render.
LEG_ROLE_LABELS: dict[str, str] = {
    "short_put": "Short Put",
    "covered_call": "Covered Call",
    "overlay_collar_call": "Collar Call",
    "protective_put": "Protective Put",
}


def strategy_label(strategy_id: str) -> str:
    """Fuller-form headline label for a raw strategy_id.

    Unmapped id raises ValueError — never silently falls back to the raw id or
    drops the caller's message (same loud-failure contract as
    build_strategy_table's bucket check).
    """
    try:
        return STRATEGY_LABELS[strategy_id]
    except KeyError:
        raise ValueError(f"no display label mapped for strategy_id={strategy_id!r}") from None


def leg_role_label(leg_role: str) -> str:
    """Display label for a leg_role. Unmapped role raises ValueError."""
    try:
        return LEG_ROLE_LABELS[leg_role]
    except KeyError:
        raise ValueError(f"no display label mapped for leg_role={leg_role!r}") from None
