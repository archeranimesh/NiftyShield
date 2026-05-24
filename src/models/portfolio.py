"""Shared data models for portfolio strategy tracking.

Canonical home for all portfolio domain types. Modules in src/portfolio/,
src/strategy/, src/risk/, and src/execution/ all import from here — never
from each other — to keep the dependency graph acyclic.

Covers strategy definitions, individual legs, daily price/greeks snapshots,
trade ledger entries, and the combined portfolio summary dataclass.

All timestamps are UTC internally; IST conversion happens at display layer only.
Monetary fields (entry_price, ltp, close, underlying_price, price) use Decimal
to preserve sub-rupee precision through P&L calculations and SQLite round-trips.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.mf.tracker import PortfolioPnL
    from src.dhan.models import DhanPortfolioSummary
    from src.nuvama.models import NuvamaBondSummary, NuvamaOptionsSummary
from enum import Enum

from pydantic import (
    BaseModel,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

logger = logging.getLogger(__name__)


class TradeAction(str, Enum):
    """Direction of a physical trade execution — BUY or SELL."""

    BUY = "BUY"
    SELL = "SELL"


class Trade(BaseModel):
    """A single physical trade execution — one row in the trades ledger.

    Immutable after construction (frozen=True). Monetary fields use Decimal
    stored as TEXT in SQLite, same convention as Leg.entry_price and MFTransaction.

    Attributes:
        strategy_name: Strategy this trade belongs to, e.g. "ILTS" or "FinRakshak".
        leg_role: Human label identifying the position, e.g. "EBBETF0431".
        instrument_key: Upstox instrument key, e.g. "NSE_EQ|INF754K01LE1".
        trade_date: Actual execution date.
        action: BUY or SELL.
        quantity: Units transacted. Always positive — direction is in action.
        price: Execution price per unit. Always positive.
        notes: Optional free-text annotation (contract note ref, reason, etc.).
    """

    strategy_name: str = Field(..., min_length=1)
    leg_role: str = Field(..., min_length=1)
    instrument_key: str = Field(..., min_length=1)
    trade_date: date
    action: TradeAction
    quantity: int = Field(..., gt=0)
    price: Decimal = Field(..., gt=0)
    notes: str = ""

    model_config = {"frozen": True}

    @field_validator("price", mode="before")
    @classmethod
    def price_must_be_positive(cls, v: object) -> object:
        """Coerce str/float inputs and guard against zero/negative values."""
        if isinstance(v, float):
            v = Decimal(str(v))
        return v


class Position(BaseModel):
    """Aggregated positional state for a strategy leg from the trades ledger.

    Attributes:
        strategy_name: Strategy this position belongs to.
        leg_role: Role/name of the leg.
        instrument_key: Instrument key of the position, or None if no trades exist.
        quantity: Net quantity (positive for net long, negative for net short).
        average_price: Weighted average buy price of remaining units.
    """

    strategy_name: str = Field(..., min_length=1)
    leg_role: str = Field(..., min_length=1)
    instrument_key: str | None = Field(default=None)
    quantity: int  # negative for net short positions
    average_price: Decimal = Field(default=Decimal("0"), ge=0)

    model_config = {"frozen": True}

    @field_validator("average_price", mode="before")
    @classmethod
    def avg_price_must_be_non_negative(cls, v: object) -> object:
        """Coerce str/float/int inputs and guard against negative values."""
        if isinstance(v, float):
            v = Decimal(str(v))
        elif isinstance(v, (str, int)):
            v = Decimal(v)
        if isinstance(v, Decimal) and v < 0:
            raise ValueError("average_price must be non-negative")
        return v


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ProductType(str, Enum):
    CNC = "CNC"
    NRML = "NRML"
    MIS = "MIS"


class AssetType(str, Enum):
    EQUITY = "EQUITY"
    BOND = "BOND"
    CE = "CE"
    PE = "PE"
    FUTURES = "FUTURES"


class Leg(BaseModel):
    """A single leg of a multi-leg strategy."""

    id: int | None = None
    strategy_id: int | None = None
    instrument_key: str = Field(description="Upstox instrument key for API lookups")
    display_name: str = Field(description="Human-readable name, e.g. 'NIFTY DEC 23000 PE'")
    asset_type: AssetType
    direction: Direction
    quantity: int
    lot_size: int = Field(default=1, description="Lot size — 1 for ETFs, 75 for Nifty options")
    entry_price: Decimal
    entry_date: date
    expiry: date | None = Field(
        default=None, description="Expiry date for F&O legs, None for equity"
    )
    strike: Decimal | None = Field(default=None, description="Strike price for options")
    product_type: ProductType

    @model_validator(mode="after")
    def validate_leg_invariants(self) -> Leg:
        """Enforce option/futures leg constraints, strike grid, and
        expiry schedules.
        """
        # 1. Asset type specific expiry and strike checks
        if self.asset_type in {AssetType.EQUITY, AssetType.BOND}:
            if self.expiry is not None:
                raise ValueError(
                    f"Expiry must be None for {self.asset_type.name}"
                )
            if self.strike is not None:
                raise ValueError(
                    f"Strike must be None for {self.asset_type.name}"
                )
        elif self.asset_type == AssetType.FUTURES:
            if self.expiry is None:
                raise ValueError("Expiry must not be None for FUTURES")
            if self.strike is not None:
                raise ValueError("Strike must be None for FUTURES")
        elif self.asset_type in {AssetType.CE, AssetType.PE}:
            if self.expiry is None:
                raise ValueError(
                    f"Expiry must not be None for option "
                    f"type {self.asset_type.name}"
                )
            if self.strike is None:
                raise ValueError(
                    f"Strike must not be None for option "
                    f"type {self.asset_type.name}"
                )

        # 2. Strike grid validation for Nifty options
        if (
            self.asset_type in {AssetType.CE, AssetType.PE}
            and self.strike is not None
        ):
            # Check if Nifty 50 option (exclude BANK/FIN/MIDCPNIFTY)
            key_upper = self.instrument_key.upper()
            name_upper = self.display_name.upper()
            is_nifty = (
                ("NIFTY" in key_upper or "NIFTY" in name_upper)
                and not any(
                    x in key_upper or x in name_upper
                    for x in {"BANK", "FIN", "MIDCP"}
                )
            )
            if is_nifty:
                # strike < 18000: multiple of 50
                # strike >= 18000: multiple of 100
                strike_dec = self.strike
                is_low = strike_dec < Decimal("18000")
                grid = Decimal("50") if is_low else Decimal("100")
                if strike_dec % grid != Decimal("0"):
                    raise ValueError(
                        f"Nifty strike {self.strike} must be a "
                        f"multiple of {grid}"
                    )

        # 3. Expiry validations (only for F&O legs where expiry is not None)
        if self.expiry is not None:
            # Check whitelist exceptions (skip validations)
            whitelist = {date(2026, 4, 7), date(2026, 12, 29)}
            if self.expiry not in whitelist:
                # Import is_trading_day inline to prevent circular imports
                from src.market_calendar.holidays import is_trading_day
                
                # Check 1: Expiry must be a trading day
                if not is_trading_day(self.expiry):
                    raise ValueError(
                        f"Expiry date {self.expiry} is not a valid trading day"
                    )
                
                # Check 2: Expiry must be Thursday, or the
                # preceding trading day if Thursday is a holiday.
                # Find Thursday of the expiry's week
                # weekday() is 0 for Monday, ..., 3 for Thursday
                weekday_diff = 3 - self.expiry.weekday()
                nominal_thursday = (
                    self.expiry + timedelta(days=weekday_diff)
                )
                
                if self.expiry > nominal_thursday:
                    # Expiry cannot be after Thursday (e.g. Friday)
                    raise ValueError(
                        f"Expiry date {self.expiry} cannot be after "
                        f"Thursday of its week"
                    )
                
                # Verify that all days between expiry + 1 and nominal_thursday
                # (inclusive) are NOT trading days
                curr = self.expiry + timedelta(days=1)
                while curr <= nominal_thursday:
                    if is_trading_day(curr):
                        raise ValueError(
                            f"Expiry date {self.expiry} must be Thursday or "
                            f"the preceding trading day if Thursday is a "
                            f"holiday. {curr} is a trading day after "
                            f"{self.expiry} in the same week."
                        )
                    curr += timedelta(days=1)

                # Check 3: Prior to June 27, 2019, option
                # expiries must strictly be monthly.
                is_option = self.asset_type in {AssetType.CE, AssetType.PE}
                if is_option and self.expiry < date(2019, 6, 27):
                    # Compute last Thursday of the month
                    if self.expiry.month == 12:
                        next_month_1st = date(self.expiry.year + 1, 1, 1)
                    else:
                        next_month_1st = date(
                            self.expiry.year, self.expiry.month + 1, 1
                        )
                    last_day_of_month = next_month_1st - timedelta(days=1)
                    
                    # Find last Thursday of the month
                    offset = (last_day_of_month.weekday() - 3) % 7
                    last_thursday = (
                        last_day_of_month - timedelta(days=offset)
                    )
                    
                    if self.expiry > last_thursday:
                        raise ValueError(
                            f"Expiry date {self.expiry} is after the last "
                            f"Thursday {last_thursday} of the month"
                        )
                    
                    # All days from expiry + 1 to last_thursday
                    # must not be trading days.
                    curr = self.expiry + timedelta(days=1)
                    while curr <= last_thursday:
                        if is_trading_day(curr):
                            raise ValueError(
                                f"Prior to June 27, 2019, option expiries "
                                f"must strictly be monthly expiries. "
                                f"{self.expiry} is not the last Thursday "
                                f"of the month or the preceding trading "
                                f"day if the last Thursday is a holiday. "
                                f"{curr} is a trading day after "
                                f"{self.expiry} in the same month."
                            )
                        curr += timedelta(days=1)
                        
        return self

    @computed_field
    @property
    def total_lots(self) -> int:
        """Number of lots (quantity / lot_size)."""
        return self.quantity // self.lot_size if self.lot_size > 0 else self.quantity

    @computed_field
    @property
    def entry_value(self) -> Decimal:
        """Total capital deployed at entry."""
        return self.entry_price * self.quantity

    def pnl(self, current_price: float | Decimal) -> Decimal:
        """Compute unrealized P&L for this leg at a given price.

        Accepts float (from broker API) or Decimal. Float inputs are
        converted via str() to avoid binary representation errors.

        For BUY legs:  (current - entry) * quantity
        For SELL legs: (entry - current) * quantity
        """
        cp = current_price if isinstance(current_price, Decimal) else Decimal(str(current_price))
        if self.direction == Direction.BUY:
            return (cp - self.entry_price) * self.quantity
        return (self.entry_price - cp) * self.quantity

    def pnl_percent(self, current_price: float | Decimal) -> Decimal:
        """P&L as percentage of entry value."""
        if self.entry_value == 0:
            return Decimal("0")
        return (self.pnl(current_price) / abs(self.entry_value)) * 100


class Strategy(BaseModel):
    """A named strategy comprising one or more legs."""

    id: int | None = None
    name: str
    description: str = ""
    legs: list[Leg] = Field(default_factory=list)
    created_at: datetime | None = None

    @computed_field
    @property
    def total_entry_value(self) -> Decimal:
        """Net capital deployed across all legs (buys positive, sells negative)."""
        total = Decimal("0")
        for leg in self.legs:
            if leg.direction == Direction.BUY:
                total += leg.entry_value
            else:
                total -= leg.entry_value
        return total

    def total_pnl(self, prices: dict[int, float | Decimal]) -> Decimal:
        """Compute strategy-level P&L given current prices keyed by leg ID.

        Args:
            prices: Mapping of leg.id -> current LTP (float or Decimal).
        """
        return sum(
            (leg.pnl(prices[leg.id])
             for leg in self.legs
             if leg.id is not None and leg.id in prices),
            Decimal("0"),
        )

    def get_protection_delta(
        self,
        current_pnl: Decimal,
        prev_pnl: Decimal,
    ) -> Decimal | None:
        """Calculate the protection delta contribution of this strategy.

        Returns None by default. Subclasses (like HedgeStrategy) can override
        this to compute the delta compared to prior day's P&L.
        """
        return None


class HedgeStrategy(Strategy):
    """A strategy that serves as a portfolio hedge."""

    def get_protection_delta(
        self,
        current_pnl: Decimal,
        prev_pnl: Decimal,
    ) -> Decimal | None:
        """Calculate the protection delta for this hedge strategy."""
        return current_pnl - prev_pnl


_STRATEGY_REGISTRY: dict[str, type[Strategy]] = {}


def register_strategy_type(name: str, cls: type[Strategy]) -> None:
    """Register a strategy subclass for polymorphic instantiation by name."""
    _STRATEGY_REGISTRY[name.lower()] = cls


def create_strategy_instance(
    id: int | None,
    name: str,
    description: str,
    legs: list[Leg],
    created_at: datetime | None,
) -> Strategy:
    """Polymorphic factory to construct the appropriate Strategy subclass."""
    if name.lower() not in _STRATEGY_REGISTRY:
        # Dynamic import of specifically named strategy modules to register their subclasses.
        # This keeps imports targeted and avoids loading unrelated strategies (and their validation checks).
        # Note: 'finideas' is currently hardcoded as the sole provider package. If more provider
        # directories are added under strategies/, they should be appended to the provider list.
        try:
            import importlib
            for provider in ["finideas"]:
                try:
                    importlib.import_module(f"src.portfolio.strategies.{provider}.{name.lower()}")
                    break
                except ImportError:
                    continue
        except ImportError:
            pass
        except Exception as e:
            logger.warning(
                "Unexpected error during dynamic registration of strategy '%s': %s",
                name,
                e,
                exc_info=True,
            )

    cls = _STRATEGY_REGISTRY.get(name.lower(), Strategy)
    return cls(
        id=id,
        name=name,
        description=description,
        legs=legs,
        created_at=created_at,
    )


class DailySnapshot(BaseModel):
    """A single day's closing data for one leg."""

    id: int | None = None
    leg_id: int
    snapshot_date: date
    ltp: Decimal
    close: Decimal | None = None
    iv: float | None = Field(default=None, description="Implied volatility")
    delta: float | None = None
    theta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    oi: int | None = Field(default=None, description="Open interest")
    volume: int | None = None
    underlying_price: Decimal | None = Field(
        default=None, description="Nifty spot at snapshot time"
    )

    def leg_pnl(self, entry_price: Decimal, quantity: int, direction: Direction) -> Decimal:
        """Compute P&L using this snapshot's LTP."""
        if direction == Direction.BUY:
            return (self.ltp - entry_price) * quantity
        return (entry_price - self.ltp) * quantity


