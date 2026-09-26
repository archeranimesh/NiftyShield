"""Scratch script — Three-track base-leg roll notification Telegram message formatting.

Message #3 in docs/plan/telegram-markdown-migration/TODO.md's "Confirmed missing" queue —
`_notify_roll` (real function name — confirmed via `sed`, TODO.md's line-range citation
309-313 points at the message-construction block inside it) in
scripts/strategies/three_track/paper_3track_roll.py. TODO.md's summary line ("Opened:
{next_key} @ ₹{open_price} + status line. Two lines, single position event.") undersold the
real message — the CURRENT (pre-migration) code is actually 6 lines:

    msg = (
        f"🔄 BASE LEG ROLLED\\n"
        f"Strategy: {pos.strategy_name}\\n"
        f"Leg: {pos.leg_role}\\n"
        f"Closed: {pos.instrument_key} @ ₹{close_price}\\n"
        f"Opened: {next_key} @ ₹{open_price}\\n"
        f"{status_line}"
    )

Handles the base-leg roll for `base_futures` (DTE<=1) and `base_ditm_call` (DTE<20) —
separate from the backbone-managed overlay/CSP rolls (`CSPNiftyV1`/`NiftyTrackComparisonV1`
via `PaperExecutor`, see CONTEXT.md's `src/strategy/` section, "S5").

**backbone/ (MD-1..MD-5) status as of this session: NOT shipped** — confirmed via
`search_graph("mdcode")` returning zero results and `ls src/notifications/` showing no
`markdown.py`. This script inlines its own copies of `escape_markdown()` / `mdcode()`,
matching MD-1's exact spec in docs/plan/telegram-markdown-migration/backbone/stories.md, same
as the `reentry_notice`/`strategy_event_alert` scratch scripts before it.

Iteration history this session (v1 -> v2 -> v3, all Animesh-driven, not proposed by Claude):

v1 — direct kv-line port of the current 6-line message (label lookups + mdcode() on instrument
keys, no new fields). Confirmed working, but superseded before being locked in.

v2 — added a closed-leg realized P&L line: `pnl = (close_price - pos.avg_cost) * qty`,
`qty = abs(pos.net_qty)`. Uses `avg_cost`, not `avg_sell_price` — both rollable leg roles
(`base_futures`, `base_ditm_call`) are long proxy/hedge positions (bought, never sold short)
per CONTEXT.md's `src/paper/`/`src/strategy/` sections, so `avg_cost` (BUY-only weighted
average, per `PaperPosition`'s own docstring) is the correct entry basis. This is real added
scope beyond an escaping/formatting port — `_notify_roll`'s real implementation currently
receives no P&L, so the eventual port must thread `pos.avg_cost`/`abs(pos.net_qty)` (both
already in scope as attributes of `pos`, the loop variable already available where the message
is built — no new fetch, no signature change needed since `pos` itself is already local) into
the message-building block.

v3 (THIS VERSION, current confirmed target) — full redesign per Animesh's counter-proposal,
replacing the kv-line shape entirely with a denser trader-facing layout:

    🔄 ROLL: NIFTY FUT [AUG ➡️ SEP]
    💰 P&L: +₹7,812.50 🟢
    📐 Spread: 43.25 pts (Contango)

    ⬇️ OUT: ₹24,812.50
    ⬆️ IN: ₹24,855.75
    ✅ L-Gate: PASS

Confirmed field-by-field data-availability audit (per Animesh's explicit ask — which parts
need real code changes vs. pure reformatting):
    - OUT/IN prices, L-Gate status, partial-roll override: zero new data — `close_price`,
      `open_price`, `gate_passed`, `partial` are already `_notify_roll`'s existing inputs.
    - Spread + Contango/Backwardation label: zero new data — `open_price - close_price`,
      both already in scope. Contango = far-month price > near-month price (correct usage,
      confirmed with Animesh — this is the calendar-spread sign, not spot-vs-future, but the
      same "curve slope" concept; valid specifically for `base_futures`, NOT generalized to
      `base_ditm_call` yet — that leg's equivalent line is explicitly deferred, see below).
    - P&L line: small code change — `pos.avg_cost`/`abs(pos.net_qty)` already local (see v2
      note above), just needs threading into the message string.
    - Month labels ("AUG"/"SEP"): small code change, not a new data source — `expiry_date`
      (current contract) is already resolved earlier in `_run()` via `_get_expiry_date()`, and
      `next_inst` (the dict `get_next_contract_in_band`/`get_next_contract` returns) already
      carries a raw `expiry` field per `InstrumentLookup`'s own return type
      (`src/instruments/lookup.py::get_next_contract_in_band`, confirmed via
      `get_code_snippet`). Needs `parse_expiry()` + `.strftime("%b")` on both — no new lookup
      call.

**base_ditm_call variant — confirmed in a follow-up round this same session** (Animesh's
"come to DITM once we close the futures message" instruction, then two counter-proposal
rounds after the futures shape was confirmed). See `_build_message_ditm`'s own docstring for
the full confirmed layout and the specific differences from the futures variant (two-line
header with strike, "Debit"/"Credit" instead of "Contango"/"Backwardation", arrows kept
consistent with futures' ⬇️/⬆️ rather than the initially-proposed 📤/📥, gate-failure reason
explicitly dropped rather than guessed at). One real deferred item inside the DITM variant
itself: `check_ditm_liquidity_gate` (`paper_3track_roll.py:125-132`) collapses its two
independent checks (OI floor, bid/ask spread ceiling) into a single bool — a specific
"(Wide Bid/Ask)"-style reason on the gate line would need that function's return type changed
first, confirmed out of scope for this workshop pass.

**Also flagged, not yet confirmed on-device:** `⬇️`/`⬆️` (U+2B07/U+2B06) both carry the
emoji-presentation variation selector, same class of glyph FMT-1e flagged for `▶` inside a
fenced table. This message has no fence, so FMT-1e's alignment-breaking concern doesn't
technically apply, but confirm the stacked arrow+text rendering actually looks clean on-device
before locking this in — not yet verified live.

Not part of src/notifications/ — purely for iterating on layout before wiring into the real
script. Read-only w.r.t. the DB — makes zero DB calls. Sends a real Telegram message (counts
against the configured message budget).

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-10_3track_roll_notification_format <scenario> [--send]
    python -m scratch.2026-08-10_3track_roll_notification_format --list-scenarios
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import aiohttp

# Allow running as a plain script (python scratch/foo.py) as well as -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402

# ── Inline copies of MD-1's helpers (backbone/ not shipped yet — see module docstring) ──

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


def mdcode(value: str) -> str:
    """Wrap a dynamic identifier-like value as an inline code span.

    Mirrors MD-1's spec: falls back to escape_markdown() if value itself contains a
    backtick, rather than emitting a broken/nested code span.
    """
    if "`" in value:
        return escape_markdown(value)
    return f"`{value}`"


def format_money(value: Decimal, *, signed: bool = False) -> str:
    """2dp, comma thousands, ₹ prefix — mirrors FMT-2's format_money spec (not yet real code).

    Negative values: sign BEFORE the ₹ symbol per FMT-1's locked-in rule, not after.
    signed=True forces a leading '+' on positive values too (used for the P&L line, where
    "up vs. down" needs to be unambiguous at a glance — the plain default only distinguishes
    negative, per FMT-1's original spec, which is why this is a local override flag rather
    than changing format_money's default behavior for every other caller).
    """
    if value < 0:
        return f"-₹{-value:,.2f}"
    if signed and value > 0:
        return f"+₹{value:,.2f}"
    return f"₹{value:,.2f}"


# ── Display-label tables (still used by the deferred base_ditm_call placeholder shape) ──

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

LEG_ROLE_LABELS: dict[str, str] = {
    "base_futures": "Base Futures",
    "base_ditm_call": "Base DITM Call",
}

# Short, all-caps header token for the v3 DITM layout ("PROXY DITM CALL") — distinct from
# STRATEGY_LABELS' fuller "Proxy Track" form used by the deferred v1 placeholder. Scoped to
# only the strategies that actually carry a base_ditm_call leg (paper_nifty_proxy is the only
# one today per CONTEXT.md's src/paper/ section) plus base_futures' own short form for parity,
# even though the futures header hardcodes "NIFTY FUT" today rather than using this table —
# kept here so a future generalization (multiple proxy-style strategies) has a home.
STRATEGY_SHORT_LABELS: dict[str, str] = {
    "paper_nifty_proxy": "PROXY",
    "paper_nifty_futures": "FUTURES",
    "paper_nifty_spot": "SPOT",
}


def _short_label_strategy(strategy_name: str) -> str:
    try:
        return STRATEGY_SHORT_LABELS[strategy_name]
    except KeyError:
        raise ValueError(f"no short label mapped for strategy_name={strategy_name!r}") from None


def _label_strategy(strategy_name: str) -> str:
    try:
        return STRATEGY_LABELS[strategy_name]
    except KeyError:
        raise ValueError(f"no display label mapped for strategy_name={strategy_name!r}") from None


def _label_leg(leg_role: str) -> str:
    try:
        return LEG_ROLE_LABELS[leg_role]
    except KeyError:
        raise ValueError(f"no display label mapped for leg_role={leg_role!r}") from None


def _pnl_emoji(pnl: Decimal) -> str:
    """>0 -> green, <0 -> red, ==0 -> neutral. Distinct dict from FMT-1b's not-yet-real
    pnl_emoji() (which specs ✅/🔻/➖) — Animesh's confirmed example uses 🟢 for this specific
    message, kept as-is rather than forced into FMT-1b's palette; flag for reconciliation if
    FMT-1b's helper ships before this message's real port lands."""
    if pnl > 0:
        return "🟢"
    if pnl < 0:
        return "🔴"
    return "➖"


def _spread_label(spread: Decimal) -> str:
    """Calendar-spread sign -> curve-structure label. base_futures only."""
    if spread > 0:
        return "Contango"
    if spread < 0:
        return "Backwardation"
    return "Flat"


def _ditm_spread_label(spread: Decimal) -> str:
    """base_ditm_call's equivalent of _spread_label — option-premium terminology, not
    futures-curve terminology (per Animesh's confirmed correction that Contango/Backwardation
    is specifically a futures-curve concept). spread = open_price (new contract's premium) -
    close_price (old contract's premium): positive means the farther-dated call costs more to
    roll into (net Debit to the position), negative means it's cheaper (net Credit)."""
    if spread > 0:
        return "Debit"
    if spread < 0:
        return "Credit"
    return "Flat"


# ── Sample data ──
# futures_* scenarios carry the v3 fields (old_expiry/new_expiry for month labels, avg_cost/qty
# for P&L). ditm_call_* scenarios are still on the OLD v1 kv-line shape (deferred, see module
# docstring) and carry the older instrument_key/next_key fields that shape needs instead.

SCENARIOS: dict[str, dict] = {
    "futures_clean_pass": {
        "strategy_name": "paper_nifty_futures",
        "leg_role": "base_futures",
        "close_price": Decimal("24812.50"),
        "open_price": Decimal("24855.75"),
        "gate_passed": True,
        "partial": False,
        "avg_cost": Decimal("24500.00"),
        "qty": 25,
        "old_expiry": date(2026, 8, 25),
        "new_expiry": date(2026, 9, 29),
    },
    "futures_loss_backwardation": {
        "strategy_name": "paper_nifty_futures",
        "leg_role": "base_futures",
        "close_price": Decimal("24812.50"),
        "open_price": Decimal("24780.25"),
        "gate_passed": True,
        "partial": False,
        "avg_cost": Decimal("25100.00"),
        "qty": 25,
        "old_expiry": date(2026, 8, 25),
        "new_expiry": date(2026, 9, 29),
    },
    "futures_gate_warn": {
        "strategy_name": "paper_nifty_futures",
        "leg_role": "base_futures",
        "close_price": Decimal("24812.50"),
        "open_price": Decimal("24855.75"),
        "gate_passed": False,
        "partial": False,
        "avg_cost": Decimal("24500.00"),
        "qty": 25,
        "old_expiry": date(2026, 8, 25),
        "new_expiry": date(2026, 9, 29),
    },
    "futures_partial_roll": {
        "strategy_name": "paper_nifty_futures",
        "leg_role": "base_futures",
        "close_price": Decimal("24812.50"),
        "open_price": Decimal("24855.75"),
        "gate_passed": True,
        "partial": True,
        "avg_cost": Decimal("24500.00"),
        "qty": 25,
        "old_expiry": date(2026, 8, 25),
        "new_expiry": date(2026, 9, 29),
    },
    # v3 DITM layout — confirmed shape (Animesh, this session): strike-bearing ticket line,
    # "Debit"/"Credit" spread label instead of Contango/Backwardation, arrows kept consistent
    # with the futures message's ⬇️/⬆️ (explicitly confirmed — do not diverge to 📤/📥), gate
    # WARN reason omitted (check_ditm_liquidity_gate collapses OI+spread into one bool today,
    # see build_message_ditm's docstring).
    "ditm_call_warn": {
        "strategy_name": "paper_nifty_proxy",
        "leg_role": "base_ditm_call",
        "strike": 24000,
        "close_price": Decimal("86.68"),
        "open_price": Decimal("112.30"),
        "gate_passed": False,
        "partial": False,
        "avg_cost": Decimal("102.40"),
        "qty": 25,
        "old_expiry": date(2026, 8, 25),
        "new_expiry": date(2026, 9, 29),
    },
    "ditm_call_profit_credit": {
        "strategy_name": "paper_nifty_proxy",
        "leg_role": "base_ditm_call",
        "strike": 24000,
        "close_price": Decimal("112.30"),
        "open_price": Decimal("86.68"),
        "gate_passed": True,
        "partial": False,
        "avg_cost": Decimal("70.00"),
        "qty": 25,
        "old_expiry": date(2026, 9, 29),
        "new_expiry": date(2026, 10, 27),
    },
    "ditm_call_partial_roll": {
        "strategy_name": "paper_nifty_proxy",
        "leg_role": "base_ditm_call",
        "strike": 24000,
        "close_price": Decimal("86.68"),
        "open_price": Decimal("112.30"),
        "gate_passed": True,
        "partial": True,
        "avg_cost": Decimal("102.40"),
        "qty": 25,
        "old_expiry": date(2026, 8, 25),
        "new_expiry": date(2026, 9, 29),
    },
}


def build_message(d: dict) -> str:
    """v3 confirmed layout for base_futures rolls (Animesh's counter-proposal, this session):

        🔄 ROLL: NIFTY FUT [<old month> ➡️ <new month>]
        💰 P&L: <signed money> <pnl emoji>
        📐 Spread: <abs spread> pts (<Contango|Backwardation|Flat>)
        <blank line>
        ⬇️ OUT: <close money>
        ⬆️ IN: <open money>
        <gate/partial line>

    gate/partial line — one of:
        🚨 PARTIAL ROLL — VERIFY POSITIONS MANUALLY   (partial=True; overrides gate_passed)
        ✅ L\\-Gate: PASS                              (partial=False, gate_passed=True)
        ⚠️ L\\-Gate: WARN                              (partial=False, gate_passed=False)

    P&L: `pnl = (close_price - avg_cost) * qty` (see module docstring v2 note — avg_cost is
    the correct basis, this is a long leg). Spread: `open_price - close_price`; sign picks the
    Contango/Backwardation/Flat label via `_spread_label`. Month labels: `strftime("%b").upper()`
    on old_expiry/new_expiry (real port derives these from `expiry_date`/`next_inst["expiry"]`
    via `parse_expiry()` — see module docstring's data-availability audit).

    Escaping: header brackets `[` `]` and the leading `[`/`]` are MarkdownV2-reserved and
    escaped explicitly in the static template, same discipline as every other message in this
    epic ("static template text needs escaping too", backbone/stories.md). `L-Gate`'s hyphen is
    also reserved and escaped. The arrow/emoji glyphs themselves are never escaped — MarkdownV2
    reserves ASCII punctuation only, not arbitrary Unicode symbols/emoji.

    Dispatches to `_build_message_ditm` for `base_ditm_call` — see that function's own
    docstring for the DITM-specific layout (confirmed in a follow-up round this same session).
    """
    if d["leg_role"] != "base_futures":
        return _build_message_ditm(d)

    old_month = escape_markdown(d["old_expiry"].strftime("%b").upper())
    new_month = escape_markdown(d["new_expiry"].strftime("%b").upper())

    pnl = (d["close_price"] - d["avg_cost"]) * d["qty"]
    pnl_money = escape_markdown(format_money(pnl, signed=True))
    pnl_emoji = _pnl_emoji(pnl)

    spread = d["open_price"] - d["close_price"]
    spread_label = _spread_label(spread)
    spread_str = escape_markdown(f"{abs(spread):.2f}")

    close_money = escape_markdown(format_money(d["close_price"]))
    open_money = escape_markdown(format_money(d["open_price"]))

    if d["partial"]:
        gate_line = "🚨 PARTIAL ROLL — VERIFY POSITIONS MANUALLY"
    elif d["gate_passed"]:
        gate_line = "✅ L\\-Gate: PASS"
    else:
        gate_line = "⚠️ L\\-Gate: WARN"

    lines = [
        f"🔄 ROLL: NIFTY FUT \\[{old_month} ➡️ {new_month}\\]",
        f"💰 P&L: {pnl_money} {pnl_emoji}",
        f"📐 Spread: {spread_str} pts \\({spread_label}\\)",
        "",
        f"⬇️ OUT: {close_money}",
        f"⬆️ IN: {open_money}",
        gate_line,
    ]
    return "\n".join(lines)


def _build_message_ditm(d: dict) -> str:
    """v3 confirmed layout for base_ditm_call rolls (Animesh's second counter-proposal round,
    same session as the futures v3 layout):

        🔄 ROLL: <STRATEGY> DITM CALL
        🎟️ [NIFTY <strike> CE] <old month> ➡️ <new month>
        💰 P&L: <signed money> <pnl emoji>
        📐 Spread: <abs spread> pts (<Debit|Credit|Flat>)
        <blank line>
        ⬇️ OUT: <close money>
        ⬆️ IN: <open money>
        <gate/partial line>

    Differences from the futures v3 layout (`build_message`), both explicitly confirmed:
    - Header is two lines here (strategy + ticket/strike/month), not one — the strike never
      changes on this roll (`InstrumentLookup.get_next_contract_in_band` matches strike
      exactly, confirmed via its docstring/implementation), so it's a fixed identity fact
      worth surfacing, unlike futures where there's no strike concept at all.
    - Spread label is "Debit"/"Credit" (`_ditm_spread_label`), not "Contango"/"Backwardation"
      — that terminology is specific to futures curve structure and doesn't apply to an
      option-premium difference between two expiries of the same strike (Animesh's
      correction, this session).
    - OUT/IN arrows are the SAME ⬇️/⬆️ as the futures message (explicitly confirmed — an
      earlier draft used 📤/📥 for visual distinction, rejected in favor of consistency across
      both leg-role variants of this message).
    - Gate line intentionally omits a failure reason (e.g. "(Wide Bid/Ask)") — confirmed
      out of scope for this workshop pass. `check_ditm_liquidity_gate`
      (`paper_3track_roll.py:125-132`) collapses two independent checks
      (`oi >= PROXY_OI_MIN`, `spread <= PROXY_SPREAD_MAX`) into a single bool today; surfacing
      which one failed needs that function's return type changed first (a real ROLL-9
      implementation task, not a formatting change) — deferred, not silently dropped.

    `pos.avg_cost`/`abs(pos.net_qty)` P&L basis, `expiry_date`/`next_inst["expiry"]` month
    derivation — same data-availability audit as the futures variant (module docstring).
    `strike` itself is already resolvable without a new fetch: `_get_expiry_date` and the
    `get_next_contract_in_band` call both already go through `InstrumentLookup.get_by_key`
    internally, whose returned dict carries `strike_price` — the real implementation reads it
    off the same lookup, not a separate call.
    """
    strategy_short = escape_markdown(_short_label_strategy(d["strategy_name"]))
    old_month = escape_markdown(d["old_expiry"].strftime("%b").upper())
    new_month = escape_markdown(d["new_expiry"].strftime("%b").upper())

    pnl = (d["close_price"] - d["avg_cost"]) * d["qty"]
    pnl_money = escape_markdown(format_money(pnl, signed=True))
    pnl_emoji = _pnl_emoji(pnl)

    spread = d["open_price"] - d["close_price"]
    spread_label = _ditm_spread_label(spread)
    spread_str = escape_markdown(f"{abs(spread):.2f}")

    close_money = escape_markdown(format_money(d["close_price"]))
    open_money = escape_markdown(format_money(d["open_price"]))

    if d["partial"]:
        gate_line = "🚨 PARTIAL ROLL — VERIFY POSITIONS MANUALLY"
    elif d["gate_passed"]:
        gate_line = "✅ L\\-Gate: PASS"
    else:
        gate_line = "⚠️ L\\-Gate: WARN"

    lines = [
        f"🔄 ROLL: {strategy_short} DITM CALL",
        f"🎟️ \\[NIFTY {d['strike']} CE\\] {old_month} ➡️ {new_month}",
        f"💰 P&L: {pnl_money} {pnl_emoji}",
        f"📐 Spread: {spread_str} pts \\({spread_label}\\)",
        "",
        f"⬇️ OUT: {close_money}",
        f"⬆️ IN: {open_money}",
        gate_line,
    ]
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
    scenario = sys.argv[1] if len(sys.argv) > 1 else "futures_clean_pass"
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
