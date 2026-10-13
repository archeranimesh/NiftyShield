"""Domain models for Nifty calendar structures and metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.models.portfolio import AssetType, Direction
from src.nifty_calendar.errors import InvalidStructureError, MissingGreeksError


@dataclass(frozen=True)
class CalendarLeg:
    """One leg of a calendar structure with Greeks and entry price.

    All money and Greeks fields are Decimal. None is rejected for Greeks
    at construction time.
    """

    instrument_key: str
    strike: Decimal
    option_type: AssetType
    expiry: date
    side: Direction
    qty_lots: int
    entry_price: Decimal
    delta: Decimal
    vega: Decimal
    iv: Decimal

    def __post_init__(self) -> None:
        """Validate leg constraints."""
        if self.delta is None or self.vega is None or self.iv is None:
            raise MissingGreeksError(
                f"Missing Greeks on leg {self.instrument_key}: "
                f"delta={self.delta}, vega={self.vega}, iv={self.iv}"
            )
        if self.option_type not in (AssetType.CE, AssetType.PE):
            raise InvalidStructureError(f"option_type must be CE or PE, got {self.option_type}")
        if self.side not in (Direction.BUY, Direction.SELL):
            raise InvalidStructureError(f"side must be BUY or SELL, got {self.side}")
        if self.qty_lots <= 0:
            raise InvalidStructureError(f"qty_lots must be positive, got {self.qty_lots}")


@dataclass(frozen=True)
class CalendarStructure:
    """A four-leg Nifty diagonal calendar structure.

    Consists of a near-month short ATM straddle (short_ce, short_pe) and
    far-month long OTM wings (long_ce_wing, long_pe_wing).
    """

    short_ce: CalendarLeg
    short_pe: CalendarLeg
    long_ce_wing: CalendarLeg
    long_pe_wing: CalendarLeg

    def __post_init__(self) -> None:
        """Validate structure constraints and invariants."""
        if self.short_ce.side != Direction.SELL or self.short_pe.side != Direction.SELL:
            raise InvalidStructureError("Short legs must have side=SELL")
        if self.long_ce_wing.side != Direction.BUY or self.long_pe_wing.side != Direction.BUY:
            raise InvalidStructureError("Long wing legs must have side=BUY")
        if self.short_ce.expiry != self.short_pe.expiry:
            raise InvalidStructureError("Short CE and Short PE must have identical expiry")
        if self.short_ce.strike != self.short_pe.strike:
            raise InvalidStructureError("Short CE and Short PE must have identical strike")
        if self.long_ce_wing.expiry != self.long_pe_wing.expiry:
            raise InvalidStructureError("Long wings must have identical expiry")
        if self.short_ce.expiry >= self.long_ce_wing.expiry:
            raise InvalidStructureError("Near expiry must be strictly before far expiry")
        if not (
            self.short_ce.qty_lots > 0
            and self.short_ce.qty_lots
            == self.short_pe.qty_lots
            == self.long_ce_wing.qty_lots
            == self.long_pe_wing.qty_lots
        ):
            raise InvalidStructureError("All four legs must have identical positive qty_lots")
        if (
            self.short_ce.option_type != AssetType.CE
            or self.long_ce_wing.option_type != AssetType.CE
        ):
            raise InvalidStructureError("Call legs must have option_type=CE")
        if (
            self.short_pe.option_type != AssetType.PE
            or self.long_pe_wing.option_type != AssetType.PE
        ):
            raise InvalidStructureError("Put legs must have option_type=PE")

    @property
    def legs(self) -> tuple[CalendarLeg, CalendarLeg, CalendarLeg, CalendarLeg]:
        """Tuple of all four structure legs."""
        return (self.short_ce, self.short_pe, self.long_ce_wing, self.long_pe_wing)

    @property
    def near_expiry(self) -> date:
        """Near expiry date of the short straddle."""
        return self.short_ce.expiry

    @property
    def far_expiry(self) -> date:
        """Far expiry date of the long wings."""
        return self.long_ce_wing.expiry

    @property
    def short_strike(self) -> Decimal:
        """Strike price of the short straddle."""
        return self.short_ce.strike

    @property
    def qty_lots(self) -> int:
        """Uniform quantity in lots across all legs."""
        return self.short_ce.qty_lots

    @property
    def net_credit_per_unit(self) -> Decimal:
        """Net credit collected per unit at entry in rupees."""
        return (self.short_ce.entry_price + self.short_pe.entry_price) - (
            self.long_ce_wing.entry_price + self.long_pe_wing.entry_price
        )

    def net_credit_per_lot(self, lot_size: int) -> Decimal:
        """Net credit collected per lot at entry in rupees.

        Args:
            lot_size: Contract lot size.

        Returns:
            Net credit per lot in rupees as Decimal.
        """
        return self.net_credit_per_unit * Decimal(lot_size)


@dataclass(frozen=True)
class StructureMetrics:
    """Payoff and risk metrics for a calendar structure."""

    net_delta: Decimal
    net_vega: Decimal
    risk_reward: Decimal
    breakeven_low: Decimal
    breakeven_high: Decimal
    breakeven_low_pct: Decimal
    breakeven_high_pct: Decimal
    loss_at_breakeven_low_per_lot: Decimal
    loss_at_breakeven_high_per_lot: Decimal
    net_credit_per_unit: Decimal
    net_credit_per_lot: Decimal
    max_profit_per_lot: Decimal
    max_loss_per_lot: Decimal
