"""Data models for Nuvama bond portfolio tracking.

Covers individual bond holdings and an aggregated portfolio summary.
All monetary fields use Decimal for precision. All dataclasses are frozen.

Key design note: Nuvama's Holdings() response does not include avg_price.
Cost basis is loaded from the seeded `nuvama_positions` table and attached
at parse time by reader.parse_bond_holdings().
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

_TWO_DP = Decimal("0.01")
_FOUR_DP = Decimal("0.0001")


@dataclass(frozen=True)
class NuvamaBondHolding:
    """A single Nuvama bond / NCD / G-Sec / SGB holding.

    All monetary fields are Decimal. Classification is always 'BOND'
    (Nuvama account holds only debt instruments; asTyp field in the API
    is always 'EQUITY' and is not used for classification here).

    Attributes:
        isin: International Securities Identification Number (stable key).
        company_name: Cleaned company/instrument name from cpName.
        trading_symbol: dpName from the response (e.g. '10EFSL34A').
        exchange: Exchange segment ('BSE' or 'NSE').
        qty: Total quantity held.
        avg_price: Average purchase price (from seeded nuvama_positions table).
        ltp: Last traded price from Holdings() response.
        chg_pct: Day-change percent from Holdings() response (e.g. Decimal('-1.28')).
        hair_cut: Pledge haircut percentage (e.g. Decimal('25.00')).
        classification: Always 'BOND'.
    """

    isin: str
    company_name: str
    trading_symbol: str
    exchange: str
    qty: int
    avg_price: Decimal
    ltp: Decimal
    chg_pct: Decimal
    hair_cut: Decimal
    classification: str = "BOND"

    @property
    def cost_basis(self) -> Decimal:
        """Total capital deployed: avg_price × qty."""
        return self.avg_price * self.qty

    @property
    def current_value(self) -> Decimal:
        """Mark-to-market value: ltp × qty."""
        return self.ltp * self.qty

    @property
    def pnl(self) -> Decimal:
        """Unrealized P&L: current_value − cost_basis."""
        return self.current_value - self.cost_basis

    @property
    def pnl_pct(self) -> Decimal | None:
        """P&L as percentage of cost basis, rounded to 2 dp.

        Returns None when cost_basis is zero to avoid division by zero.
        """
        if self.cost_basis == 0:
            return None
        return (self.pnl / self.cost_basis * 100).quantize(_TWO_DP, ROUND_HALF_UP)

    @property
    def day_delta(self) -> Decimal:
        """Approximate day-change in rupees: current_value × chg_pct / 100.

        Derived directly from the chgP field in the Holdings() response.
        No prior snapshot required. Accurate for bonds (stable intraday price).
        """
        return (self.current_value * self.chg_pct / 100).quantize(
            _TWO_DP, ROUND_HALF_UP
        )


@dataclass(frozen=True)
class NuvamaBondSummary:
    """Aggregated Nuvama bond portfolio for one snapshot date.

    Computed once per snapshot run. All monetary fields are Decimal.
    """

    snapshot_date: date
    holdings: tuple[NuvamaBondHolding, ...]

    # Portfolio totals
    total_value: Decimal
    total_basis: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal | None  # None when total_basis is zero

    # Day-change (sum of per-holding day_delta)
    total_day_delta: Decimal
