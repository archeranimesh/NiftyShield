"""Scratch script — 3-Track BASE ENTRY bootstrap notification Telegram message formatting.

Message #7a in docs/plan/telegram-markdown-migration/TODO.md's "Confirmed missing" queue
(item 7, split per Animesh's 2026-08-11 decision — 7a done this session, 7b deferred to a
separate session since the two call sites are structurally distinct messages).

Real call site: `scripts/strategies/three_track/paper_3track_entry.py::main`, ~line 940
(`notifier.send(msg)` inside the `if args.confirm:` / `if notifier:` block). Fires once, at
bootstrap, when one or more of {spot, futures, proxy} tracks are entered for the first time
via `--confirm` (optionally scoped with `--auto-futures`/`--auto-ditm`/`--tracks`).

**backbone/ (MD-1..MD-5) status as of this session: NOT shipped** — confirmed via
`search_graph("mdcode")` returning zero hits under src/notifications/. This script inlines
its own copies of `escape_markdown()` / `mdcode()`, matching MD-1's spec, same as every prior
scratch script in this epic (2026-08-08_reentry_notice_format.py, etc.).

Original source (mangled em-dash/rupee-sign encoding fixed here to real characters):
    lines = [f"🎯 BASE ENTRY — 3-Track bootstrap ({', '.join(sorted(tracks_to_enter))})"]
    lines.append(f"Cycle: {args.cycle}")
    if STRATEGY_SPOT in tracks_to_enter:
        lines.append(f"Spot: NIFTYBEES qty={prices.niftybees_qty} @ ₹{prices.niftybees_ltp}")
    if STRATEGY_FUTURES in tracks_to_enter:
        lines.append(f"Futures: {prices.futures_key} @ ₹{prices.futures_price}")
    if STRATEGY_PROXY in tracks_to_enter:
        lines.append(
            f"Proxy: {prices.proxy_instrument_key} @ ₹{prices.proxy_price} "
            f"(Δ={prices.proxy_actual_delta})"
        )
    msg = "\n".join(lines)

v1 (superseded, kept only in git history via this session's earlier commit — see TODOS.md):
kv-lines with raw broker instrument_key wrapped in `mdcode()`, `Cycle:` line kept.

v2 (Animesh-confirmed 2026-08-11, replacing v1 wholesale after a counter-proposal round):
resolved human-readable instrument labels instead of raw broker keys — matches this epic's
established direction (item 6/ROLL-12 already walked away from raw identifiers as "cryptic"
in favor of resolved labels; v1's raw-key choice here was a step backward, not a new
pattern). Unified `Long` verb for all three legs (all three are `TradeAction.BUY` per
`build_trades()` — confirmed via `get_code_snippet`, not assumed), explicit lot count on
every leg (`futures`/`proxy` both trade `quantity=p.lot_size` — a real field, confirmed via
`build_trades()`, not invented). `Cycle:` line dropped entirely as internal-only bookkeeping
noise with no trading meaning to a reader glancing at their phone (cf. ROLL-10's "Action:
line dropped as fabricated-data" precedent for trimming operator-only clutter) — this was
the v1 module docstring's open question, now resolved.

v2.1 (live-send correction, same 2026-08-11 session): first v2 pass put 📥 on the headline
only, dropping it from the three leg lines — a misreading of Animesh's original counter-
proposal, which used 📥 as a per-line marker (one per action line, not a single message-level
anchor). Confirmed via an actual --send round trip landing on-device and Animesh flagging the
per-line emoji as missing. Restored: 📥 prefixes every leg line as well as the headline.

Shape:
    📥 Base Entry — 3\\-Track Bootstrap
    📥 Spot: Long <niftybees_qty>x NIFTYBEES @ ₹<niftybees_ltp>
    📥 Futures: Long <lot_size>x NIFTY <MON> FUT @ ₹<futures_price>
    📥 Proxy: Long <lot_size>x NIFTY <MON> <strike> CE @ ₹<proxy_price> \\(Δ\\=<delta>\\)

Instrument-label derivation, resolved from real `LivePrices` fields (not fabricated):
    - Futures: month comes from `futures_expiry` (the `derive_expiry()` result passed into
      `fetch_live_prices()`, an ISO date string) — `date.fromisoformat(...).strftime("%b").upper()`.
      Right/strike don't apply (NIFTY futures, not an option).
    - Proxy: strike comes from `p.proxy_strike` (real field, already used in `build_trades()`'s
      `notes=` string as `strike={p.proxy_strike:.0f}`), month from `p.expiry` (real field,
      `proxy_row["expiry"]`, also an ISO date string). Right is hardcoded `CE` — proxy is
      always `leg_role="base_ditm_call"`, never a put, per `build_trades()`.
    - Spot: no derivation needed, `NIFTYBEES` is a fixed ticker (`NIFTYBEES_KEY` constant).

Escaping notes carried over from v1 (both were live 400s / silent literal-backslash bugs this
session, keep the discipline going forward):
    1. Literal '=' in static template text (not just dynamic values) must be explicitly
       `\\=` — MarkdownV2 reserves '=' and Telegram 400s on it unescaped, even in text Claude
       wrote itself. `escape_markdown()` only ever runs on dynamic values here.
    2. Em dash (—, U+2014) is NOT MarkdownV2-reserved — Telegram reserves ASCII punctuation
       only (`_*[]()~\`>#+-=|{}.!`). An unescaped `\` before it doesn't error, it silently
       renders as a literal backslash — this class of bug isn't caught by a live --send round
       trip failing, only by checking the actual reserved-char list.

Not part of src/notifications/ — purely for iterating on layout before wiring into the real
script. Makes zero DB calls. Sends a real Telegram message (counts against the configured
message budget).

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-11_3track_base_entry_format <scenario> [--send]
    python -m scratch.2026-08-11_3track_base_entry_format --list-scenarios
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

    ₹ itself is NOT MarkdownV2-reserved (ASCII punctuation only), so it's never escaped; only
    the numeric '.' gets escaped, via escape_markdown() wrapping this function's *output* at
    the call site, same pattern as every prior scratch script in this epic.
    """
    return f"₹{value:,.2f}"


