#!/usr/bin/env python3
"""S5.5 discussion aid — render (and optionally send) every Telegram message the
signals pipeline emits, current + proposed.

Not a cron, not tested. Dummy values only.

  python scratch/2026-09-08_signal_telegram_messages.py           # list + print all
  python scratch/2026-09-08_signal_telegram_messages.py 3         # print only message 3
  python scratch/2026-09-08_signal_telegram_messages.py 3 --send  # push only message 3
                                                                  # (needs TELEGRAM_* env)

CURRENT (live in morning_signal.py):
  - directional consensus / NO_TRADE split / NO_TRADE no-responses

PROPOSED (S5.5a — reference renderer for record_signal_outcome.py EOD push):
  - executed / skipped / NO_TRADE outcome messages with P&L
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from scripts.morning_signal import _format_signal_notification
from src.notifications.formatting import format_money, pnl_emoji
from src.notifications.markdown import escape_markdown
from src.notifications.telegram import build_notifier
from src.paper.constants import LOT_SIZE
from src.signals.models import (
    DailySignal,
    Direction,
    SignalOutcome,
    SignalResponse,
    TradeAction,
)

load_dotenv()

_ACTION_LABEL = {TradeAction.BUY_CALL: "BUY CALL", TradeAction.BUY_PUT: "BUY PUT"}


def _resp(provider: str, direction: Direction, conf: int, strike: int) -> SignalResponse:
    return SignalResponse(
        trade_date=date(2026, 9, 8),
        provider=provider,
        direction=direction,
        confidence=conf,
        recommended_strike=strike,
        entry_premium_low=Decimal("58.00"),
        entry_premium_high=Decimal("72.00"),
        key_reason="GIFT Nifty +0.6%, PCR 1.3, FII cash +2400cr — bid supportive.",
        key_risk="US CPI print tonight; a hot number reverses the gap.",
        raw_response="{}",
    )


_E = escape_markdown


def format_directional_v3(signal: DailySignal) -> str:
    """Message 1 candidate (Animesh, 2026-09-08) — header + strike/confidence + vote block.

    Formatter owns escaping; send WITHOUT re-wrapping.
    """
    if signal.trade_action is TradeAction.NO_TRADE:
        if not signal.responses:
            return (
                f"*{_E('🚨 SIGNAL PIPELINE FAILED')}*\n"
                f"\n"
                f"{_E('❌ 0 / 3 models responded')}\n"
                f"{_E('⏸ No signal issued today')}\n"
                f"\n"
                f"{_E('👉 Check logs before the next run')}"
            )
        pm = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "➖"}
        lines = "\n".join(
            _E(f"{pm[r.direction.value]} {r.provider}: {r.direction.value}")
            for r in signal.responses
        )
        return f"*{_E('⏸ NO TRADE · NO CONSENSUS')}*\n\n{lines}"

    emoji = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "⏸"}[signal.consensus_direction.value]
    agree = ", ".join(signal.agreeing_models) or "—"
    dissent = ", ".join(signal.dissenting_models) or "—"
    top = max(
        (r for r in signal.responses if r.provider in signal.agreeing_models),
        key=lambda r: r.confidence,
    )
    band = f"₹{top.entry_premium_low:.2f} – ₹{top.entry_premium_high:.2f}"
    return (
        f"*{_E(f'{emoji} CONSENSUS: {signal.consensus_direction.value}')}*\n"
        f"\n"
        f"{_E(f'🎯 Strike: {signal.recommended_strike}')}\n"
        f"{_E(f'📊 Confidence: {signal.consensus_confidence} / 5.0')}\n"
        f"{_E(f'💰 Entry band: {band}')}\n"
        f"\n"
        f"*{_E('Model Votes:')}*\n"
        f"{_E(f'👍 Agree: {agree}')}\n"
        f"{_E(f'👎 Dissent: {dissent}')}"
    )


def format_directional_v2(signal: DailySignal) -> str:
    """PROPOSED S5.5c — formatter owns its escaping, emits literal * for bold.

    Caller must send this WITHOUT re-wrapping in escape_markdown().
    """
    if signal.trade_action is TradeAction.NO_TRADE:
        votes = ", ".join(f"{r.provider}: {r.direction.value}" for r in signal.responses)
        body = _E(f"split signal ({votes})") if votes else _E("no responses")
        return f"*⏸ NO TRADE*\n{body}"

    top = max(
        (r for r in signal.responses if r.provider in signal.agreeing_models),
        key=lambda r: r.confidence,
    )
    emoji = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "⏸"}[signal.consensus_direction.value]
    band = f"₹{top.entry_premium_low:.2f}–₹{top.entry_premium_high:.2f}"
    return (
        f"*{_E(f'{emoji} DIRECTIONAL CONSENSUS · {signal.consensus_direction.value}')}*\n"
        f"{_E(f'Strike: {signal.recommended_strike} · Confidence: {signal.consensus_confidence}/5')}\n"
        f"{_E(f'Entry band: {band}')}\n"
        f"{_E('Agree: ' + (', '.join(signal.agreeing_models) or '—') + ' · Dissent: ' + (', '.join(signal.dissenting_models) or '—'))}\n"
        f"{_E('Why: ' + top.key_reason)}\n"
        f"{_E('Risk: ' + top.key_risk)}"
    )


# --------------------------------------------------------------------------- #
# PROPOSED renderer — S5.5a reference implementation
# --------------------------------------------------------------------------- #
def format_outcome_notification(outcome: SignalOutcome, signal: DailySignal) -> str:
    """PROPOSED S5.5a — formatter owns its escaping; send WITHOUT re-wrapping."""
    day = outcome.trade_date.strftime("%d %b")
    header = f"*{_E(f'📊 SIGNAL OUTCOME · {day}')}*"
    close = _E(f"Nifty close {outcome.nifty_close:,.0f}")

    if outcome.trade_action is TradeAction.NO_TRADE:
        return f"{header}\n{_E('NO TRADE')}  ·  {close}"

    action = _ACTION_LABEL[outcome.trade_action]
    line1 = _E(f"{signal.consensus_direction.value} · {action} {outcome.recommended_strike}")

    if not outcome.executed:
        exit_str = format_money(outcome.exit_premium) if outcome.exit_premium is not None else "—"
        return f"{header}\n{line1} · {_E('NOT TAKEN')}\n{_E(f'Exit {exit_str} (would-be)')}  ·  {close}"

    total = outcome.pnl_per_lot or Decimal("0")
    pnl = f"{pnl_emoji(total)} {_E(format_money(total, signed=True))} / lot"
    return (
        f"{header}\n{line1}\n"
        f"{_E(f'Entry {format_money(outcome.entry_premium)} → Exit {format_money(outcome.exit_premium)}')}  ·  {pnl}\n"
        f"{close}  ·  {_E('phase ' + outcome.phase)}"
    )


# --------------------------------------------------------------------------- #
# Scenarios
# --------------------------------------------------------------------------- #
_SIGNAL_BUY = DailySignal(
    trade_date=date(2026, 9, 8),
    responses=[
        _resp("grok", Direction.BULLISH, 4, 24800),
        _resp("gpt4o", Direction.BULLISH, 3, 24800),
        _resp("gemini", Direction.BEARISH, 2, 24750),
    ],
    consensus_direction=Direction.BULLISH,
    consensus_confidence=Decimal("3.5"),
    trade_action=TradeAction.BUY_CALL,
    recommended_strike=24800,
    agreeing_models=["grok", "gpt4o"],
    dissenting_models=["gemini"],
)
_SIGNAL_SPLIT = DailySignal(
    trade_date=date(2026, 9, 8),
    responses=[
        _resp("grok", Direction.BULLISH, 3, 24800),
        _resp("gpt4o", Direction.BEARISH, 3, 24750),
        _resp("gemini", Direction.NEUTRAL, 2, 24800),
    ],
    consensus_direction=Direction.NEUTRAL,
    consensus_confidence=Decimal("0"),
    trade_action=TradeAction.NO_TRADE,
    recommended_strike=None,
    agreeing_models=[],
    dissenting_models=["grok", "gpt4o", "gemini"],
)
_SIGNAL_EMPTY = _SIGNAL_SPLIT.model_copy(update={"responses": [], "dissenting_models": []})

_OUT_EXEC = SignalOutcome(
    trade_date=date(2026, 9, 8),
    trade_action=TradeAction.BUY_CALL,
    recommended_strike=24800,
    entry_premium=Decimal("65.50"),
    exit_premium=Decimal("92.00"),
    pnl_per_lot=(Decimal("92.00") - Decimal("65.50")) * LOT_SIZE,
    nifty_close=Decimal("24842.10"),
    executed=True,
)
_OUT_SKIP = _OUT_EXEC.model_copy(
    update={"executed": False, "entry_premium": None, "pnl_per_lot": None}
)
_OUT_NOTRADE = SignalOutcome(
    trade_date=date(2026, 9, 8),
    trade_action=TradeAction.NO_TRADE,
    recommended_strike=None,
    entry_premium=None,
    exit_premium=None,
    pnl_per_lot=None,
    nifty_close=Decimal("24842.10"),
    executed=False,
)

# Every entry is already MarkdownV2-escaped (formatter owns the boundary) — send verbatim.
# Index = the number you pass on the CLI. Maps to a subtask in signals_tasks.md.
MESSAGES: list[tuple[str, str, str]] = [
    ("S5.5c", "directional consensus", format_directional_v3(_SIGNAL_BUY)),
    ("S5.5c", "NO_TRADE · split vote", format_directional_v3(_SIGNAL_SPLIT)),
    ("S5.5c", "NO_TRADE · no responses", format_directional_v3(_SIGNAL_EMPTY)),
    (
        "S5.5c",
        "CURRENT baseline · directional (for comparison)",
        _E(_format_signal_notification(_SIGNAL_BUY)),
    ),
    (
        "S5.5c",
        "CURRENT baseline · NO_TRADE (for comparison)",
        _E(_format_signal_notification(_SIGNAL_SPLIT)),
    ),
    ("S5.5a", "PROPOSED · outcome executed", format_outcome_notification(_OUT_EXEC, _SIGNAL_BUY)),
    ("S5.5a", "PROPOSED · outcome skipped", format_outcome_notification(_OUT_SKIP, _SIGNAL_BUY)),
    (
        "S5.5a",
        "PROPOSED · outcome NO_TRADE",
        format_outcome_notification(_OUT_NOTRADE, _SIGNAL_SPLIT),
    ),
]


def _print_one(idx: int) -> str:
    task, title, escaped = MESSAGES[idx - 1]
    print("=" * 72)
    print(f"[{idx}] {task} — {title}")
    print("-" * 72)
    print(escaped)
    print()
    return escaped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("n", nargs="?", type=int, help="1-based message index (omit for all).")
    parser.add_argument(
        "--send", action="store_true", help="Push the selected message(s) to Telegram."
    )
    parser.add_argument(
        "--bare",
        action="store_true",
        help="Send with no [idx] identifying prefix — the real message.",
    )
    args = parser.parse_args()

    if args.n is not None and not 1 <= args.n <= len(MESSAGES):
        parser.error(f"n must be 1..{len(MESSAGES)}")

    notifier = build_notifier() if args.send else None
    if args.send and notifier is None:
        print("--send given but TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — printing only.\n")

    print("Messages (index → subtask):")
    for i, (task, title, _t) in enumerate(MESSAGES, 1):
        print(f"  {i}. {task}  {title}")
    print()

    indices = [args.n] if args.n is not None else range(1, len(MESSAGES) + 1)
    for idx in indices:
        task, title, _t = MESSAGES[idx - 1]
        escaped = _print_one(idx)
        if notifier is not None:
            payload = (
                escaped if args.bare else f"*\\[{idx}\\] {_E(task + ' — ' + title)}*\n{escaped}"
            )
            ok = asyncio.run(notifier.send(payload))
            print(f"  → telegram send: {'ok' if ok else 'FAILED'}\n")


if __name__ == "__main__":
    main()
