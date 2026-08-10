"""Scratch script — Position Health check alert Telegram message formatting.

Message #6 in docs/plan/telegram-markdown-migration/TODO.md's "Confirmed missing" queue —
`scripts/position_health_check.py::main`, lines 129-135 (confirmed via `search_graph` +
`get_code_snippet`, not the TODO.md grep excerpt alone):

    if has_issue:
        alert_body = "\n".join(findings)
        alert_msg = f"?????? NiftyShield Position Health ??? {today.isoformat()}\n{alert_body}"
        ...
        success = await notifier.send(alert_msg)

(mangled emoji/dash bytes in the current source — `search_code` returned them as `??????`;
the real chars are presumably `⚠️` and `—`, confirm against the actual file bytes before
implementing for real, don't copy the mangled form.)

`findings` (`list[str]`) is built by `run_position_checks()` (same file, lines 48-91) —
already pre-aggregated per root CLAUDE.md Rule 1 (never raw position rows). Exactly two
finding shapes, both pre-formatted f-strings today:

    f"❌ UNRESOLVED_INSTRUMENT: {strategy_name}/{position.leg_role} "
    f"key={position.instrument_key} net_qty={position.net_qty}"

    f"❌ ROLL_OVERDUE: {strategy_name}/{position.leg_role} "
    f"key={position.instrument_key} expiry={expiry_str} "
    f"({days_overdue}d overdue) net_qty={position.net_qty}"

**backbone/ (MD-1..MD-5) status as of this session: NOT shipped** — confirmed via
`search_graph("mdcode")` / `search_graph("escape_markdown")` (both zero results outside
`scratch/`, same check as every prior queue item's session). This script inlines its own
copy of `escape_markdown()`/`mdcode()`, matching MD-1's exact spec in
`docs/plan/telegram-markdown-migration/backbone/stories.md`.

**v3 — CONFIRMED SHAPE (2026-08-10, Animesh's exact counter-proposal, not yet on-device
verified — this session's sandbox has no working venv/aiohttp, see "Known sandbox
limitation" below):**

    ⚠️ NIFTYSHIELD: POSITION HEALTH

    ❌ ROLLS OVERDUE (2):
    🚨 12d LATE: [CSP V1] Short 25x NIFTY 22500 PE (18 Aug 26)
    🚨 5d LATE: [IC V1 Weekly] Short 50x NIFTY 23000 CE (25 Aug 26)

    ❓ UNMAPPED ASSET (1):
    ⚠️ [Covered Call V1] Long 100x (Unknown Token: 99999)

**v1/v2 -> v3 elimination trail:**
1. v1 (superseded) was a raw `mdcode()`-identifier line per finding — `strategy/leg_role` +
   raw instrument_key + `key=value` fields, closest to a straight re-render of the current
   f-strings. Rejected by Animesh as "cryptic" (the raw `NSE_FO|48521` broker key specifically).
2. v2 (superseded) kept the grouped-list shape but swapped the raw key for a resolved option
   label via the real `format_option_label()`. Rejected in favor of v3's further restructure:
   direction word (Short/Long) + quantity instead of a bare signed `qty=`, human strategy label
   in `[brackets]` instead of the raw `strategy_name/leg_role` identifier, and a per-row
   `Xd LATE:` prefix instead of a trailing `(Nd overdue)` suffix.
3. **Severity icon — confirmed always 🚨 for ROLLS OVERDUE, no ⚠️ tier** (Animesh's answer,
   2026-08-10): every roll-overdue finding is inherently action-required regardless of how many
   days overdue: no two-tier severity threshold. `days_overdue` still renders as `Nd LATE:` —
   only the icon is fixed, not the number.
4. **Date format — confirmed to stay on FMT-1's locked `dd Mon yy` spec** (Animesh's answer,
   2026-08-10), NOT the shorter `dd-Mon` shown in his own sketch — his sketch used the compact
   form informally; asked explicitly rather than assume an unstated FMT-1 override, per this
   epic's own precedent (`build_leg_table`'s 1dp override required an explicit confirmed
   decision, not silent adoption). So `(18-Aug)` in his sketch renders as `(18 Aug 26)` here.
5. **Strategy display labels — reuses the existing `STRATEGY_LABELS` dict**, the SAME table
   `scratch/2026-08-08_strategy_event_alert_format.py` (`_label_strategy`) and
   `scratch/2026-08-08_reentry_notice_format.py` already define for ROLL-7/ROLL-8 — duplicated
   here rather than imported since none of these are real `src/` code yet (all are pre-`ROLL-*`
   scratch references); this is the SAME already-flagged "revisit once one of these ships"
   duplication point those two scripts note, not a new one. An unmapped `strategy_name` raises
   `ValueError` loudly rather than silently falling back to the raw id — same discipline
   ROLL-6/ROLL-7/ROLL-8 all require for their own label tables.
6. **Direction (Short/Long) derived from `net_qty`'s sign** (negative = Short, positive =
   Long) — matches the project's existing short-option-collects-premium convention (e.g.
   `short_call`/`short_put` leg roles always carry negative `net_qty` in this codebase).
   Quantity itself renders as `abs(net_qty)`, e.g. `net_qty=-25` -> `Short 25x`.
7. **"Unknown Token: 99999"** — UNMAPPED ASSET rows show only the numeric suffix of the raw
   instrument_key (after the `|`), not the full `NSE_FO|99999` broker key. Parsed defensively:
   falls back to the full raw key if the key doesn't contain `|` (format assumption, not a
   hard-coded NSE_FO-only parser — flag if a non-`|`-delimited key format is ever seen in
   practice, this fallback exists specifically so that case doesn't silently mis-render).
8. **Section renamed** `UNRESOLVED_INSTRUMENT` -> `UNMAPPED ASSET` (❓ header, ⚠️ per-row icon,
   distinct from ROLLS OVERDUE's ❌ header / 🚨 per-row icon) and `ROLL_OVERDUE` ->
   `ROLLS OVERDUE` (plural) — Animesh's exact wording, adopted verbatim rather than kept as the
   raw enum-style names from the current f-strings.
9. **Rows within ROLLS OVERDUE sorted descending by `days_overdue`** (12d before 5d) — matches
   the order in Animesh's sketch; with severity icon now fixed at 🚨 for every row (see #3),
   days-overdue-descending is the only remaining signal for "which one needs attention first"
   at a glance, so sorting on it explicitly rather than leaving `run_position_checks()`'s
   incidental iteration order (loop-through-strategies-then-positions) is a deliberate call,
   not restated in the sketch but consistent with it — flag if Animesh wants insertion order
   preserved instead.
10. Header drops the date entirely (`⚠️ NIFTYSHIELD: POSITION HEALTH`, no `— <date>` suffix) —
    matches Animesh's sketch exactly; unlike ROLL-11's `Healthcheck` alert (which keeps a
    `[HH:MM]` in its headline), this message's rows each already carry their own expiry date,
    so a message-level "as-of" date/time was judged redundant in the sketch. Not independently
    re-litigated here — following the sketch as given.

**Asymmetry that can't be fixed by formatting alone (unchanged from v2):** UNMAPPED ASSET
findings have no `inst` by construction — `lookup.get_by_key()` returned `None`, which is
exactly why the finding fired. There is no strike/underlying/expiry to build a Short/Long +
instrument line from, so these rows keep the bare direction/qty + the token suffix as the only
identifying information, structurally different from a ROLLS OVERDUE row rather than a
formatting inconsistency.

**Known sandbox limitation (this session):** this sandbox's Python lacks `aiohttp` (confirmed
via `import aiohttp` -> `ModuleNotFoundError`) and has no working project venv — same
limitation ROLL-9/ROLL-10/ROLL-11's sessions hit. `--send` cannot be exercised here; Animesh
needs to run this from his own machine to confirm on-device rendering before this format is
treated as locked in (do not tick TODO.md's box on print-only output alone).

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-10_position_health_alert_format <scenario> [--send]
    python -m scratch.2026-08-10_position_health_alert_format --list-scenarios
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import aiohttp

# Allow running as a plain script (python scratch/foo.py) as well as -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.instruments.lookup import format_option_label  # noqa: E402 — real, already-shipped helper

# ── Inline copies of MD-1's escape_markdown()/mdcode() (backbone/ not shipped yet — see
# module docstring) ──

MARKDOWNV2_RESERVED = "_*[]()~`>#+-=|{}.!"


def escape_markdown(text: str) -> str:
    """Backslash-escape MarkdownV2 reserved characters in free text.

    Mirrors docs/plan/telegram-markdown-migration/backbone/stories.md MD-1 spec exactly —
    inline copy pending the real src/notifications/markdown.py landing.
    """
    out = []
    for ch in text:
        if ch in MARKDOWNV2_RESERVED:
            out.append("\\")
        out.append(ch)
    return "".join(out)


# ── Strategy display-name table — SAME dict as ROLL-7/ROLL-8's reference scripts (see module
# docstring point 5); duplicated here for the same not-yet-real-code reason. Only the
# strategy_name values actually reachable via run_position_checks() (i.e. every strategy that
# can hold an open paper position) need entries here. ──

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


def _label_strategy(strategy_name: str) -> str:
    """Explicit-mapping lookup; unmapped id raises loudly rather than silently falling back
    to the raw id — same discipline ROLL-6/ROLL-7/ROLL-8 all require for their own label
    tables (module docstring point 5)."""
    try:
        return STRATEGY_LABELS[strategy_name]
    except KeyError:
        raise ValueError(f"no display label mapped for strategy_name={strategy_name!r}") from None


FindingType = Literal["roll_overdue", "unresolved_instrument"]


@dataclass(frozen=True)
class PositionFinding:
    """Structured equivalent of one entry in `run_position_checks()`'s `list[str]` return —
    this script builds the message from structured fields rather than re-parsing the current
    pre-formatted strings, same anti-brittle-parsing reasoning as ROLL-7/ROLL-11 in this epic.
    The real implementation would need `run_position_checks()` refactored to return
    `list[PositionFinding]` instead of `list[str]`, same class of upstream change ROLL-11
    needed for `run_checks()`."""

    finding_type: FindingType
    strategy_name: str
    leg_role: str
    instrument_key: str
    net_qty: int
    expiry_str: str | None = None  # only set for roll_overdue
    days_overdue: int | None = None  # only set for roll_overdue
    # Resolved-instrument fields — only ever set for roll_overdue (unresolved_instrument
    # findings have no `inst` by construction, see module docstring's Asymmetry note).
    underlying_symbol: str | None = None
    strike_price: float | None = None
    instrument_type: str | None = None  # "CE" / "PE" / "FUT"


def _direction_and_qty(net_qty: int) -> tuple[str, int]:
    """(Short|Long, abs(qty)) — module docstring point 6. net_qty == 0 legs are never passed
    in (run_position_checks() already skips closed legs), so no zero-case is defined here."""
    return ("Short", -net_qty) if net_qty < 0 else ("Long", net_qty)


def _resolved_label(f: PositionFinding) -> str:
    """Human-readable instrument label for a roll_overdue finding (never called for
    unresolved_instrument — see module docstring's Asymmetry note).

    CE/PE: reuses the real format_option_label(). FUT: format_option_label() would print a
    meaningless strike (futures have none) — special-cased here rather than passed through.
    """
    if f.instrument_type == "FUT":
        expiry_label = date.fromisoformat(f.expiry_str).strftime("%d %b %y").lstrip("0")
        return f"{f.underlying_symbol} FUT"
    label = format_option_label(
        f.underlying_symbol, f.strike_price, f.instrument_type, f.expiry_str
    )
    # format_option_label() renders "NIFTY 23000 CE 25 AUG 26" (month upper-cased, per its own
    # convention). v3's confirmed shape wants the underlying+strike+type only — the expiry
    # renders separately in the trailing "(dd Mon yy)" parenthetical (module docstring point 4)
    # — so strip format_option_label's own trailing expiry rather than duplicate it.
    underlying_strike_type = f"{f.underlying_symbol} {label.split()[1]} {f.instrument_type}"
    return underlying_strike_type


def _unknown_token(instrument_key: str) -> str:
    """Numeric suffix of a broker instrument_key (module docstring point 7). Falls back to
    the full raw key if it doesn't contain '|' — defensive, not a hard-coded NSE_FO-only
    parser; flag if this fallback ever actually fires against real BOD data."""
    return instrument_key.split("|", 1)[1] if "|" in instrument_key else instrument_key


# ── Sample data — structured equivalents of what run_position_checks() produces today
# (as plain strings) in scripts/position_health_check.py. Strategy names match the real
# constants in src/paper/constants.py (confirmed via search_code — e.g. Covered Call V1's
# real strategy_name is "paper_covered_call_v1", not "paper_cc_overlay_v1"). ──

SCENARIOS: dict[str, list[PositionFinding]] = {
    "roll_overdue_only": [
        PositionFinding(
            "roll_overdue", "paper_ic_nifty_v1_weekly", "short_call", "NSE_FO|48521",
            -50, expiry_str="2026-08-25", days_overdue=5,
            underlying_symbol="NIFTY", strike_price=23000, instrument_type="CE",
        ),
        PositionFinding(
            "roll_overdue", "paper_csp_nifty_v1", "short_put", "NSE_FO|48530",
            -25, expiry_str="2026-08-18", days_overdue=12,
            underlying_symbol="NIFTY", strike_price=22500, instrument_type="PE",
        ),
    ],
    "unresolved_only": [
        PositionFinding(
            "unresolved_instrument", "paper_covered_call_v1", "overlay_cc", "NSE_FO|99999", 100,
        ),
    ],
    "mixed": [
        PositionFinding(
            "roll_overdue", "paper_ic_nifty_v1_weekly", "short_call", "NSE_FO|48521",
            -50, expiry_str="2026-08-25", days_overdue=5,
            underlying_symbol="NIFTY", strike_price=23000, instrument_type="CE",
        ),
        PositionFinding(
            "roll_overdue", "paper_csp_nifty_v1", "short_put", "NSE_FO|48530",
            -25, expiry_str="2026-08-18", days_overdue=12,
            underlying_symbol="NIFTY", strike_price=22500, instrument_type="PE",
        ),
        PositionFinding(
            "unresolved_instrument", "paper_covered_call_v1", "overlay_cc", "NSE_FO|99999", 100,
        ),
    ],
    "single_finding": [
        PositionFinding(
            "roll_overdue", "paper_protective_put_v1", "overlay_pp", "NSE_FO|48540",
            10, expiry_str="2026-08-11", days_overdue=1,
            underlying_symbol="NIFTY", strike_price=21500, instrument_type="PE",
        ),
    ],
    "roll_overdue_futures": [
        # base_futures leg roll from ROLL-9 — no strike. format_option_label() isn't called
        # for FUT at all (see _resolved_label); this scenario exists to exercise that path.
        PositionFinding(
            "roll_overdue", "paper_nifty_futures", "base_futures", "NSE_FO|11111",
            75, expiry_str="2026-08-25", days_overdue=3,
            underlying_symbol="NIFTY", strike_price=0, instrument_type="FUT",
        ),
    ],
}


def build_message(findings: list[PositionFinding]) -> str:
    """Position Health alert, MarkdownV2-safe — v3 confirmed shape (see module docstring).

    Shape:
        ⚠️ NIFTYSHIELD: POSITION HEALTH
        <blank line>
        ❌ ROLLS OVERDUE (<n>):
        <one "🚨 <days>d LATE: [<strategy label>] <Short|Long> <qty>x <underlying> <strike>
              <CE|PE|FUT> (<dd Mon yy>)" line per roll_overdue finding, sorted by days_overdue
              descending>
        <blank line>
        ❓ UNMAPPED ASSET (<n>):
        <one "⚠️ [<strategy label>] <Short|Long> <qty>x (Unknown Token: <numeric suffix>)"
              line per unresolved_instrument finding>

    A group section is omitted entirely if it has zero findings of that type (mirrors
    ROLL-11's "omit SYSTEMS NORMAL if empty" convention). This function is never called with
    an empty findings list — `run_position_checks()`'s `has_issue` bool gates the call site,
    same contract as ROLL-11's `run_checks()`.
    """
    lines = ["⚠️ NIFTYSHIELD: POSITION HEALTH", ""]

    overdue = sorted(
        (f for f in findings if f.finding_type == "roll_overdue"),
        key=lambda f: f.days_overdue,
        reverse=True,
    )
    unresolved = [f for f in findings if f.finding_type == "unresolved_instrument"]

    if overdue:
        lines.append(f"❌ ROLLS OVERDUE {escape_markdown(f'({len(overdue)})')}:")
        for f in overdue:
            direction, qty = _direction_and_qty(f.net_qty)
            strategy_label = escape_markdown(_label_strategy(f.strategy_name))
            instrument = escape_markdown(_resolved_label(f))
            expiry = escape_markdown(
                f"({date.fromisoformat(f.expiry_str).strftime('%d %b %y').lstrip('0')})"
            )
            lines.append(
                f"🚨 {f.days_overdue}d LATE: {escape_markdown('[')}{strategy_label}"
                f"{escape_markdown(']')} {direction} {qty}x {instrument} {expiry}"
            )
        lines.append("")

    if unresolved:
        lines.append(f"❓ UNMAPPED ASSET {escape_markdown(f'({len(unresolved)})')}:")
        for f in unresolved:
            direction, qty = _direction_and_qty(f.net_qty)
            strategy_label = escape_markdown(_label_strategy(f.strategy_name))
            token = escape_markdown(_unknown_token(f.instrument_key))
            lines.append(
                f"⚠️ {escape_markdown('[')}{strategy_label}{escape_markdown(']')} "
                f"{direction} {qty}x {escape_markdown('(')}Unknown Token: {token}"
                f"{escape_markdown(')')}"
            )
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


async def send_markdown_v2(bot_token: str, chat_id: str, message: str) -> bool:
    """Send with parse_mode=MarkdownV2 — per epic decision, not legacy Markdown/HTML."""
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "MarkdownV2"}
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, json=payload) as resp:
                # Don't raise_for_status() before reading the body — Telegram puts the
                # actual parse-error reason in the JSON "description" field even on a 400.
                resp_data = await resp.json()
                if not resp_data.get("ok"):
                    print(f"!! Telegram API error ({resp.status}): {resp_data.get('description')}")
                return bool(resp_data.get("ok"))
    except Exception as exc:  # Intentional: isolate all API failures, scratch probe only
        print(f"!! send failed: {exc}")
        return False


async def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "mixed"
    if scenario == "--list-scenarios":
        print("\n".join(SCENARIOS.keys()))
        return
    if scenario not in SCENARIOS:
        print(f"!! unknown scenario {scenario!r}; use one of: {', '.join(SCENARIOS)}")
        return

    text = build_message(SCENARIOS[scenario])
    print(f"--- scenario: {scenario} ---")
    print(text)
    print("---")

    if "--send" not in sys.argv:
        print("(print-only; pass --send to actually post to Telegram)")
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
