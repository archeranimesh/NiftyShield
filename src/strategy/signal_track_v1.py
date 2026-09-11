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
from collections.abc import Callable
from datetime import datetime, timedelta
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
from src.paper.models import PaperTrade, SignalMark, SignalPaperEntry
from src.paper.store import PaperStore
from src.strategy._price_utils import find_option_leg, resolve_price
from src.strategy.signal_exit import RULESET_VERSION, SL_PCT, TGT_PCT, derive_levels, evaluate

if TYPE_CHECKING:
    from src.client.protocol import BrokerClient
    from src.instruments.lookup import InstrumentLookup
    from src.models.options import OptionChain, OptionLeg
    from src.notifications.telegram import TelegramNotifier
    from src.paper.models import PaperPosition
    from src.signals.models import DailySignal, MarketSnapshot

_STALE_AFTER = 30  # seconds — quote_ts older than this behind `now` marks stale=1.
_GAP_PCT = Decimal("0.20")  # |mark - prev_mark| / E threshold for gap_event.

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


def _compute_mark(
    entry: SignalPaperEntry,
    leg: OptionLeg,
    now: datetime,
    quote_ts: datetime | None,
    prev_mark: Decimal | None,
    prev_mfe_pct: Decimal,
    prev_mae_pct: Decimal,
) -> SignalMark:
    """Build one ``SignalMark`` telemetry row from the current leg quote.

    Pure — no I/O. ``mark`` is ``(bid + ask) / 2`` (falls back to ``ltp`` via
    :func:`resolve_price` when bid/ask are unusable). ``mfe_pct`` / ``mae_pct``
    are the running best/worst ``unrealised_pct`` seen so far, seeded at 0 on
    the first tick so they never cross the entry line before an excursion
    actually happens.

    Args:
        entry: The frozen entry (carries ``entry_premium`` == ``E``).
        leg: ``OptionLeg`` with the current ``bid``/``ask``/``ltp``.
        now: Tick evaluation time (IST).
        quote_ts: Broker quote timestamp, or ``None`` if not supplied.
        prev_mark: The previous tick's mark, or ``None`` on the first tick.
        prev_mfe_pct: Running max favourable excursion so far.
        prev_mae_pct: Running max adverse excursion so far.

    Returns:
        The new ``SignalMark`` (not yet persisted).
    """
    mark = resolve_price(leg)
    unrealised_pct = (mark / entry.entry_premium) - 1
    mfe_pct = max(prev_mfe_pct, unrealised_pct)
    mae_pct = min(prev_mae_pct, unrealised_pct)
    stale = quote_ts is not None and (now - quote_ts) > timedelta(seconds=_STALE_AFTER)
    gap_event = prev_mark is not None and abs(mark - prev_mark) / entry.entry_premium > _GAP_PCT
    return SignalMark(
        trade_id=entry.trade_id,
        ts=now,
        quote_ts=quote_ts,
        stale=stale,
        ltp=leg.ltp,
        bid=leg.bid,
        ask=leg.ask,
        mark=mark,
        unrealised_pct=unrealised_pct,
        mfe_pct=mfe_pct,
        mae_pct=mae_pct,
        gap_event=gap_event,
    )


