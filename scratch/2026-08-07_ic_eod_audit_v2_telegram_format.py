"""Scratch script — IC EOD audit (V2 monthly) Telegram message, confirmed format.

Not part of src/notifications/. Reference implementation for ROLL-1's real
port once backbone/formatting-rules ship — see module docstring notes below
for exactly what's inlined vs. what should be deleted at port time.

History / context (2026-08-07):
- This is a follow-on to scratch/2026-08-07_ic_eod_audit_telegram_format.py
  (the FIRST IC EOD audit iteration, strategy_id=paper_ic_nifty_v1_monthly,
  legacy parse_mode=Markdown v1). That earlier script is the one referenced
  by docs/plan/telegram-markdown-migration/ as "the prototype."
- THIS script targets a different, later-confirmed layout for
  paper_ic_nifty_v2_monthly (real V2 IC position data) AND switches to
  parse_mode=MarkdownV2 per the epic's "Revised 2026-08-07" README note —
  MarkdownV2, not legacy Markdown, is the actual migration target.
- Backbone (MD-1: mdcode()/escape_markdown() in src/notifications/markdown.py)
  and formatting-rules (FMT-2/FMT-3: format_money/format_greek/format_strike/
  format_pct/build_leg_table in src/notifications/formatting.py) have NOT
  shipped yet as of this session (confirmed via search_graph — zero hits for
  either function name). Per docs/plan/telegram-markdown-migration/
  message-format-workshop.md's protocol, this script therefore inlines its
  own copies of all five helpers below, matching the exact signatures/
  docstrings specified in backbone/stories.md MD-1 and
  formatting-rules/stories.md FMT-2/FMT-3 — so the eventual real
  implementation in ROLL-1 is a near-verbatim port of this file's helpers
  into src/notifications/, not a rewrite. DELETE the inlined helpers at
  port time and import the real ones instead.

MarkdownV2 reserved-character set (escaped by escape_markdown() below):
    _ * [ ] ( ) ~ ` > # + - = | { } . !
This is wider than legacy Markdown's `_ * \\` [` — in particular "." and
"(" "/" ")" are reserved, so every literal decimal point and parenthesis in
both static template text AND formatted numeric values must be escaped, not
just underscores in identifiers. Values wrapped in a code span (mdcode(), or
inside a ```fenced block```) are exempt — Telegram does not parse entities
inside code spans/blocks, which is why the leg table lives in a fence and
strategy_id uses mdcode() rather than escape_markdown().

Read-only w.r.t. the DB — makes zero DB calls. Sends a real Telegram message
(counts against the configured message budget) when run as __main__.

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-07_ic_eod_audit_v2_telegram_format
or:
    python scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

import aiohttp

# Allow running as a plain script (python scratch/foo.py) as well as -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402

data = {
    "strategy_label": "IC EOD (Monthly)",
    "strategy_id": "paper_ic_nifty_v2_monthly",
    "dte": 18,
    "nifty": 24571,
    "ivr": 0.16,
    # theta: None on every leg, same as the two longs' delta — this position's
    # real data has never captured per-leg theta (see resolve_leg_delta() in
    # src/paper/track_snapshot.py — that (delta, theta, vega) chain lookup
    # exists but is only wired for 3-track base/overlay legs, never IC).
    # Do NOT backfill a guessed theta here; compute_net_greek() below treats
    # any None as "net incomplete" rather than silently summing a partial set.
    "legs": [
        {
            "role": "Short Put",
            "strike": 24200,
            "opt_type": "PE",
            "delta": -0.23,
            "theta": None,
            "ltp": Decimal("88.95"),
            "entry": Decimal("97.78"),
        },
        {
            "role": "Long Put",
            "strike": 23500,
            "opt_type": "PE",
            "delta": None,
            "theta": None,
            "ltp": Decimal("18.05"),
            "entry": None,
        },
        {
            "role": "Short Call",
            "strike": 25100,
            "opt_type": "CE",
            "delta": 0.23,
            "theta": None,
            "ltp": Decimal("74.25"),
            "entry": Decimal("81.10"),
        },
        {
            "role": "Long Call",
            "strike": 25500,
            "opt_type": "CE",
            "delta": None,
            "theta": None,
            "ltp": Decimal("19.75"),
            "entry": None,
        },
    ],
    "mark": Decimal("125.40"),
    "entry_credit": Decimal("128.92"),
    "margin": Decimal("97243"),
    # ROI figures taken as-given from the confirmed source message, not
    # recomputed here — margin-based ROI depends on lot size / capital-basis
    # conventions this scratch script has no authority to assume. A prior
    # draft of this file guessed roi_amount = captured_credit * 75 (lot
    # size), which is fabricated and was wrong to include — real ROI must
    # come from PaperTracker's actual calculation, not a guess in a
    # formatting scratch script.
    "roi_amount": 229,
    "roi_pct": 0.2,
    "signals": [],
    "intraday_actions": [],
}


def _make_scenario(*, legs=None, **overrides) -> dict:
    """Deep-copy `data` and apply top-level field overrides.

    `legs`, if given, replaces the leg list wholesale (used by
    `full_greeks` below to supply complete synthetic delta/theta data —
    every other scenario reuses the real position's leg list unchanged).
    """
    import copy

    d = copy.deepcopy(data)
    if legs is not None:
        d["legs"] = legs
    d.update(overrides)
    return d


# Synthetic complete-Greeks leg set for the `full_greeks` scenario only.
# NOT real position data — exists purely to demonstrate the Net Δ/Net θ
# line rendering once all four legs' Greeks are actually captured (see
# compute_net_greek()'s "incomplete" branch, which is what every other
# scenario below exercises instead, since the real position genuinely
# lacks this data today).
_FULL_GREEKS_LEGS = [
    {
        "role": "Short Put",
        "strike": 24200,
        "opt_type": "PE",
        "delta": -0.23,
        "theta": Decimal("4.10"),
        "ltp": Decimal("88.95"),
        "entry": Decimal("97.78"),
    },
    {
        "role": "Long Put",
        "strike": 23500,
        "opt_type": "PE",
        "delta": -0.06,
        "theta": Decimal("-0.85"),
        "ltp": Decimal("18.05"),
        "entry": None,
    },
    {
        "role": "Short Call",
        "strike": 25100,
        "opt_type": "CE",
        "delta": 0.23,
        "theta": Decimal("3.95"),
        "ltp": Decimal("74.25"),
        "entry": Decimal("81.10"),
    },
    {
        "role": "Long Call",
        "strike": 25500,
        "opt_type": "CE",
        "delta": 0.05,
        "theta": Decimal("-0.70"),
        "ltp": Decimal("19.75"),
        "entry": None,
    },
]

# Named presets for exercising pnl_emoji()/alert_emoji()/net-Greeks branches
# without hand-editing `data` each time. Add a new key here rather than a
# one-off edit to `data` when you need another combination.
SCENARIOS = {
    "profit": lambda: _make_scenario(),
    "loss": lambda: _make_scenario(mark=Decimal("140.00")),
    "flat": lambda: _make_scenario(mark=data["entry_credit"]),
    "alert": lambda: _make_scenario(signals=["DELTA_WARN"]),  # profit + alert
    "loss_alert": lambda: _make_scenario(mark=Decimal("140.00"), signals=["DELTA_WARN"]),
    "full_greeks": lambda: _make_scenario(legs=_FULL_GREEKS_LEGS),
}


# --- Inlined MD-1 helpers (src/notifications/markdown.py, not yet shipped) ---

MARKDOWNV2_RESERVED = "_*[]()~`>#+-=|{}.!"


def escape_markdown(text: str) -> str:
    """Backslash-escape MarkdownV2 reserved characters in free text.

    Matches backbone/stories.md MD-1 signature exactly — inlined here only
    because src/notifications/markdown.py doesn't exist yet this session.
    """
    return "".join(f"\\{ch}" if ch in MARKDOWNV2_RESERVED else ch for ch in text)


def mdcode(value: str) -> str:
    """Wrap a dynamic identifier-like value as an inline code span.

    Matches MD-1 signature exactly. Falls back to escape_markdown() if value
    contains a literal backtick (broken/nested code span otherwise).
    """
    if "`" in value:
        return escape_markdown(value)
    return f"`{value}`"


# --- Inlined FMT-2 helpers (src/notifications/formatting.py, not yet shipped) ---


def format_money(value: Decimal) -> str:
    """2dp, comma thousands, ₹ prefix, sign BEFORE the symbol for negatives.

    Matches FMT-2 signature. FMT-1's spec table only shows positive examples
    (₹86.68, ₹82,628) - a naive f"₹{value:,.2f}" puts the minus sign after
    the rupee symbol for negative Decimals ("₹-10.50"), which reads wrong.
    Handled explicitly so the real FMT-2 implementation doesn't reintroduce
    it once this message starts showing loss states.
    """
    if not isinstance(value, Decimal):
        raise TypeError(f"format_money expects Decimal, got {type(value)}")
    sign = "-" if value < 0 else ""
    return f"{sign}\u20b9{abs(value):,.2f}"


def pnl_emoji(amount: Decimal) -> str:
    """Presence/sign-based P&L indicator - not a severity tier.

    >0 -> checkmark, <0 -> down-arrow, ==0 -> flat dash. Deliberately does
    NOT do string-matching on any signal name (rejected approach: matching
    "WARN" in a signal code string is fragile and couples display logic to
    a naming convention that isn't guaranteed stable - e.g. a future
    GAMMA_RISK_ACTION code wouldn't contain "WARN" but would be worse).
    """
    if amount > 0:
        return "✅"
    if amount < 0:
        return "\U0001f53b"
    return "➖"


def alert_emoji(signals: list[str]) -> str:
    """Presence-based alert indicator: green when signals is empty, warning
    otherwise. A real three-tier version (info/warn/action) needs the actual
    ExitSignalResult severity threaded through from ExitSignalEngine - not
    available in this scratch script's data shape, and not safely fakeable
    by substring-matching the signal code name (same rejection reason as
    pnl_emoji above).
    """
    return "\U0001f7e2" if not signals else "⚠️"


def compute_net_greek(legs: list[dict], key: str) -> Decimal | None:
    """Sum a Greek across all legs, or None if ANY leg is missing it.

    Deliberately does NOT sum only the legs that happen to have a value -
    a partial sum labeled "Net" would look complete while silently
    excluding real (non-zero) contributions from whichever legs are
    missing data. For this position specifically, the two long legs have
    no captured delta and no leg has captured theta at all (see the
    `data["legs"]` module-level comment) - so this returns None for both
    Net Δ and Net θ until a real chain-Greeks fetch (the IC equivalent of
    src/paper/track_snapshot.py's resolve_leg_delta) backfills every leg.
    """
    values = [leg.get(key) for leg in legs]
    if any(v is None for v in values):
        return None
    return (
        sum(values, Decimal("0")) if isinstance(values[0], Decimal) else Decimal(str(sum(values)))
    )


def format_greek(value: float | None, *, width: int | None = None) -> str:
    """2dp, always signed, '-' placeholder for None. Matches FMT-2 signature."""
    if value is None:
        s = "-"
    else:
        s = f"{value:+.2f}"
    return f"{s:>{width}}" if width else s


def format_strike(value: float | int) -> str:
    """Integer string, no decimal. Matches FMT-2 signature."""
    return str(int(value))


def format_pct(value: float) -> str:
    """1dp; whole numbers print with no trailing .0 (FMT-1's '4%' example)."""
    return f"{value:.0f}%" if value == int(value) else f"{value:.1f}%"


# --- Inlined FMT-3 leg table (src/notifications/formatting.py, not yet shipped) ---


def build_leg_table(legs: list[dict]) -> str:
    """Fenced-code-block-ready position table: Act/Strike/Type/Δ/LTP/Entry.

    LTP/Entry columns use the locked-in 1dp exception (FMT-1), NOT
    format_money's 2dp default — local f"{value:.1f}" per FMT-3's docstring,
    not format_money(). Delta uses format_greek() for consistent None/sign
    handling. Caller wraps the return in a ```fenced block```.
    """
    rows = []
    for leg in legs:
        badge = "[S]" if leg["role"].startswith("Short") else "[B]"
        delta_str = format_greek(leg["delta"])
        entry_str = f"{leg['entry']:.1f}" if leg["entry"] is not None else "-"
        rows.append(
            (
                badge,
                format_strike(leg["strike"]),
                leg["opt_type"],
                delta_str,
                f"{leg['ltp']:.1f}",
                entry_str,
            )
        )

    widths = {
        "act": 3,
        "strike": max(len("Strike"), *(len(r[1]) for r in rows)),
        "type": max(len("Type"), *(len(r[2]) for r in rows)),
        "delta": max(len("Δ"), *(len(r[3]) for r in rows)),
        "ltp": max(len("LTP"), *(len(r[4]) for r in rows)),
        "entry": max(len("Entry"), *(len(r[5]) for r in rows)),
    }

    header = (
        f"{'Act':<{widths['act']}} {'Strike':<{widths['strike']}} "
        f"{'Type':<{widths['type']}} {'Δ':>{widths['delta']}} "
        f"{'LTP':>{widths['ltp']}} {'Entry':>{widths['entry']}}"
    )
    lines = [header, "-" * len(header)]
    for act, strike, opt_type, delta_str, ltp_str, entry_str in rows:
        lines.append(
            f"{act:<{widths['act']}} {strike:<{widths['strike']}} "
            f"{opt_type:<{widths['type']}} {delta_str:>{widths['delta']}} "
            f"{ltp_str:>{widths['ltp']}} {entry_str:>{widths['entry']}}"
        )
    return "\n".join(lines)


def build_message(d: dict) -> str:
    """Confirmed 2026-08-07 target format for the IC EOD (V2 monthly) audit.

    Structure: bold header + mdcode() identifier line, bold Nifty/DTE/IVR
    line, fenced leg table, bold Credit/Mark line, bold Captured/ROI line,
    bold Margin line, bold Alert/Actions line. Every literal reserved
    MarkdownV2 character in static template text (parentheses, pipes,
    periods inside money figures) is escaped explicitly below — this is
    the part MD-3/MD-4's audit-and-fix pass will need to repeat for every
    other message, per backbone/stories.md's "static template text needs
    escaping too" note.
    """
    captured_credit = d["entry_credit"] - d["mark"]
    captured_pct = float(captured_credit / d["entry_credit"] * 100)
    roi_amount = d["roi_amount"]
    roi_pct = d["roi_pct"]

    net_delta = compute_net_greek(d["legs"], "delta")
    net_theta = compute_net_greek(d["legs"], "theta")

    # signal_notes: optional list[str | None], index-aligned with d["signals"]
    # — a short free-text annotation per signal code (e.g. "Test short wing").
    # Absent/shorter list is fine; missing entries render with no note.
    signal_notes = d.get("signal_notes", [])
    if d["signals"]:
        parts = []
        for i, s in enumerate(d["signals"]):
            note = signal_notes[i] if i < len(signal_notes) else None
            if note:
                parts.append(f"{mdcode(s)} \\({escape_markdown(note)}\\)")
            else:
                parts.append(mdcode(s))
        signals = ", ".join(parts)
    else:
        signals = "None"
    actions = (
        ", ".join(mdcode(a) for a in d["intraday_actions"]) if d["intraday_actions"] else "None"
    )

    header_label = escape_markdown(d["strategy_label"])  # "IC EOD (Monthly)" -> escapes ( )
    nifty_str = escape_markdown(f"{d['nifty']:,}")
    ivr_str = escape_markdown(f"{d['ivr']:.2f}")
    credit_str = escape_markdown(format_money(d["entry_credit"]))
    mark_str = escape_markdown(format_money(d["mark"]))
    captured_amt_str = escape_markdown(format_money(captured_credit))  # includes ₹ + sign
    captured_pct_str = escape_markdown(format_pct(captured_pct))
    roi_pct_str = escape_markdown(format_pct(roi_pct))
    roi_amt_str = escape_markdown(str(roi_amount))
    margin_str = escape_markdown(f"{int(d['margin']):,}")

    pnl_icon = pnl_emoji(captured_credit)
    alert_icon = alert_emoji(d["signals"])
    # format_money already puts the sign before the ₹ for a negative
    # captured_credit; only strip its own leading "-" here since the
    # \( escaping wraps the whole figure and a bare "-10.50" inside
    # parens is fine either way — no extra handling needed beyond
    # format_money's fix above.

    if net_delta is None:
        net_delta_str = "incomplete"
    else:
        net_delta_str = escape_markdown(format_greek(float(net_delta)))
    if net_theta is None:
        net_theta_str = "incomplete"
    else:
        net_theta_str = escape_markdown(format_greek(float(net_theta)))

    lines = [
        f"\U0001f4ca *{header_label}* \\| {mdcode(d['strategy_id'])}",
        f"*Nifty:* {nifty_str} \\| *DTE:* {d['dte']} \\| *IVR:* {ivr_str}",
        f"*Net \u0394:* {net_delta_str} \\| *Net \u03b8:* {net_theta_str}",
        "```",
        build_leg_table(d["legs"]),
        "```",
        f"\U0001f4b0 *Credit:* {credit_str} \u27a1\ufe0f *Mark:* {mark_str}",
        f"{pnl_icon} *Captured:* {captured_amt_str} \\({captured_pct_str}\\) \\| "
        f"*ROI:* {roi_pct_str} \\(\u20b9{roi_amt_str}\\)",
        f"\U0001f3e6 *Margin:* \u20b9{margin_str}",
        f"{alert_icon} *Alert:* {signals}",
        f"\u2699\ufe0f *Actions:* {actions}",
    ]
    return "\n".join(lines)


async def send_markdown_v2(bot_token: str, chat_id: str, message: str) -> bool:
    """Send with parse_mode=MarkdownV2 — the epic's actual migration target
    (not legacy Markdown, which the first scratch script used).
    """
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "MarkdownV2"}
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, json=payload) as resp:
                # Don't raise_for_status() before reading the body — Telegram
                # puts the actual parse-error reason in the JSON "description"
                # field even on a 400, and raising first discards it. This
                # exact mistake cost a full debugging round-trip in the
                # original IC EOD session (2026-08-07) — don't repeat it.
                resp_data = await resp.json()
                if not resp_data.get("ok"):
                    print(f"!! Telegram API error ({resp.status}): {resp_data.get('description')}")
                return bool(resp_data.get("ok"))
    except Exception as exc:  # Intentional: isolate all API failures, scratch probe only
        print(f"!! send failed: {exc}")
        return False


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="IC EOD audit (V2 monthly) Telegram message format probe."
    )
    parser.add_argument(
        "--scenario",
        default="profit",
        choices=sorted(SCENARIOS),
        help="Named data preset to render (default: profit — your confirmed real numbers).",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="Print available --scenario names and exit.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send to Telegram (default: print only, never sends). "
        "Requires TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID in the environment.",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()

    if args.list_scenarios:
        for name in sorted(SCENARIOS):
            print(name)
        return

    scenario_data = SCENARIOS[args.scenario]()
    text = build_message(scenario_data)
    print(f"--- scenario: {args.scenario} ---")
    print(text)
    print(
        "\n(Note: printed text above is raw MarkdownV2 source — asterisks/"
        "backslashes are literal here. Check the actual rendering on-device "
        "after sending, not this console output.)"
    )

    if not args.send:
        print("\n(--send not passed — nothing sent. Pass --send to actually post to Telegram.)")
        return

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print(
            "\n!! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in environment — "
            "cannot send. Aborting without sending anything."
        )
        return

    ok = await send_markdown_v2(settings.telegram_bot_token, settings.telegram_chat_id, text)
    print(f"\nsend_markdown_v2() returned {ok}")
    if not ok:
        print("!! send failed — check logs / credentials before retrying")


if __name__ == "__main__":
    asyncio.run(main())
