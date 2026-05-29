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
from src.client.upstox_market import parse_upstox_option_chain
from src.models.options import OptionChain
from src.models.portfolio import (
    AssetType,
    Direction,
    Leg,
    Position,
    ProductType,
    Strategy,
)
from src.portfolio.service import SnapshotService
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
    positions: dict[str, Position],
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
            dict[leg_role → Position].

    Returns:
        New Strategy instance with trade-derived quantities where available.
    """
    # Build instrument_key → Position for O(1) lookup
    by_instrument_key: dict[str, Position] = {
        pos.instrument_key: pos
        for pos in positions.values()
    }

    updated_legs: list[Leg] = []
    matched_keys: set[str] = set()

    for leg in strategy.legs:
        if leg.instrument_key in by_instrument_key:
            matched_keys.add(leg.instrument_key)
            pos = by_instrument_key[leg.instrument_key]
            if pos.quantity == 0:
                continue  # fully closed — drop from active P&L
            updated_legs.append(leg.model_copy(update={
                "quantity": pos.quantity,
                "entry_price": pos.average_price,
            }))
        else:
            updated_legs.append(leg)

    # Append legs that exist in trades but not in the strategy definition
    entry_date = strategy.legs[0].entry_date if strategy.legs else date.today()
    for leg_role, pos in positions.items():
        if pos.instrument_key in matched_keys:
            continue
        if pos.quantity == 0:
            continue  # fully closed — skip
        updated_legs.append(Leg(
            instrument_key=pos.instrument_key,
            display_name=leg_role,
            asset_type=AssetType.EQUITY,
            direction=Direction.BUY,
            quantity=pos.quantity,
            lot_size=1,
            entry_price=pos.average_price,
            entry_date=entry_date,
            expiry=None,
            strike=None,
            product_type=ProductType.CNC,
        ))

    return strategy.__class__(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        legs=updated_legs,
        created_at=strategy.created_at,
    )


class PortfolioTracker:
    """Tracks P&L and records daily snapshots for all strategies."""

    def __init__(
        self,
        store: PortfolioStore,
        market: MarketDataProvider,
        snapshot_service: SnapshotService | None = None,
    ) -> None:
        self.store = store
        self.market = market
        self.snapshot_service = snapshot_service if snapshot_service is not None else SnapshotService(store)

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

    def _build_strategy_pnl(
        self, strategy: Strategy, prices: dict[str, Decimal]
    ) -> StrategyPnL:
        """Compute StrategyPnL from an already-fetched prices dict."""
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
                ltp = (
                    raw_ltp if isinstance(raw_ltp, Decimal)
                    else Decimal(str(raw_ltp))
                )

            leg_pnls.append(
                LegPnL(
                    leg=leg,
                    current_price=ltp,
                    pnl=leg.pnl(ltp),
                    pnl_percent=leg.pnl_percent(ltp),
                )
            )

        return StrategyPnL(strategy_name=strategy.name, legs=leg_pnls)

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
        return self._build_strategy_pnl(strategy, prices)

    async def record_daily_snapshot(
        self,
        strategy_name: str,
        snapshot_date: date | None = None,
        underlying_price: Decimal | None = None,
        prices: dict[str, Decimal] | None = None,
    ) -> tuple[int, StrategyPnL | None]:
        """Fetch current prices and record a daily snapshot for every leg.

        Args:
            strategy_name: Name of the strategy in the store.
            snapshot_date: Date to record (defaults to today).
            underlying_price: Nifty spot price (optional, stored for context).
            prices: Optional pre-fetched prices to skip the LTP fetch.

        Returns:
            Tuple of (number of snapshots recorded, StrategyPnL based on prices).
        """
        snap_date = snapshot_date or date.today()
        strategy = self._get_overlaid_strategy(strategy_name)
        if not strategy:
            logger.warning("Strategy '%s' not found — skipping snapshot", strategy_name)
            return 0, None

        instrument_keys = [leg.instrument_key for leg in strategy.legs]
        if prices is None:
            prices = await self.market.get_ltp(instrument_keys)

        # Try to get greeks for option legs
        greeks_map = await self._fetch_greeks(strategy.legs)

        count = self.snapshot_service.persist_snapshots(
            strategy_name=strategy_name,
            strategy=strategy,
            snap_date=snap_date,
            prices=prices,
            greeks_map=greeks_map,
            underlying_price=underlying_price,
        )

        pnl = self._build_strategy_pnl(strategy, prices)
        return count, pnl

    async def record_all_strategies(
        self,
        snapshot_date: date | None = None,
        underlying_price: Decimal | None = None,
        prices: dict[str, Decimal] | None = None,
    ) -> tuple[dict[str, int], dict[str, StrategyPnL | None]]:
        """Record daily snapshots for every strategy in the store."""
        strategies = self._get_all_overlaid_strategies()
        counts = {}
        pnls = {}
        for strategy in strategies:
            count, pnl = await self.record_daily_snapshot(
                strategy.name, snapshot_date, underlying_price, prices=prices
            )
            counts[strategy.name] = count
            pnls[strategy.name] = pnl
        return counts, pnls

    async def _fetch_greeks(self, legs: list[Leg]) -> dict[str, dict]:
        """Best-effort fetch of Greeks from Upstox option chain for option legs.

        Filters to CE/PE legs with a non-None expiry, groups by expiry,
        makes one chain call per expiry, then extracts Greeks per leg.
        Failures are logged at WARNING — never raise, never block the
        snapshot from recording.

        Args:
            legs: All legs for the strategy being snapshotted.

        Returns:
            Dict mapping instrument_key -> {"delta", "gamma", "theta",
            "vega", "iv", "oi", "volume"} for every option leg whose
            Greeks could be resolved. Missing keys mean the leg was
            equity/bond/futures or the chain call failed.
        """
        option_legs = [
            leg for leg in legs
            if leg.asset_type in {AssetType.CE, AssetType.PE}
            and leg.expiry is not None
        ]
        if not option_legs:
            return {}

        # Group by expiry — one chain call per expiry date.
        by_expiry: dict[date, list[Leg]] = {}
        for leg in option_legs:
            by_expiry.setdefault(leg.expiry, []).append(leg)  # type: ignore[arg-type]

        result: dict[str, dict] = {}
        for expiry, exp_legs in by_expiry.items():
            try:
                raw = await self.market.get_option_chain(
                    "NSE_INDEX|Nifty 50", expiry.isoformat()
                )
                chain = parse_upstox_option_chain(raw if isinstance(raw, list) else [])
            except Exception as exc:
                # Intentional: Broad catch to prevent a single failed expiry fetch from blocking
                # greeks computation for all other legs in the batch.
                logger.warning("Greeks fetch failed for expiry %s: %s", expiry, exc)
                continue
            for leg in exp_legs:
                greeks = _extract_greeks_from_chain(chain, leg)
                if greeks:
                    result[leg.instrument_key] = greeks
        return result


# ── Greeks extraction (module-level: _extract_greeks_from_chain) ──


def _extract_greeks_from_chain(
    chain: OptionChain, leg: Leg
) -> dict[str, Decimal]:
    """Extract Greeks for a single option leg from a parsed OptionChain.

    Looks up the leg's strike in ``chain.strikes`` by ``Decimal(str(leg.strike))``
    and picks the CE or PE side via ``leg.asset_type``.  Returns an empty
    dict for any mismatch so callers can handle missing data uniformly.

    Args:
        chain: Fully parsed OptionChain for the relevant expiry.
        leg: The strategy leg whose Greeks are needed.

    Returns:
        Dict with keys: delta, gamma, theta, vega, iv, oi, volume — all
        Decimal except oi and volume which are int.  Empty dict when the
        leg is not an option, has no strike, or the strike is not in the
        chain.
    """
    if leg.strike is None or leg.asset_type not in {AssetType.CE, AssetType.PE}:
        return {}

    key = Decimal(str(leg.strike))
    strike_entry = chain.strikes.get(key)
    if strike_entry is None:
        return {}

    option_leg = strike_entry.ce if leg.asset_type == AssetType.CE else strike_entry.pe
    if option_leg is None:
        return {}

    return {
        "delta": option_leg.delta,
        "gamma": option_leg.gamma,
        "theta": option_leg.theta,
        "vega": option_leg.vega,
        "iv": option_leg.iv,
        "oi": option_leg.oi,
        "volume": option_leg.volume,
    }
