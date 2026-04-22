"""Pure portfolio summary computation — no I/O, no side effects.

All functions here are fully unit-testable without a DB, network, or .env.
They consume plain data structures (Strategy, DailySnapshot, PortfolioSummary)
and return Decimal values or PortfolioSummary dataclasses.

These helpers were extracted from scripts/daily_snapshot.py (TODO 5) so that
the backtesting and visualisation layers (TODO 3) can import them directly
without going through the script.

Deferred imports are preserved for mf.tracker and portfolio.tracker to avoid
potential circular imports and keep this module I/O-free at import time.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.models.portfolio import (
    AssetType,
    DailySnapshot,
    PortfolioSummary,
    Strategy,
)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.mf.tracker import PortfolioPnL
    from src.dhan.models import DhanPortfolioSummary
    from src.nuvama.models import NuvamaBondSummary, NuvamaOptionsSummary
    from src.portfolio.tracker import StrategyPnL


def _etf_current_value(strategies: list[Strategy], prices: dict[str, float]) -> Decimal:
    """Mark-to-market value of all EQUITY legs across strategies.

    ETF legs are assets — value is qty × current LTP.
    Falls back to entry price if LTP is missing (e.g. market closed).

    Args:
        strategies: All loaded Strategy objects.
        prices: instrument_key → LTP from the batch fetch.

    Returns:
        Total ETF value as Decimal.
    """
    total = Decimal("0")
    for strategy in strategies:
        for leg in strategy.legs:
            if leg.asset_type == AssetType.EQUITY:
                ltp = prices.get(leg.instrument_key, leg.entry_price)
                total += Decimal(str(ltp)) * Decimal(str(leg.quantity))
    return total


def _etf_cost_basis(strategies: list[Strategy]) -> Decimal:
    """Total entry cost of all EQUITY legs (qty × entry_price).

    Args:
        strategies: All loaded Strategy objects.

    Returns:
        Sum of entry costs as Decimal.
    """
    return sum(
        leg.entry_price * leg.quantity
        for strategy in strategies
        for leg in strategy.legs
        if leg.asset_type == AssetType.EQUITY
    )


def _build_prev_prices(
    strategies: list[Strategy],
    prev_snapshots: dict[int, DailySnapshot],
) -> dict[str, float]:
    """Build instrument_key → LTP dict from previous-day snapshots.

    Uses the leg_id → instrument_key mapping derived from strategy legs to
    translate the prev_snapshots keyed by leg_id into a prices dict keyed by
    instrument_key — the same format used by _etf_current_value and
    _compute_strategy_pnl_from_prices.

    Args:
        strategies: Strategy objects with DB-assigned leg IDs.
        prev_snapshots: {leg_id: DailySnapshot} from get_prev_snapshots().

    Returns:
        {instrument_key: float(ltp)} for all legs that have a prev-day row.
    """
    leg_id_to_key: dict[int, str] = {
        leg.id: leg.instrument_key
        for strategy in strategies
        for leg in strategy.legs
        if leg.id is not None
    }
    return {
        leg_id_to_key[leg_id]: float(snap.ltp)
        for leg_id, snap in prev_snapshots.items()
        if leg_id in leg_id_to_key
    }


def _compute_prev_mf_pnl(
    prev_nav_snaps: list,  # list[MFNavSnapshot]
    holdings: dict,        # dict[str, MFHolding]
) -> "PortfolioPnL | None":
    """Reconstruct a PortfolioPnL from stored NAV snapshots and current holdings.

    Used by both live and historical paths to compute the previous day's MF
    value for day-change delta. Import of mf.tracker is deferred to avoid
    a cross-module import at module level.

    Args:
        prev_nav_snaps: NAV snapshots from the prior date.
        holdings: Current net holdings from MFStore.get_holdings().

    Returns:
        PortfolioPnL for the prior date, or None if no matching schemes.
    """
    from src.mf.tracker import aggregate_mf_pnl, compute_scheme_pnl

    if not prev_nav_snaps or not holdings:
        return None
    schemes = [
        compute_scheme_pnl(holdings[s.amfi_code], s.nav)
        for s in prev_nav_snaps
        if s.amfi_code in holdings
    ]
    if not schemes:
        return None
    return aggregate_mf_pnl(prev_nav_snaps[0].snapshot_date, schemes)


def _compute_strategy_pnl_from_prices(
    strategy: "Strategy", prices: "dict[str, Decimal]"
) -> "StrategyPnL":
    """Compute StrategyPnL from a pre-built prices dict (no live fetch).

    Used by the historical query path to reconstruct P&L from stored LTPs
    without touching the market client.

    Args:
        strategy: Strategy object with legs already loaded.
        prices: instrument_key → Decimal LTP. Falls back to leg.entry_price
            when a key is absent (same fallback as PortfolioTracker.compute_pnl).

    Returns:
        StrategyPnL with per-leg breakdown.
    """
    from src.portfolio.tracker import LegPnL, StrategyPnL

    leg_pnls = []
    for leg in strategy.legs:
        ltp = prices.get(leg.instrument_key, leg.entry_price)
        leg_pnls.append(
            LegPnL(
                leg=leg,
                current_price=ltp,
                pnl=leg.pnl(ltp),
                pnl_percent=leg.pnl_percent(ltp),
            )
        )
    return StrategyPnL(strategy_name=strategy.name, legs=leg_pnls)


def _build_portfolio_summary(
    snap_date: date,
    strategies: list[Strategy],
    prices: dict[str, float],
    strategy_pnls: dict[str, "StrategyPnL"],
    mf_pnl: "PortfolioPnL | None",
    prev_snapshots: dict[int, DailySnapshot] | None = None,
    prev_mf_pnl: "PortfolioPnL | None" = None,
    dhan_summary: "DhanPortfolioSummary | None" = None,
    nuvama_summary: "NuvamaBondSummary | None" = None,
    nuvama_options_summary: "NuvamaOptionsSummary | None" = None,
) -> PortfolioSummary:
    """Compute combined portfolio values into a PortfolioSummary.

    Owns all arithmetic — ETF mark-to-market, options net P&L, MF totals,
    Dhan equity/bond, combined aggregates, and day-change deltas.
    Pure: no I/O, no side effects.

    Args:
        snap_date: The snapshot date (stored in PortfolioSummary.snapshot_date).
        strategies: All loaded Strategy objects.
        prices: instrument_key → LTP (current day).
        strategy_pnls: strategy name → StrategyPnL (from compute_pnl).
        mf_pnl: Completed MF PortfolioPnL, or None if the MF fetch failed.
        prev_snapshots: {leg_id: DailySnapshot} from get_prev_snapshots(), or None.
        prev_mf_pnl: PortfolioPnL for the prior date, or None.
        dhan_summary: DhanPortfolioSummary, or None if Dhan unavailable.
        nuvama_summary: NuvamaBondSummary, or None if Nuvama unavailable.

    Returns:
        Fully populated PortfolioSummary dataclass.
    """
    etf_value = _etf_current_value(strategies, prices)
    etf_basis = _etf_cost_basis(strategies)

    options_pnl = sum(
        (p.total_pnl for p in strategy_pnls.values() if p),
        Decimal("0"),
    )

    mf_value = mf_pnl.total_current_value if mf_pnl else Decimal("0")
    mf_invested = mf_pnl.total_invested if mf_pnl else Decimal("0")

    dhan_eq_value = dhan_summary.equity_value if dhan_summary else Decimal("0")
    dhan_eq_basis = dhan_summary.equity_basis if dhan_summary else Decimal("0")
    dhan_bd_value = dhan_summary.bond_value if dhan_summary else Decimal("0")
    dhan_bd_basis = dhan_summary.bond_basis if dhan_summary else Decimal("0")

    nuvama_bd_value = (
        nuvama_summary.total_value if nuvama_summary else Decimal("0")
    )
    nuvama_bd_basis = (
        nuvama_summary.total_basis if nuvama_summary else Decimal("0")
    )

    total_value = (
        mf_value + etf_value + options_pnl
        + dhan_eq_value + dhan_bd_value + nuvama_bd_value
    )
    total_invested = (
        mf_invested + etf_basis
        + dhan_eq_basis + dhan_bd_basis + nuvama_bd_basis
    )
    
    total_pnl = (
        (mf_pnl.total_pnl if mf_pnl else Decimal("0"))
        + (etf_value - etf_basis)
        + options_pnl
        + (dhan_summary.equity_pnl if dhan_summary else Decimal("0"))
        + (dhan_summary.bond_pnl if dhan_summary else Decimal("0"))
        + (nuvama_summary.total_pnl if nuvama_summary else Decimal("0"))
        + (
            nuvama_options_summary.net_pnl
            if nuvama_options_summary
            else Decimal("0")
        )
    )
    
    total_pnl_pct = (
        (total_pnl / total_invested * 100).quantize(Decimal("0.01"))
        if total_invested
        else Decimal("0")
    )

    # ── Day-change deltas (None when prior data unavailable) ──────
    etf_day_delta: Decimal | None = None
    options_day_delta: Decimal | None = None
    mf_day_delta: Decimal | None = None
    finrakshak_day_delta: Decimal | None = None

    if prev_snapshots:
        prev_prices = _build_prev_prices(strategies, prev_snapshots)
        prev_etf_value = _etf_current_value(strategies, prev_prices)
        prev_prices_dec = {k: Decimal(str(v)) for k, v in prev_prices.items()}
        prev_options_pnl = sum(
            (_compute_strategy_pnl_from_prices(s, prev_prices_dec).total_pnl
             for s in strategies),
            Decimal("0"),
        )
        etf_day_delta = etf_value - prev_etf_value
        options_day_delta = options_pnl - prev_options_pnl

        # Finrakshak delta isolated — needed for hedge effectiveness reporting
        frak_strat = next(
            (s for s in strategies if getattr(s, "name", None) == "finrakshak"), None
        )
        curr_frak = strategy_pnls.get("finrakshak")
        if frak_strat is not None and curr_frak is not None:
            prev_frak_pnl = _compute_strategy_pnl_from_prices(frak_strat, prev_prices_dec)
            finrakshak_day_delta = curr_frak.total_pnl - prev_frak_pnl.total_pnl

    if prev_mf_pnl is not None and mf_pnl is not None:
        mf_day_delta = mf_value - prev_mf_pnl.total_current_value

    any_delta = (
        etf_day_delta is not None
        or mf_day_delta is not None
        or (
            dhan_summary.equity_day_delta if dhan_summary else None
        ) is not None
        or (
            dhan_summary.bond_day_delta if dhan_summary else None
        ) is not None
        or (
            nuvama_summary.total_day_delta if nuvama_summary else None
        ) is not None
    )
    total_day_delta: Decimal | None = None
    if any_delta:
        total_day_delta = (
            (mf_day_delta or Decimal("0"))
            + (etf_day_delta or Decimal("0"))
            + (options_day_delta or Decimal("0"))
            + (
                (dhan_summary.equity_day_delta or Decimal("0"))
                if dhan_summary else Decimal("0")
            )
            + (
                (dhan_summary.bond_day_delta or Decimal("0"))
                if dhan_summary else Decimal("0")
            )
            + (
                (nuvama_summary.total_day_delta or Decimal("0"))
                if nuvama_summary else Decimal("0")
            )
        )

    return PortfolioSummary(
        snapshot_date=snap_date,
        mf_pnl=mf_pnl,
        dhan=dhan_summary,
        nuvama_bonds=nuvama_summary,
        nuvama_options=nuvama_options_summary,
        etf_value=etf_value,
        etf_basis=etf_basis,
        options_pnl=options_pnl,
        total_value=total_value,
        total_invested=total_invested,
        total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct,
        mf_day_delta=mf_day_delta,
        etf_day_delta=etf_day_delta,
        options_day_delta=options_day_delta,
        total_day_delta=total_day_delta,
        finrakshak_day_delta=finrakshak_day_delta,
    )
