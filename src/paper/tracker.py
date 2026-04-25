"""Paper trading tracker — P&L computation and daily snapshot recording.

Mirrors PortfolioTracker's shape but operates exclusively on paper_trades
and paper_nav_snapshots tables.  No broker order calls are made.

All monetary arithmetic uses Decimal.  LTP values from the market client
are floats — converted at the boundary via Decimal(str(float_val)).
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from src.client.protocol import MarketDataProvider
from src.models.portfolio import TradeAction
from src.paper.models import PaperNavSnapshot, PaperPosition
from src.paper.store import PaperStore

logger = logging.getLogger(__name__)


def _compute_leg_unrealized_pnl(
    position: PaperPosition,
    ltp: Decimal,
) -> Decimal:
    """Compute unrealized P&L for one open paper leg at a given LTP.

    For a SHORT (net_qty < 0) position: profit when LTP falls below avg_sell_price.
        P&L = (avg_sell_price - ltp) * abs(net_qty)
    For a LONG (net_qty > 0) position: profit when LTP rises above avg_cost.
        P&L = (ltp - avg_cost) * net_qty

    Args:
        position: Current open position for this leg.
        ltp: Current last-traded price as Decimal.

    Returns:
        Unrealized P&L in rupees. Positive = profit, negative = loss.
    """
    if position.net_qty == 0:
        return Decimal("0")
    if position.net_qty < 0:
        # Short position opened by SELL — use avg_sell_price as cost basis
        return (position.avg_sell_price - ltp) * abs(position.net_qty)
    return (ltp - position.avg_cost) * position.net_qty


def _compute_realized_pnl(store: PaperStore, strategy_name: str) -> Decimal:
    """Compute cumulative realized P&L for a paper strategy from closed trades.

    Realized P&L = sum of (sell_price - buy_avg_cost) * qty for each completed
    round-trip.  Approximated here as: total SELL proceeds - total BUY cost.

    This is a simple implementation that works correctly for strategies that
    open a position via SELL (options writer) and close via BUY, or open via
    BUY (long) and close via SELL.  For partial closes the approximation uses
    the full weighted average cost rather than FIFO — acceptable for
    paper-trading analysis purposes.

    Args:
        store: PaperStore instance.
        strategy_name: Paper strategy to compute realized P&L for.

    Returns:
        Cumulative realized P&L in rupees.
    """
    trades = store.get_trades(strategy_name)
    if not trades:
        return Decimal("0")

    # Bucket by leg_role
    total_realized = Decimal("0")

    for leg_role in sorted({t.leg_role for t in trades}):
        leg_trades = [t for t in trades if t.leg_role == leg_role]
        total_buy_qty = sum(
            t.quantity for t in leg_trades if t.action == TradeAction.BUY
        )
        total_sell_qty = sum(
            t.quantity for t in leg_trades if t.action == TradeAction.SELL
        )
        closed_qty = min(total_buy_qty, total_sell_qty)

        if closed_qty == 0:
            continue

        buy_total = sum(
            t.price * t.quantity
            for t in leg_trades
            if t.action == TradeAction.BUY
        )
        sell_total = sum(
            t.price * t.quantity
            for t in leg_trades
            if t.action == TradeAction.SELL
        )

        buy_avg = buy_total / total_buy_qty if total_buy_qty else Decimal("0")
        sell_avg = sell_total / total_sell_qty if total_sell_qty else Decimal("0")

        # Realized per closed qty: (sell_avg - buy_avg) * closed_qty
        total_realized += (sell_avg - buy_avg) * closed_qty

    return total_realized


class PaperTracker:
    """Computes P&L and records daily NAV snapshots for paper strategies.

    Mirrors PortfolioTracker's constructor and public-method shapes.
    The market client is used only for LTP lookups — no order placement.

    Args:
        store: PaperStore for persistence.
        market: MarketDataProvider for live LTP (pass MockBrokerClient in tests).
    """

    def __init__(self, store: PaperStore, market: MarketDataProvider) -> None:
        self.store = store
        self.market = market

    async def compute_pnl(
        self, strategy_name: str
    ) -> tuple[Decimal, Decimal, Decimal] | None:
        """Fetch current LTPs and compute live P&L for a paper strategy.

        Queries open positions, fetches LTPs, computes unrealized P&L per leg,
        and adds cumulative realized P&L.

        Args:
            strategy_name: Paper strategy name (must start with ``paper_``).

        Returns:
            Tuple (unrealized_pnl, realized_pnl, total_pnl) or None if the
            strategy has no trades at all.
        """
        # Return None only when there are zero trades at all — not just zero open positions.
        all_trades = self.store.get_trades(strategy_name)
        if not all_trades:
            logger.warning("No trades found for paper strategy '%s'", strategy_name)
            return None

        positions = self._get_open_positions(strategy_name)
        instrument_keys = [p.instrument_key for p in positions if p.instrument_key]
        prices: dict[str, float] = {}
        if instrument_keys:
            prices = await self.market.get_ltp(instrument_keys)

        unrealized = Decimal("0")
        for pos in positions:
            raw_ltp = prices.get(pos.instrument_key, 0.0)
            ltp = Decimal(str(raw_ltp))
            unrealized += _compute_leg_unrealized_pnl(pos, ltp)

        realized = _compute_realized_pnl(self.store, strategy_name)
        total = unrealized + realized

        return unrealized, realized, total

    async def record_daily_snapshot(
        self,
        strategy_name: str,
        snapshot_date: date | None = None,
        underlying_price: float | None = None,
    ) -> PaperNavSnapshot | None:
        """Fetch LTPs, compute P&L, and persist a daily NAV snapshot.

        Idempotent: re-running for the same (strategy, date) updates the
        existing row via the ON CONFLICT DO UPDATE upsert in PaperStore.

        Args:
            strategy_name: Paper strategy name.
            snapshot_date: Date to record (defaults to today).
            underlying_price: Nifty spot price for context (optional).

        Returns:
            The persisted PaperNavSnapshot, or None if no trades exist.
        """
        snap_date = snapshot_date or date.today()
        pnl = await self.compute_pnl(strategy_name)

        if pnl is None:
            logger.warning(
                "Skipping NAV snapshot for '%s' — no trades found", strategy_name
            )
            return None

        unrealized, realized, total = pnl
        underlying = (
            Decimal(str(underlying_price)) if underlying_price is not None else None
        )

        snapshot = PaperNavSnapshot(
            strategy_name=strategy_name,
            snapshot_date=snap_date,
            unrealized_pnl=unrealized,
            realized_pnl=realized,
            total_pnl=total,
            underlying_price=underlying,
        )
        self.store.record_nav_snapshot(snapshot)
        logger.info(
            "Recorded paper NAV snapshot for '%s' on %s: total_pnl=%.2f",
            strategy_name,
            snap_date.isoformat(),
            float(total),
        )
        return snapshot

    async def record_all_strategies(
        self,
        snapshot_date: date | None = None,
        underlying_price: float | None = None,
    ) -> dict[str, PaperNavSnapshot | None]:
        """Record daily snapshots for all known paper strategies.

        Args:
            snapshot_date: Date to record (defaults to today).
            underlying_price: Nifty spot price for context (optional).

        Returns:
            Mapping of strategy_name -> PaperNavSnapshot (None if no trades).
        """
        strategy_names = self.store.get_strategy_names()
        results: dict[str, PaperNavSnapshot | None] = {}
        for name in strategy_names:
            results[name] = await self.record_daily_snapshot(
                name, snapshot_date, underlying_price
            )
        return results

    # ── Private helpers ─────────────────────────────��─────────────────────────

    def _get_open_positions(self, strategy_name: str) -> list[PaperPosition]:
        """Return all legs with non-zero net quantity for a strategy.

        Args:
            strategy_name: Paper strategy to inspect.

        Returns:
            List of PaperPosition where net_qty != 0.
        """
        trades = self.store.get_trades(strategy_name)
        leg_roles: set[str] = {t.leg_role for t in trades}
        positions = [
            self.store.get_position(strategy_name, role) for role in leg_roles
        ]
        return [p for p in positions if p.net_qty != 0]
