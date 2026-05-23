"""Service layer for portfolio operations."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from src.models.portfolio import DailySnapshot, Strategy
from src.portfolio.store import PortfolioStore

logger = logging.getLogger(__name__)


class SnapshotService:
    """Service to handle persistence of daily snapshots and related operations."""

    def __init__(self, store: PortfolioStore) -> None:
        """Initialize the service.

        Args:
            store: PortfolioStore instance for persistence.
        """
        self.store = store

    def persist_snapshots(
        self,
        strategy_name: str,
        strategy: Strategy,
        snap_date: date,
        prices: dict[str, float],
        greeks_map: dict[str, dict],
        underlying_price: float | None = None,
    ) -> int:
        """Create DailySnapshot models and persist them in bulk.

        Enforces leg IDs for trade-only legs (auto-persisting if id is None).

        Args:
            strategy_name: Name of the strategy.
            strategy: Strategy model with overlaid trade positions.
            snap_date: Date of the snapshot.
            prices: dict mapping instrument_key -> price.
            greeks_map: dict mapping instrument_key -> greeks dict.
            underlying_price: Optional Nifty spot price.

        Returns:
            Number of snapshots recorded.
        """
        snapshots = []
        underlying_price_dec = (
            Decimal(str(underlying_price))
            if underlying_price is not None
            else None
        )

        for leg in strategy.legs:
            if leg.id is None:
                # Trade-only leg (e.g. LIQUIDBEES) — auto-persist to get a DB id
                leg_id = self.store.ensure_leg(strategy_name, leg)
                leg = leg.model_copy(update={"id": leg_id})
                logger.info(
                    "Auto-persisted trade-only leg '%s' (id=%d) for '%s'",
                    leg.display_name,
                    leg_id,
                    strategy_name,
                )

            ltp = Decimal(str(prices.get(leg.instrument_key, 0.0)))
            greeks = greeks_map.get(leg.instrument_key, {})

            snapshots.append(
                DailySnapshot(
                    leg_id=leg.id,
                    snapshot_date=snap_date,
                    ltp=ltp,
                    close=ltp,  # EOD snapshot — LTP is close
                    iv=greeks.get("iv"),
                    delta=greeks.get("delta"),
                    gamma=greeks.get("gamma"),
                    vega=greeks.get("vega"),
                    oi=greeks.get("oi"),
                    volume=greeks.get("volume"),
                    underlying_price=underlying_price_dec,
                )
            )

        if snapshots:
            count = self.store.record_snapshots_bulk(snapshots)
            logger.info(
                "Recorded %d snapshots for '%s' on %s",
                count,
                strategy_name,
                snap_date.isoformat(),
            )
            return count
        return 0