class SignalTrackV1:
    """``PaperStrategy`` shell for ``paper_signal_track_v1`` (SPT-3/SPT-4).

    Entry is driven by :func:`open_signal_paper_entry` off the morning signal,
    not by a monitor tick. ``check_signals`` (SPT-4) writes the per-tick
    ``paper_signal_marks`` row and hands ``(entry, mark, now)`` to
    ``signal_exit.evaluate`` — a non-HOLD decision is logged only (no fill /
    close / Telegram; that is SPT-5's caller-side wiring). Runs at a 30 s
    cadence via ``due_interval_s`` on the shared ``StrategyMonitor`` while
    credit-spread strategies stay at the monitor's default 90 s.
    """

    strategy_name: str = STRATEGY_SIGNAL_TRACK
    auto_execute: bool = True
    due_interval_s: int = 30

    def __init__(
        self,
        store: PaperStore | None = None,
        broker: BrokerClient | None = None,
        notifier: TelegramNotifier | None = None,
        lookup: InstrumentLookup | None = None,
        clock: Callable[[], datetime] | None = None,
        **kwargs: Any,
    ) -> None:
        """Store the collaborators; all optional to match the sibling strategies.

        Args:
            clock: Zero-arg callable returning the current IST time; defaults
                to ``datetime.now(tz=_IST)``. Injectable so tests can pin the
                tick evaluation time without depending on wall-clock time
                (e.g. for the 15:00 IST square-off check in ``signal_exit``).
        """
        self._store = store
        self._broker = broker
        self._notifier = notifier
        self._lookup = lookup
        self._clock = clock or (lambda: datetime.now(tz=_IST))
        # SPT-4 dedup: trade_ids for which a non-HOLD decision has already been
        # logged this process lifetime, so a stray re-tick before SPT-5 wires
        # the actual close never re-fires the same exit decision.
        self._exit_fired_trade_ids: set[int] = set()

    async def check_signals(self, market: OptionChain, positions: list[PaperPosition]) -> list[Any]:
        """Per-tick mark-path telemetry + exit-decision routing (SPT-4).

        Holiday / outside-market-hours are already gated by
        ``StrategyMonitor._tick`` before this is ever called. No-open-position
        and an unresolvable leg are logged no-ops. Emits no ``SignalEvent``s —
        exit dispatch is SPT-5's caller-side wiring; this only logs the
        decision and records the dedup key.

        Args:
            market: Current NIFTY option chain for this position's expiry.
            positions: This strategy's open positions (unused directly — the
                open entry is the source of truth via ``get_open_signal_entry``).

        Returns:
            Always ``[]`` — SPT-4 does not emit ``SignalEvent``s.
        """
        if self._store is None:
            return []

        entry = await asyncio.to_thread(self._store.get_open_signal_entry)
        if entry is None:
            return []
        if entry.trade_id in self._exit_fired_trade_ids:
            return []

        leg = find_option_leg(entry.instrument_key, market, self._lookup)
        if leg is None:
            logger.warning(
                "signal_track.mark_leg_absent",
                trade_id=entry.trade_id,
                instrument_key=entry.instrument_key,
            )
            return []

        prior_marks = await asyncio.to_thread(self._store.get_marks, entry.trade_id)
        prev = prior_marks[-1] if prior_marks else None
        prev_mark = prev.mark if prev is not None else None
        prev_mfe_pct = prev.mfe_pct if prev is not None else Decimal("0")
        prev_mae_pct = prev.mae_pct if prev is not None else Decimal("0")

        now = self._clock()
        try:
            mark_row = _compute_mark(
                entry,
                leg,
                now=now,
                # TODO(SPT-?): set from the broker's quote timestamp once
                # parse_upstox_option_chain exposes one on OptionLeg; until
                # then `stale` is always False in production (the logic is
                # unit-tested directly against a supplied quote_ts).
                quote_ts=None,
                prev_mark=prev_mark,
                prev_mfe_pct=prev_mfe_pct,
                prev_mae_pct=prev_mae_pct,
            )
        except ValueError:
            logger.warning(
                "signal_track.mark_no_valid_price",
                trade_id=entry.trade_id,
                instrument_key=entry.instrument_key,
            )
            return []

        await asyncio.to_thread(self._store.record_mark, mark_row)

        decision = evaluate(entry, mark_row.mark, now)
        if decision.reason is not None:
            self._exit_fired_trade_ids.add(entry.trade_id)
            logger.info(
                "signal_track.exit_decision",
                trade_id=entry.trade_id,
                reason=decision.reason.value,
                mark=str(mark_row.mark),
            )

        return []

    def describe_context(self, event: Any, market: Any, positions: Any) -> str:
        """No council context — this strategy never routes through approval."""
        return ""

    async def apply_action(self, positions: Any, action: Any) -> Any:
        """No monitor-driven actions in SPT-3; return positions unchanged."""
        return positions