def _fmt_delta(value: Decimal) -> str:
    """Greeks: 2dp, explicit sign, per CLAUDE.md formatting-rules. Escaped at call site."""
    return f"{value:+.2f}"


def _month_label(iso_date: str) -> str:
    """ISO date string -> 3-letter uppercase month (`2026-12-30` -> `DEC`).

    Matches 2026-08-10_3track_roll_notification_format.py's month-derivation convention
    (`strftime("%b").upper()`), applied here to plain ISO strings rather than date objects
    since that's what `futures_expiry`/`p.expiry` actually are in this script's call sites.
    """
    return date.fromisoformat(iso_date).strftime("%b").upper()


# ── Sample data — mirrors the real LivePrices-shaped fields (confirmed via get_code_snippet
# on fetch_live_prices()/build_trades() this session, not guessed). ──

SCENARIOS: dict[str, dict] = {
    "all_three": {
        "tracks_to_enter": {"spot", "futures", "proxy"},
        "lot_size": 65,
        "niftybees_qty": 480,
        "niftybees_ltp": Decimal("281.45"),
        "futures_expiry": "2026-12-31",
        "futures_price": Decimal("24850.00"),
        "proxy_strike": Decimal("24500"),
        "expiry": "2026-12-31",
        "proxy_price": Decimal("612.30"),
        "proxy_actual_delta": Decimal("0.72"),
    },
    "futures_only": {
        "tracks_to_enter": {"futures"},
        "lot_size": 65,
        "futures_expiry": "2026-12-31",
        "futures_price": Decimal("24850.00"),
    },
    "proxy_only": {
        "tracks_to_enter": {"proxy"},
        "lot_size": 65,
        "proxy_strike": Decimal("25200"),
        "expiry": "2027-03-25",
        "proxy_price": Decimal("612.30"),
        "proxy_actual_delta": Decimal("-0.31"),
    },
}


def build_message(d: dict) -> str:
    """v2 layout for paper_3track_entry.py's BASE ENTRY notify block, MarkdownV2-safe.

    See module docstring for the full shape, derivation notes, and escaping discipline.
    """
    tracks = d["tracks_to_enter"]
    lines = ["📥 Base Entry — 3\\-Track Bootstrap"]

    if "spot" in tracks:
        ltp = escape_markdown(format_money(d["niftybees_ltp"]))
        lines.append(f"📥 Spot: Long {d['niftybees_qty']}x NIFTYBEES @ {ltp}")

    if "futures" in tracks:
        month = escape_markdown(_month_label(d["futures_expiry"]))
        price = escape_markdown(format_money(d["futures_price"]))
        lines.append(f"📥 Futures: Long {d['lot_size']}x NIFTY {month} FUT @ {price}")

    if "proxy" in tracks:
        month = escape_markdown(_month_label(d["expiry"]))
        strike = escape_markdown(f"{d['proxy_strike']:.0f}")
        price = escape_markdown(format_money(d["proxy_price"]))
        delta = escape_markdown(_fmt_delta(d["proxy_actual_delta"]))
        lines.append(
            f"📥 Proxy: Long {d['lot_size']}x NIFTY {month} {strike} CE @ {price} "
            f"\\(Δ\\={delta}\\)"
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
    scenario = sys.argv[1] if len(sys.argv) > 1 else "all_three"
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