@dataclass(frozen=True)
class PortfolioSummary:
    """Combined portfolio value snapshot across MF, ETF, and options.

    Computed once per snapshot run and consumed by both the formatted output
    path and the upcoming visualization layer.  All monetary fields are
    Decimal.  Day-change fields are None on the first ever run when no
    prior-day snapshot exists.
    """

    snapshot_date: date

    # ETF component
    etf_value: Decimal
    etf_basis: Decimal

    # Options net P&L (sign-corrected for short legs)
    options_pnl: Decimal

    # Combined totals
    total_value: Decimal
    total_invested: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal  # quantized to 2 dp

    mf_pnl: "PortfolioPnL | None" = None
    dhan: "DhanPortfolioSummary | None" = None
    nuvama_bonds: "NuvamaBondSummary | None" = None
    nuvama_options: "NuvamaOptionsSummary | None" = None

    # Day-change deltas — None when prior-day data is unavailable
    mf_day_delta: Decimal | None = None
    etf_day_delta: Decimal | None = None
    options_day_delta: Decimal | None = None
    total_day_delta: Decimal | None = None

    # FinRakshak-specific day delta — isolated from combined options_day_delta
    # Enables hedge effectiveness reporting: MF Δday + FinRakshak Δday = net protection
    finrakshak_day_delta: Decimal | None = None

    @property
    def mf_available(self) -> bool:
        return self.mf_pnl is not None

    @property
    def dhan_available(self) -> bool:
        return self.dhan is not None

    @property
    def nuvama_available(self) -> bool:
        return self.nuvama_bonds is not None

    @property
    def nuvama_options_available(self) -> bool:
        return self.nuvama_options is not None
