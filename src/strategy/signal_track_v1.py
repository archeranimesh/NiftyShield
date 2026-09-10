"""SignalTrackV1 — paper-trade the multi-LLM daily directional consensus (SPT-3).

The `signals/` epic produces a consensus `DailySignal` each morning; this module
turns it into a simulated long-option paper position on the shared
`paper_signal_track_v1` namespace (`paper_trades` + `paper_signal_entries`).

Two surfaces:

* `open_signal_paper_entry(...)` — the entry hook. Both the SPT-6
  `morning_signal` tail-call and the manual `signal_paper_entry.py` backfill
  tool call this identical async callable so they can never diverge. It
  resolves the monthly option, fetches its own bid/ask quote, takes a
  simulated `PaperFillSimulator` BUY fill, freezes a `SignalPaperEntry`, and
  sends the Telegram entry message. NO_TRADE / already-open are logged no-ops.
* `SignalTrackV1` — the `PaperStrategy` shell registered with `StrategyMonitor`.
  SPT-4 fills in the per-tick mark-path + exit routing; SPT-3 only establishes
  the class and its `strategy_name`.

Exit-policy numbers (SL −30 % / target +50 %) live in
`src/strategy/signal_exit.py`; this module never inlines a level literal.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import structlog

from src.models.portfolio import TradeAction as PaperTradeAction
from src.notifications.formatting import build_position_table
from src.notifications.markdown import escape_markdown
from src.notifications.telegram import build_notifier
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    LOT_SIZE,
    STRATEGY_SIGNAL_TRACK,
)
from src.paper.models import PaperTrade, SignalPaperEntry
from src.paper.store import PaperStore
from src.strategy._price_utils import resolve_price
from src.strategy.signal_exit import RULESET_VERSION, SL_PCT, TGT_PCT, derive_levels

if TYPE_CHECKING:
    from src.client.protocol import BrokerClient
    from src.notifications.telegram import TelegramNotifier
    from src.signals.models import DailySignal, MarketSnapshot

logger = structlog.get_logger(__name__)

_IST = ZoneInfo("Asia/Kolkata")
_UNDERLYING = "NIFTY"
_LEG_ROLE = "signal_long"
_NIFTY_KEY = "NSE_INDEX|Nifty 50"
_ACTION_TO_OPT_TYPE = {"BUY_CALL": "CE", "BUY_PUT": "PE"}

_E = escape_markdown


def _money(value: Decimal) -> str:
    """2dp, comma grouping, no ``₹`` — the EOD-PT-table money override (FORMATTING.md §5)."""
    return f"{value:,.2f}"


def _money_signed(value: Decimal) -> str:
    """As :func:`_money` with a leading ``+`` on non-negative values."""
    return f"{value:+,.2f}"


def _spot(value: Decimal) -> str:
    """Index level: integer, comma grouping (FORMATTING.md 'Index / spot level')."""
    return f"{int(value.to_integral_value(rounding=ROUND_HALF_UP)):,}"


def _instrument_label(strike: int, expiry_label: str, opt_type: str) -> str:
    """``NIFTY 23000 29 SEP 26 PE`` — CE/PE last, matching the EOD PT summary table."""
    return f"{_UNDERLYING} {strike} {expiry_label} {opt_type}"


def build_signal_entry_message(
    entry: SignalPaperEntry,
    instrument_label: str,
    cumulative: tuple[Decimal, int, int, int],
) -> str:
    """Render the Telegram entry confirmation (MarkdownV2, self-escaping).

    Seven-column position table (shared with the exit message and the EOD PT
    summary); ``Exit`` / ``P&L`` / ``Chg`` blank at entry; SL / target and the
    since-inception footer below the fence. This builder owns its escaping —
    the caller sends the result without re-wrapping it.

    Args:
        entry: The frozen entry just persisted.
        instrument_label: Human option label for the Instrument column.
        cumulative: ``PaperStore.cumulative_pnl()`` — ``(total, n, wins, losses)``
            over previously-closed signal trades.

    Returns:
        Fully-escaped message text.
    """
    total, n_trades, wins, losses = cumulative
    date_str = entry.signal_date.strftime("%d %b").lstrip("0")
    time_str = entry.entry_ts.strftime("%H:%M")

    table = build_position_table(
        rows=[
            (
                "Signal",
                instrument_label,
                str(LOT_SIZE),
                _money(entry.entry_premium),
                "—",
                "—",
                "—",
            )
        ],
        total_pnl=None,
        any_pnl_missing=False,
        title=None,
        empty_message="",
        value_header="Exit",
    )

    footer = f"Σ Inception  {_money_signed(total)}  ·  {n_trades} trades  ·  {wins}W / {losses}L"
    return "\n".join(
        [
            f"*{_E(f'✅ SIGNAL ENTRY · {date_str}')}*",
            "",
            "```",
            table,
            "```",
            "",
            _E(f"🛑 SL {_money(entry.sl_price)}   🎯 Target {_money(entry.tgt_price)}"),
            _E(f"🕘 {time_str}  ·  Nifty {_spot(entry.entry_underlying)}"),
            _E(footer),
        ]
    )


async def open_signal_paper_entry(
    signal: DailySignal,
    snapshot: MarketSnapshot,
    broker: BrokerClient,
    store: PaperStore,
    *,
    notifier: TelegramNotifier | None = None,
) -> SignalPaperEntry | None:
    """Open one signals-paper-track position from a firing ``DailySignal``.

    Idempotent by the SPT-2 one-open-position guard: a second call while a
    position is open is a logged no-op. NO_TRADE and an unresolvable option are
    also logged no-ops.

    Args:
        signal: The consensus ``DailySignal`` for the session.
        snapshot: The ``MarketSnapshot`` assembled for the same session (VIX,
            spot, resolved ``monthly_expiry``).
        broker: Authenticated broker client (``get_option_chain``).
        store: The shared ``PaperStore``.
        notifier: Optional notifier override; defaults to ``build_notifier()``.

    Returns:
        The frozen ``SignalPaperEntry`` on a successful open, else ``None``.
    """
    from src.signals.models import TradeAction as SignalTradeAction
    from src.signals.option_resolver import resolve_monthly_option

    if signal.trade_action == SignalTradeAction.NO_TRADE:
        logger.info("signal_track.no_trade", signal_date=signal.trade_date.isoformat())
        return None

    if signal.recommended_strike is None:
        # A directional DailySignal always carries a strike; guard is defensive.
        logger.warning("signal_track.no_strike", signal_date=signal.trade_date.isoformat())
        return None

    if await asyncio.to_thread(store.get_open_signal_entry) is not None:
        logger.info("signal_track.already_open", signal_date=signal.trade_date.isoformat())
        return None

    opt_type = _ACTION_TO_OPT_TYPE[signal.trade_action.value]
    instrument_key = await asyncio.to_thread(resolve_monthly_option, signal, DEFAULT_BOD_PATH)
    if instrument_key is None:
        logger.warning(
            "signal_track.resolve_failed",
            signal_date=signal.trade_date.isoformat(),
            strike=signal.recommended_strike,
            trade_action=signal.trade_action.value,
        )
        return None

    expiry = snapshot.monthly_expiry
    entry_dte = (expiry - signal.trade_date).days

    raw_chain = await broker.get_option_chain(_NIFTY_KEY, expiry.isoformat())
    from src.client.upstox_market import parse_upstox_option_chain

    chain = parse_upstox_option_chain(raw_chain)
    strike_entry = chain.strikes.get(Decimal(signal.recommended_strike))
    leg = None if strike_entry is None else getattr(strike_entry, opt_type.lower())
    if leg is None:
        logger.warning(
            "signal_track.leg_absent",
            instrument_key=instrument_key,
            strike=signal.recommended_strike,
            opt_type=opt_type,
        )
        return None

    try:
        mid = resolve_price(leg)
    except ValueError:
        logger.warning("signal_track.no_quote", instrument_key=instrument_key)
        return None

    from src.strategy.executor import PaperFillSimulator

    vix = float(snapshot.india_vix)
    fill = PaperFillSimulator().simulate_fill(
        instrument_key=instrument_key,
        action="BUY",
        quantity=LOT_SIZE,
        mid_price=mid,
        vix=vix,
    )
    premium = fill.fill_price
    sl_price, tgt_price = derive_levels(premium)
    confidence = max(
        1, min(5, int(signal.consensus_confidence.to_integral_value(rounding=ROUND_HALF_UP)))
    )

    trade = PaperTrade(
        strategy_name=STRATEGY_SIGNAL_TRACK,
        leg_role=_LEG_ROLE,
        instrument_key=instrument_key,
        trade_date=signal.trade_date,
        action=PaperTradeAction.BUY,
        quantity=LOT_SIZE,
        price=premium,
        notes="signal_track_v1 entry",
        is_paper=True,
    )
    trade_id = await asyncio.to_thread(store.record_signal_open_leg, trade)

    entry = SignalPaperEntry(
        trade_id=trade_id,
        signal_date=signal.trade_date,
        trade_action=signal.trade_action.value,
        instrument_key=instrument_key,
        expiry=expiry,
        entry_dte=entry_dte,
        entry_ts=datetime.now(tz=_IST),
        entry_premium=premium,
        entry_bid=leg.bid,
        entry_ask=leg.ask,
        entry_slippage=fill.slippage,
        entry_vix=snapshot.india_vix,
        entry_underlying=snapshot.nifty_spot,
        signal_confidence=confidence,
        sl_pct=SL_PCT,
        tgt_pct=TGT_PCT,
        sl_price=sl_price,
        tgt_price=tgt_price,
        ruleset_version=RULESET_VERSION,
    )
    await asyncio.to_thread(store.open_signal_entry, entry)

    logger.info(
        "signal_track.entry_opened",
        trade_id=trade_id,
        instrument_key=instrument_key,
        entry_premium=str(premium),
        sl_price=str(sl_price),
        tgt_price=str(tgt_price),
        entry_dte=entry_dte,
    )

    notifier = notifier or build_notifier()
    if notifier:
        cumulative = await asyncio.to_thread(store.cumulative_pnl)
        expiry_label = expiry.strftime("%d %b %y").upper()
        label = _instrument_label(int(signal.recommended_strike), expiry_label, opt_type)
        await notifier.send(build_signal_entry_message(entry, label, cumulative))

    return entry


class SignalTrackV1:
    """``PaperStrategy`` shell for ``paper_signal_track_v1`` (SPT-3).

    Entry is driven by :func:`open_signal_paper_entry` off the morning signal,
    not by a monitor tick. SPT-4 implements ``check_signals`` (per-tick
    ``paper_signal_marks`` + `signal_exit` routing); SPT-5 the exit fill. Until
    then the tick is a no-op so registration is safe.
    """

    strategy_name: str = STRATEGY_SIGNAL_TRACK
    auto_execute: bool = True

    def __init__(
        self,
        store: PaperStore | None = None,
        broker: BrokerClient | None = None,
        notifier: TelegramNotifier | None = None,
        **kwargs: Any,
    ) -> None:
        """Store the collaborators; all optional to match the sibling strategies."""
        self._store = store
        self._broker = broker
        self._notifier = notifier

    async def check_signals(self, market: Any, positions: Any) -> list[Any]:
        """No-op until SPT-4 wires the 30 s mark-path + exit routing."""
        return []

    def describe_context(self, event: Any, market: Any, positions: Any) -> str:
        """No council context — this strategy never routes through approval."""
        return ""

    async def apply_action(self, positions: Any, action: Any) -> Any:
        """No monitor-driven actions in SPT-3; return positions unchanged."""
        return positions
