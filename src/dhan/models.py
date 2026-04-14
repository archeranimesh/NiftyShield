"""Data models for Dhan portfolio tracking.

Covers individual holdings with classification (Equity/Bond) and
aggregated portfolio summaries with day-change deltas.

Monetary fields use Decimal for sub-rupee precision, consistent with
the portfolio and mf modules. All dataclasses are frozen (immutable).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

_TWO_DP = Decimal("0.01")


@dataclass(frozen=True)
class DhanHolding:
    """A single Dhan delivery holding with classification and current price.

    Attributes:
        trading_symbol: NSE trading symbol (e.g. 'NIFTYIETF', 'LIQUIDCASE').
        isin: International Securities Identification Number.
        security_id: Dhan's numeric security ID — used for market quote lookups.
        exchange: Exchange segment from Dhan (e.g. 'NSE_EQ').
        total_qty: Total quantity held in demat.
        collateral_qty: Quantity pledged as collateral.
        avg_cost_price: Average buy price from Dhan.
        classification: 'EQUITY' or 'BOND'.
        ltp: Last traded price (from Dhan marketfeed). None if unavailable.
    """

    trading_symbol: str
    isin: str
    security_id: str
    exchange: str
    total_qty: int
    collateral_qty: int
    avg_cost_price: Decimal
    classification: str  # "EQUITY" or "BOND"
    ltp: Decimal | None = None

    @property
    def cost_basis(self) -> Decimal:
        """Total capital deployed: avg_cost_price × total_qty."""
        return self.avg_cost_price * self.total_qty

    @property
    def current_value(self) -> Decimal | None:
        """Mark-to-market value: ltp × total_qty. None if LTP unavailable."""
        if self.ltp is None:
            return None
        return self.ltp * self.total_qty

    @property
    def pnl(self) -> Decimal | None:
        """Unrealized P&L: current_value − cost_basis. None if LTP unavailable."""
        cv = self.current_value
        if cv is None:
            return None
        return cv - self.cost_basis

    @property
    def pnl_pct(self) -> Decimal | None:
        """P&L as percentage of cost basis, rounded to 2 dp. None if LTP unavailable."""
        p = self.pnl
        if p is None:
            return None
        if self.cost_basis == 0:
            return Decimal("0")
        return (p / self.cost_basis * 100).quantize(_TWO_DP, ROUND_HALF_UP)


@dataclass(frozen=True)
class DhanPortfolioSummary:
    """Aggregated Dhan portfolio split by classification.

    Computed once per snapshot run. All monetary fields are Decimal.
    Day-change fields are None on the first run (no prior snapshot).
    """

    snapshot_date: date

    # Equity component
    equity_holdings: tuple[DhanHolding, ...]
    equity_value: Decimal
    equity_basis: Decimal
    equity_pnl: Decimal
    equity_pnl_pct: Decimal | None

    # Bond component
    bond_holdings: tuple[DhanHolding, ...]
    bond_value: Decimal
    bond_basis: Decimal
    bond_pnl: Decimal
    bond_pnl_pct: Decimal | None

    # Day-change deltas (None on first run)
    equity_day_delta: Decimal | None = None
    bond_day_delta: Decimal | None = None
