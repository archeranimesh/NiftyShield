"""Portfolio tracker: fetches live data, computes P&L, records snapshots.

Depends on MarketDataProvider protocol for market data. Works identically
with UpstoxLiveClient (production) or MockBrokerClient (testing).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.client.protocol import MarketDataProvider
from src.models.portfolio import (
    AssetType,
    DailySnapshot,
    Direction,
    Leg,
    ProductType,
    Strategy,
)
from src.portfolio.store import PortfolioStore

logger = logging.getLogger(__name__)


# ── P&L summary dataclasses ─────────────────────────────────────

@dataclass(frozen=True)
class LegPnL:
    """P&L summary for a single leg."""

    leg: Leg
    current_price: Decimal
    pnl: Decimal
    pnl_percent: Decimal


@dataclass(frozen=True)
class StrategyPnL:
    """P&L summary for a full strategy."""

    strategy_name: str
    legs: list[LegPnL]

    @property
    def total_pnl(self) -> Decimal:
        return sum((lp.pnl for lp in self.legs), Decimal("0"))

    @property
    def total_entry_value(self) -> Decimal:
        total = Decimal("0")
        for lp in self.legs:
            if lp.leg.direction == Direction.BUY:
                total += lp.leg.entry_value
            else:
                total -= lp.leg.entry_value
        return total

    @property
    def total_pnl_percent(self) -> Decimal:
        entry = abs(self.total_entry_value)
        return (self.total_pnl / entry * 100) if entry > 0 else Decimal("0")


def apply_trade_positions(
    strategy: Strategy,
    positions: dict[str, tuple[int, Decimal, str]],
) -> Strategy:
    """Return a new Strategy with leg quantities and entry prices from the trades ledger.

    Matching between strategy legs and trade positions is done on instrument_key —
    the unambiguous Upstox key (e.g. "NSE_EQ|INF754K01LE1"). display_name is NOT
    used for matching because it contains human-readable suffixes in the strategy
    definition (e.g. "EBBETF0431 (Bharat Bond ETF Apr 2031)") that differ from the
    short leg_role in the trades table ("EBBETF0431").

    For every leg in the strategy whose instrument_key has a matching entry in
    *positions*, the returned copy has quantity and entry_price replaced with the
    trade-derived net_qty and weighted-average buy price.

    Legs with zero net quantity in *positions* are dropped — they are fully closed.

    Leg roles in *positions* whose instrument_key has no matching leg in the strategy
    (e.g. LIQUIDBEES, which is in the trades table but not in ilts.py) are appended
    as new EQUITY/CNC legs so their mark-to-market value flows into the P&L summary.

    Legs in the strategy whose instrument_key has no entry in *positions* (e.g.
    options legs never individually traded via record_trade) are passed through
    unchanged.

    This function is pure — no I/O, no DB access.

    Args:
        strategy: Original Strategy object from ALL_STRATEGIES.
        positions: Output of PortfolioStore.get_all_positions_for_strategy() —
            dict[leg_role → (net_qty, avg_buy_price, instrument_key)].

    Returns:
        New Strategy instance with trade-derived quantities where available.
    """
    # Build instrument_key → (leg_role, net_qty, avg_price) for O(1) lookup
    by_instrument_key: dict[str, tuple[str, int, Decimal]] = {
        instrument_key: (leg_role, net_qty, avg_price)
        for leg_role, (net_qty, avg_price, instrument_key) in positions.items()
    }

    updated_legs: list[Leg] = []
    matched_keys: set[str] = set()

    for leg in strategy.legs:
        if leg.instrument_key in by_instrument_key:
            matched_keys.add(leg.instrument_key)
            _, net_qty, avg_price = by_instrument_key[leg.instrument_key]
            if net_qty == 0:
                continue  # fully closed — drop from active P&L
            updated_legs.append(leg.model_copy(update={
                "quantity": net_qty,
                "entry_price": avg_price,
            }))
        else:
            updated_legs.append(leg)

    # Append legs that exist in trades but not in the strategy definition
    entry_date = strategy.legs[0].entry_date if strategy.legs else date.today()
    for leg_role, (net_qty, avg_price, instrument_key) in positions.items():
        if instrument_key in matched_keys:
            continue
        if net_qty == 0:
            continue  # fully closed — skip
        updated_legs.append(Leg(
            instrument_key=instrument_key,
            display_name=leg_role,
            asset_type=AssetType.EQUITY,
            direction=Direction.BUY,
            quantity=net_qty,
            lot_size=1,
            entry_price=avg_price,
            entry_date=entry_date,
            expiry=None,
            strike=None,
            product_type=ProductType.CNC,
        ))

    return Strategy(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        legs=updated_legs,
        created_at=strategy.created_at,
    )


class PortfolioTracker:
    """Tracks P&L and records daily snapshots for all strategies."""

    def __init__(self, store: PortfolioStore, market: MarketDataProvider) -> None:
        self.store = store
        self.market = market

    def _get_overlaid_strategy(self, strategy_name: str) -> Strategy | None:
        """Load a strategy from the store and overlay trade-derived positions.

        Applies apply_trade_positions so that quantities and entry prices
        reflect the trades ledger rather than the static seed values.

        Args:
            strategy_name: Strategy to load and overlay.

        Returns:
            Strategy with trade overlay applied, or None if not found.
        """
        strategy = self.store.get_strategy(strategy_name)
        if not strategy:
            return None
        positions = self.store.get_all_positions_for_strategy(strategy_name)
        if positions:
            strategy = apply_trade_positions(strategy, positions)
        return strategy

    def _get_all_overlaid_strategies(self) -> list[Strategy]:
        """Load all strategies from the store with trade overlays applied."""
        strategies = self.store.get_all_strategies()
        result = []
        for s in strategies:
            positions = self.store.get_all_positions_for_strategy(s.name)
            if positions:
                s = apply_trade_positions(s, positions)
            result.append(s)
        return result

    async def compute_pnl(self, strategy_name: str) -> StrategyPnL | None:
        """Fetch current prices and compute live P&L for a strategy.

        Returns None if strategy not found in the store.
        """
        strategy = self._get_overlaid_strategy(strategy_name)
        if not strategy:
            logger.warning("Strategy '%s' not found in store", strategy_name)
            return None

        instrument_keys = [leg.instrument_key for leg in strategy.legs]
        prices = await self.market.get_ltp(instrument_keys)

        leg_pnls = []
        for leg in strategy.legs:
            raw_ltp = prices.get(leg.instrument_key)
            if raw_ltp is None:
                logger.warning(
                    "No LTP for %s (%s) — using entry price as fallback",
                    leg.display_name,
                    leg.instrument_key,
                )
                ltp: Decimal = leg.entry_price
            else:
                ltp = Decimal(str(raw_ltp))

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
        strategy = self._get_overlaid_strategy(strategy_name)
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
                # Trade-only leg (e.g. LIQUIDBEES) — auto-persist to get a DB id
                leg_id = self.store.ensure_leg(strategy_name, leg)
                leg = leg.model_copy(update={"id": leg_id})
                logger.info(
                    "Auto-persisted trade-only leg '%s' (id=%d) for '%s'",
                    leg.display_name, leg_id, strategy_name,
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
        strategies = self._get_all_overlaid_strategies()
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
        # TODO: TD-7 — remove this early return once greeks extraction is implemented.
        return {}


    @staticmethod
    def _extract_greeks_from_chain(chain: dict, leg: Leg) -> dict | None:
        """Extract greeks for a specific strike/type from an option chain response.

        The chain format depends on the Upstox API response structure.
        This is a placeholder — adapt to the actual OptionChain model
        once the Pydantic models for the option chain API are finalized.
        """
        # TODO: TD-7 — implement once OptionChain Pydantic model is defined.
        # Expected fields: iv, delta, theta, gamma, vega, oi, volume
        return None
