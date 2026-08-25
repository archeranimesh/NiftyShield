"""Value formatters for notifications."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


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
