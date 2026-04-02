"""Portfolio tracker: fetches live data, computes P&L, records snapshots.

Depends on MarketDataProvider protocol for market data. Works identically
with UpstoxLiveClient (production) or MockBrokerClient (testing).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from src.portfolio.models import (
    AssetType,
    DailySnapshot,
    Direction,
    Leg,
    Strategy,
)
from src.portfolio.store import PortfolioStore

logger = logging.getLogger(__name__)


# ── Minimal protocol surface needed by tracker ───────────────────

@runtime_checkable
class MarketDataProvider(Protocol):
    """Subset of BrokerClient that the tracker actually needs."""

    async def get_ltp(self, instruments: list[str]) -> dict[str, float]: ...

    async def get_option_chain(
        self, instrument: str, expiry: str
    ) -> dict: ...


# ── P&L summary dataclasses ─────────────────────────────────────

@dataclass(frozen=True)
class LegPnL:
    """P&L summary for a single leg."""

    leg: Leg
    current_price: float
    pnl: float
    pnl_percent: float


@dataclass(frozen=True)
class StrategyPnL:
    """P&L summary for a full strategy."""

    strategy_name: str
    legs: list[LegPnL]

    @property
    def total_pnl(self) -> float:
        return sum(lp.pnl for lp in self.legs)

    @property
    def total_entry_value(self) -> float:
        total = 0.0
        for lp in self.legs:
            if lp.leg.direction == Direction.BUY:
                total += lp.leg.entry_value
            else:
                total -= lp.leg.entry_value
        return total

    @property
    def total_pnl_percent(self) -> float:
        entry = abs(self.total_entry_value)
        return (self.total_pnl / entry * 100) if entry > 0 else 0.0


class PortfolioTracker:
    """Tracks P&L and records daily snapshots for all strategies."""

    def __init__(self, store: PortfolioStore, market: MarketDataProvider) -> None:
        self.store = store
        self.market = market

    async def compute_pnl(self, strategy_name: str) -> StrategyPnL | None:
        """Fetch current prices and compute live P&L for a strategy.

        Returns None if strategy not found in the store.
        """
        strategy = self.store.get_strategy(strategy_name)
        if not strategy:
            logger.warning("Strategy '%s' not found in store", strategy_name)
            return None

        instrument_keys = [leg.instrument_key for leg in strategy.legs]
        prices = await self.market.get_ltp(instrument_keys)

        leg_pnls = []
        for leg in strategy.legs:
            ltp = prices.get(leg.instrument_key, 0.0)
            if ltp == 0.0:
                logger.warning(
                    "No LTP for %s (%s) — using entry price as fallback",
                    leg.display_name,
                    leg.instrument_key,
                )
                ltp = leg.entry_price

            leg_pnls.append(
                LegPnL(
                    leg=leg,
                    current_price=ltp,
                    pnl=leg.pnl(ltp),
                    pnl_percent=leg.pnl_percent(ltp),
                )
            )

        return StrategyPnL(strategy_name=strategy_name, legs=leg_pnls)

    async def record_daily_snapshot(
        self,
        strategy_name: str,
        snapshot_date: date | None = None,
        underlying_price: float | None = None,
    ) -> int:
        """Fetch current prices and record a daily snapshot for every leg.

        Args:
            strategy_name: Name of the strategy in the store.
            snapshot_date: Date to record (defaults to today).
            underlying_price: Nifty spot price (optional, stored for context).

        Returns:
            Number of snapshots recorded.
        """
        snap_date = snapshot_date or date.today()
        strategy = self.store.get_strategy(strategy_name)
        if not strategy:
            logger.warning("Strategy '%s' not found — skipping snapshot", strategy_name)
            return 0

        instrument_keys = [leg.instrument_key for leg in strategy.legs]
        prices = await self.market.get_ltp(instrument_keys)

        # Try to get greeks for option legs
        greeks_map = await self._fetch_greeks(strategy.legs)

        snapshots = []
        for leg in strategy.legs:
            if leg.id is None:
                continue

            ltp = prices.get(leg.instrument_key, 0.0)
            greeks = greeks_map.get(leg.instrument_key, {})

            snapshots.append(
                DailySnapshot(
                    leg_id=leg.id,
                    snapshot_date=snap_date,
                    ltp=ltp,
                    close=ltp,  # EOD snapshot — LTP is close
                    iv=greeks.get("iv"),
                    delta=greeks.get("delta"),
                    theta=greeks.get("theta"),
                    gamma=greeks.get("gamma"),
                    vega=greeks.get("vega"),
                    oi=greeks.get("oi"),
                    volume=greeks.get("volume"),
                    underlying_price=underlying_price,
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

    async def record_all_strategies(
        self,
        snapshot_date: date | None = None,
        underlying_price: float | None = None,
    ) -> dict[str, int]:
        """Record daily snapshots for every strategy in the store."""
        strategies = self.store.get_all_strategies()
        results = {}
        for strategy in strategies:
            count = await self.record_daily_snapshot(
                strategy.name, snapshot_date, underlying_price
            )
            results[strategy.name] = count
        return results

    async def _fetch_greeks(self, legs: list[Leg]) -> dict[str, dict]:
        """Best-effort fetch of Greeks from option chain for option legs.

        Returns a dict keyed by instrument_key with available greeks.
        Non-option legs and failures return empty dicts silently.

        NOTE: Skipped until _extract_greeks_from_chain is implemented.
        Remove the early return below once the OptionChain Pydantic
        model is defined and the extraction logic is in place.
        """
        # TODO: Remove this early return once greeks extraction is implemented.
        return {}


    @staticmethod
    def _extract_greeks_from_chain(chain: dict, leg: Leg) -> dict | None:
        """Extract greeks for a specific strike/type from an option chain response.

        The chain format depends on the Upstox API response structure.
        This is a placeholder — adapt to the actual OptionChain model
        once the Pydantic models for the option chain API are finalized.
        """
        # TODO: Implement once OptionChain Pydantic model is defined.
        # Expected fields: iv, delta, theta, gamma, vega, oi, volume
        return None
