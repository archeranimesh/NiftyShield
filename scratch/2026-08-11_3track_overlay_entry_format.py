"""Scratch script — 3-Track OVERLAY ENTRY bootstrap notification Telegram message formatting.

Message #7b in docs/plan/telegram-markdown-migration/TODO.md's "Confirmed missing" queue
(item 7's second half — split from 7a on 2026-08-11 since the two call sites are structurally
distinct messages; see ROLL-13 for 7a's base-entry-bootstrap spec).

Real call site: `scripts/strategies/three_track/paper_3track_overlay_entry.py::main`,
~line 1410 (`notifier.send(msg)` inside the `if not args.dry_run:` / `if notifier:` block).
Fires once, at bootstrap, for whichever overlay type (`pp`/`cc`/`collar`) was just entered via
`--auto-pp`/`--auto-cc`/`--auto-collar` or a YAML config (`--config`).

**backbone/ (MD-1..MD-5) status as of this session: NOT shipped** — confirmed via
`search_graph("mdcode")` returning zero hits under src/notifications/ (same check as every
prior scratch script this epic). This script inlines its own copies of `escape_markdown()` /
`format_money()`, matching MD-1's spec.

Original source (mangled em-dash/rupee-sign/triangle encoding fixed here to real characters):
    notifier = build_notifier()
    if notifier:
        lines = [f"🎯 OVERLAY ENTRY — {cfg.overlay_type.upper()} bootstrap"]
        for ot in overlay_trades:
            lines.append(f"{ot.leg_role}: {ot.trade.instrument_key} @ ₹{ot.trade.price}")
        if gate_violation is not None:
            lines.append(
                f"⚠ Gate logged: {gate_violation.gate_name} "
                f"(threshold={gate_violation.threshold}, actual={gate_violation.actual})"
            )
        msg = "\n".join(lines)
        asyncio.run(notifier.send(msg))

v1 (THIS VERSION — drafted directly from ROLL-13's confirmed conventions rather than starting
from a raw-key v1 draft, since 7a already walked the "raw key -> resolved label" arc and there
is no reason to re-walk it for a near-identical message; still presented for Animesh's
confirmation/live-send before being written back, per the workshop's own discipline —
"confirmed" below means "this session's opening proposal", not yet locked until a live --send
round trip is reviewed on-device, same as 7a's process):

Resolved human-readable instrument labels instead of the raw `instrument_key` (matches
ROLL-12's and ROLL-13's established direction), `Long`/`Short` verb derived from the leg's
real `TradeAction` — **NOT uniformly `Long` like ROLL-13's base-entry message**, because
overlay legs are genuinely mixed direction: confirmed via `get_code_snippet` on
`build_overlay_trades()`, not assumed — `overlay_pp`/`overlay_collar_put` are `TradeAction.BUY`
(long puts), `overlay_cc`/`overlay_collar_call` are `TradeAction.SELL` (short calls). Explicit
lot count (`cfg.lot_size`, real field, same "always exactly one lot" contract as ROLL-13's
futures/proxy legs). Strike/month/right resolved from real `OverlayConfig` fields
(`put_strike`/`call_strike`, `expiry` — confirmed via `get_code_snippet`, not fabricated); right
is hardcoded PE/CE per leg role, not derived, since a put leg is always `overlay_pp`/
`overlay_collar_put` and a call leg is always `overlay_cc`/`overlay_collar_call` by
construction (`build_overlay_trades()` never mixes these).

v1.1 (Animesh's counter-proposal, same session): per-leg marker is direction-coded, not a
uniform ROLL-13-style `📥` — 🟢 for a `Long` leg, 🔴 for a `Short` leg, since this message
(unlike ROLL-13's base entry) genuinely mixes both directions and a same-glyph marker on every
line loses that signal at a glance. Headline keeps `📥` as the bootstrap-event marker — the
direction split only applies to per-leg lines, which are the only lines with a verb to encode.

Gate-violation line kept as a distinct trailing line when present (`GateViolation.threshold`/
`.actual` are already pre-formatted `str` fields on the real Pydantic model — confirmed via
`get_code_snippet` on `src/paper/models.py::GateViolation` — so no numeric formatting needed,
just `escape_markdown()`).

Shape:
    📥 Overlay Entry — <TYPE> Bootstrap
    🟢 <Leg Label>: Long <lot_size>x NIFTY <MON> <strike> PE @ ₹<price>   [BUY leg]
    🔴 <Leg Label>: Short <lot_size>x NIFTY <MON> <strike> CE @ ₹<price>  [SELL leg]
    [one line per leg — 1 for pp/cc, 2 for collar]
    ⚠️ Gate Logged: <gate_name> \\(threshold=<threshold>, actual=<actual>\\)   [only if a
                                                                                soft IVR gate
                                                                                was breached]

Leg-role label/right mapping (fixed, not derived):
    overlay_pp          -> "Overlay PP",   PE, TradeAction.BUY  -> Long
    overlay_cc           -> "Overlay CC",   CE, TradeAction.SELL -> Short
    overlay_collar_put   -> "Collar Put",   PE, TradeAction.BUY  -> Long
    overlay_collar_call  -> "Collar Call",  CE, TradeAction.SELL -> Short

Escaping discipline carried over from ROLL-13 (both were live-caught bugs there, applying the
same sweep here before any --send):
    1. Literal '=' in static template text (the gate-violation line's "threshold=" / "actual=")
       needs explicit `\\=` — MarkdownV2 reserves '=', `escape_markdown()` only ever runs on
       dynamic values.
    2. Em dash (—, U+2014) is NOT MarkdownV2-reserved — never escaped, per ROLL-13's finding.

Not part of src/notifications/ — purely for iterating on layout before wiring into the real
script. Makes zero DB calls. Sends a real Telegram message (counts against the configured
message budget).

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-11_3track_overlay_entry_format <scenario> [--send]
    python -m scratch.2026-08-11_3track_overlay_entry_format --list-scenarios
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


def format_money(value: Decimal) -> str:
    """2dp, comma thousands, ₹ prefix — mirrors FMT-2's format_money spec (not yet real code).

    ₹ itself is NOT MarkdownV2-reserved, so it's never escaped; only the numeric '.' gets
    escaped, via escape_markdown() wrapping this function's *output* at the call site.
    """
    return f"₹{value:,.2f}"


def _month_label(iso_date: str) -> str:
    """ISO date string -> 3-letter uppercase month, same convention as ROLL-13/ROLL-9."""
    return date.fromisoformat(iso_date).strftime("%b").upper()


# Fixed leg-role -> (display label, option right, verb) mapping. NOT derived at runtime from
# TradeAction — confirmed once via build_overlay_trades(), then hardcoded here, same
# discipline ROLL-7/ROLL-8's STRATEGY_LABELS/LEG_ROLE_LABELS dicts use (an unmapped role should
# raise, not silently guess).
LEG_META: dict[str, tuple[str, str, str]] = {
    "overlay_pp": ("Overlay PP", "PE", "Long"),
    "overlay_cc": ("Overlay CC", "CE", "Short"),
    "overlay_collar_put": ("Collar Put", "PE", "Long"),
    "overlay_collar_call": ("Collar Call", "CE", "Short"),
}


def _leg_meta(leg_role: str) -> tuple[str, str, str]:
    try:
        return LEG_META[leg_role]
    except KeyError:
        raise ValueError(f"no display mapping for leg_role={leg_role!r}") from None


# ── Sample data — mirrors real OverlayConfig/GateViolation fields (confirmed via
# get_code_snippet on build_overlay_trades()/OverlayConfig/GateViolation this session). ──

SCENARIOS: dict[str, dict] = {
    "pp_bootstrap": {
        "overlay_type": "pp",
        "lot_size": 65,
        "expiry": "2026-09-29",
        "legs": [
            {"leg_role": "overlay_pp", "strike": 23500, "price": Decimal("142.10")},
        ],
        "gate_violation": None,
    },
    "cc_bootstrap": {
        "overlay_type": "cc",
        "lot_size": 65,
        "expiry": "2026-09-29",
        "legs": [
            {"leg_role": "overlay_cc", "strike": 24800, "price": Decimal("185.20")},
        ],
        "gate_violation": None,
    },
    "collar_bootstrap": {
        "overlay_type": "collar",
        "lot_size": 65,
        "expiry": "2026-09-29",
        "legs": [
            {"leg_role": "overlay_collar_put", "strike": 23500, "price": Decimal("142.10")},
            {"leg_role": "overlay_collar_call", "strike": 24800, "price": Decimal("185.20")},
        ],
        "gate_violation": None,
    },
    "cc_bootstrap_gate_logged": {
        "overlay_type": "cc",
        "lot_size": 65,
        "expiry": "2026-09-29",
        "legs": [
            {"leg_role": "overlay_cc", "strike": 24800, "price": Decimal("185.20")},
        ],
        "gate_violation": {
            "gate_name": "ivr_cc_reentry",
            "threshold": "0.25",
            "actual": "0.19",
        },
    },
}


def build_message(d: dict) -> str:
    """v1 layout for paper_3track_overlay_entry.py's OVERLAY ENTRY notify block, MarkdownV2-safe.

    See module docstring for the full shape, derivation notes, and escaping discipline.
    Not yet Animesh-confirmed — first draft this session, pending live-send review.
    """
    month = escape_markdown(_month_label(d["expiry"]))
    lines = [f"📥 Overlay Entry — {d['overlay_type'].upper()} Bootstrap"]

    for leg in d["legs"]:
        label, right, verb = _leg_meta(leg["leg_role"])
        strike = escape_markdown(f"{leg['strike']:.0f}")
        price = escape_markdown(format_money(leg["price"]))
        marker = "🟢" if verb == "Long" else "🔴"
        lines.append(
            f"{marker} {label}: {verb} {d['lot_size']}x NIFTY {month} {strike} {right} @ {price}"
        )

    gv = d.get("gate_violation")
    if gv is not None:
        gate_name = escape_markdown(gv["gate_name"])
        threshold = escape_markdown(gv["threshold"])
        actual = escape_markdown(gv["actual"])
        lines.append(
            f"⚠️ Gate Logged: {gate_name} \\(threshold\\={threshold}, actual\\={actual}\\)"
        )

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
    scenario = sys.argv[1] if len(sys.argv) > 1 else "collar_bootstrap"
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
