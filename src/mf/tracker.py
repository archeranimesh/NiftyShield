"""MF portfolio tracker.

Composes MFStore and the AMFI NAV fetcher to perform the daily snapshot
cycle in three steps:

  1. Load current net holdings from the transaction ledger (MFStore)
  2. Fetch today's NAVs from AMFI for all held schemes
  3. Persist one MFNavSnapshot per scheme and return P&L

Intended for daily invocation from scripts/daily_snapshot.py (Commit 6).
The nav_fetcher argument is injectable so tests can pass a plain dict-returning
lambda — no network, no DB required.

P&L precision:
  current_value and pnl_pct are quantized to 2 decimal places (ROUND_HALF_UP).
  pnl is the exact difference — no quantization so the sum across schemes
  equals total_pnl without rounding drift.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable

from src.mf.models import MFHolding, MFNavSnapshot
from src.mf.nav_fetcher import fetch_navs
from src.mf.store import MFStore

logger = logging.getLogger(__name__)

_TWO_DP = Decimal("0.01")

NavFetcherFn = Callable[[set[str]], dict[str, Decimal]]


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

# MFHolding is defined in src.mf.models — imported above.


@dataclass(frozen=True)
class SchemePnL:
    """Per-scheme P&L for a single snapshot date."""

    amfi_code: str
    scheme_name: str
    current_nav: Decimal
    total_units: Decimal
    total_invested: Decimal
    current_value: Decimal   # total_units × current_nav, rounded to 2 dp
    pnl: Decimal             # current_value − total_invested (exact)
    pnl_pct: Decimal         # pnl / total_invested × 100, rounded to 2 dp


@dataclass(frozen=True)
class PortfolioPnL:
    """Aggregate MF portfolio P&L for a given snapshot date."""

    snapshot_date: date
    schemes: list[SchemePnL]
    total_invested: Decimal
    total_current_value: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal   # rounded to 2 dp


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


class MFTracker:
    """Daily MF snapshot: fetch NAVs, persist, return P&L.

    Args:
        store: Live MFStore instance (reads holdings, writes snapshots).
        nav_fetcher: Callable ``(amfi_codes: set[str]) -> dict[str, Decimal]``.
            Defaults to the live AMFI flat-file fetcher.  Pass a lambda in
            tests to keep them fully offline.
    """

    def __init__(self, store: MFStore, nav_fetcher: NavFetcherFn = fetch_navs):
        self._store = store
        self._fetch_navs = nav_fetcher

    def record_snapshot(self, snapshot_date: date | None = None) -> PortfolioPnL:
        """Run the daily MF snapshot cycle.

        Fetches NAVs for all held schemes, upserts one MFNavSnapshot per
        scheme into the store, and returns a full P&L breakdown.

        Schemes whose NAV is absent from the AMFI response are skipped with a
        WARNING log — they do not raise an exception or abort the rest.

        Args:
            snapshot_date: Date to record against.  Defaults to today.

        Returns:
            PortfolioPnL with per-scheme list and portfolio-level totals.
        """
        today = snapshot_date or date.today()
        holdings = self._store.get_holdings()

        if not holdings:
            logger.warning("No MF holdings in store — skipping NAV fetch")
            return _empty_portfolio(today)

        navs = self._fetch_navs(set(holdings.keys()))
        schemes: list[SchemePnL] = []

        for amfi_code, holding in holdings.items():
            if amfi_code not in navs:
                logger.warning("NAV missing for %s — scheme skipped", amfi_code)
                continue
            nav = navs[amfi_code]
            self._store.upsert_nav_snapshot(
                MFNavSnapshot(
                    amfi_code=amfi_code,
                    scheme_name=holding.scheme_name,
                    snapshot_date=today,
                    nav=nav,
                )
            )
            schemes.append(_scheme_pnl(holding, nav))

        return _aggregate(today, schemes)


# ---------------------------------------------------------------------------
# Pure computation helpers — no I/O, independently testable
# ---------------------------------------------------------------------------


def _scheme_pnl(holding: MFHolding, nav: Decimal) -> SchemePnL:
    """Compute P&L for one scheme given its holding and current NAV.

    Args:
        holding: Net units and invested amount for the scheme.
        nav: Current NAV as Decimal.

    Returns:
        SchemePnL with current_value, pnl, and pnl_pct populated.
    """
    current_value = (holding.total_units * nav).quantize(_TWO_DP, ROUND_HALF_UP)
    pnl = current_value - holding.total_invested
    pnl_pct = (
        (pnl / holding.total_invested * Decimal("100")).quantize(_TWO_DP, ROUND_HALF_UP)
        if holding.total_invested
        else Decimal("0.00")
    )
    return SchemePnL(
        amfi_code=holding.amfi_code,
        scheme_name=holding.scheme_name,
        current_nav=nav,
        total_units=holding.total_units,
        total_invested=holding.total_invested,
        current_value=current_value,
        pnl=pnl,
        pnl_pct=pnl_pct,
    )


def _aggregate(snapshot_date: date, schemes: list[SchemePnL]) -> PortfolioPnL:
    """Sum per-scheme figures into portfolio-level totals.

    Args:
        snapshot_date: Date of this snapshot.
        schemes: List of per-scheme P&L records.

    Returns:
        PortfolioPnL with summed totals and overall pnl_pct.
    """
    total_invested = sum((s.total_invested for s in schemes), Decimal("0"))
    total_current_value = sum((s.current_value for s in schemes), Decimal("0"))
    total_pnl = total_current_value - total_invested
    total_pnl_pct = (
        (total_pnl / total_invested * Decimal("100")).quantize(_TWO_DP, ROUND_HALF_UP)
        if total_invested
        else Decimal("0.00")
    )
    return PortfolioPnL(
        snapshot_date=snapshot_date,
        schemes=schemes,
        total_invested=total_invested,
        total_current_value=total_current_value,
        total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct,
    )


def _empty_portfolio(snapshot_date: date) -> PortfolioPnL:
    return PortfolioPnL(
        snapshot_date=snapshot_date,
        schemes=[],
        total_invested=Decimal("0"),
        total_current_value=Decimal("0"),
        total_pnl=Decimal("0"),
        total_pnl_pct=Decimal("0"),
    )
