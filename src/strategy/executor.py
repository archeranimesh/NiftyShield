"""Paper trading execution layer.

PaperFillSimulator: computes synthetic fills via the VIX-regime slippage
model defined in DECISIONS.md §Slippage Model.

PaperExecutor: thin orchestration layer that applies an ApprovedAction
against PaperStore — closing requested legs and opening new ones — then
returns the updated position list.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

import structlog

from src.models.options import OptionChain
from src.models.portfolio import TradeAction
from src.paper.models import PaperPosition, PaperTrade
from src.paper.store import PaperStore
from src.strategy._price_utils import find_option_leg, resolve_price
from src.strategy.protocol import ApprovedAction
from src.utils.logging import bind_trace_id, generate_trace_id

log = structlog.get_logger(__name__)

# VIX-regime slippage bands (absolute INR) — DECISIONS.md §Slippage Model
# Tuple: (upper_bound_exclusive, slippage_INR)
_VIX_BANDS: list[tuple[float, Decimal]] = [
    (20.0, Decimal("1.0")),
    (25.0, Decimal("1.5")),
    (30.0, Decimal("3.0")),
    (float("inf"), Decimal("4.0")),
]

# Default slippage when VIX is unknown — mid-range band (VIX 20–25)
_DEFAULT_SLIPPAGE = Decimal("1.5")


@dataclass(frozen=True)
class FillResult:
    """Result of a synthetic fill computation.

    Attributes:
        instrument_key: Upstox instrument key for this leg.
        action: "BUY" or "SELL".
        quantity: Units transacted. Always positive.
        fill_price: Simulated execution price (mid ± slippage).
        slippage: Absolute INR slippage applied.
    """

    instrument_key: str
    action: Literal["BUY", "SELL"]
    quantity: int
    fill_price: Decimal
    slippage: Decimal


class PaperFillSimulator:
    """Synthetic fill engine using a VIX-regime slippage model.

    Slippage is absolute INR, regime-aware:
    - VIX ≤ 20  → ₹1.0
    - VIX 20–25 → ₹1.5
    - VIX 25–30 → ₹3.0
    - VIX > 30  → ₹4.0
    - VIX None  → ₹1.5 (default, mid-range)

    BUY fills at mid + slippage (paid more than mid).
    SELL fills at mid − slippage (received less than mid).
    """

    def simulate_fill(
        self,
        instrument_key: str,
        action: Literal["BUY", "SELL"],
        quantity: int,
        mid_price: Decimal,
        vix: float | None = None,
    ) -> FillResult:
        """Compute synthetic fill using VIX-regime slippage model.

        Args:
            instrument_key: Upstox instrument key.
            action: "BUY" or "SELL".
            quantity: Units. Always positive.
            mid_price: Current mid price of the option leg.
            vix: India VIX value; None → default slippage band.

        Returns:
            FillResult with fill_price and slippage applied.
        """
        slippage = self._slippage_for_vix(vix)
        if action == "BUY":
            fill_price = mid_price + slippage
        else:
            fill_price = mid_price - slippage
        # Option prices cannot be negative; clamp to minimum tick
        fill_price = max(fill_price, Decimal("0.01"))
        return FillResult(
            instrument_key=instrument_key,
            action=action,
            quantity=quantity,
            fill_price=fill_price,
            slippage=slippage,
        )

    def _slippage_for_vix(self, vix: float | None) -> Decimal:
        """Return absolute INR slippage for a given VIX level.

        Args:
            vix: India VIX; None → default.

        Returns:
            Slippage as Decimal INR.
        """
        if vix is None:
            return _DEFAULT_SLIPPAGE
        for upper, slip in _VIX_BANDS:
            if vix <= upper:
                return slip
        return _VIX_BANDS[-1][1]  # unreachable; inf band catches all


class PaperExecutor:
    """Orchestration layer that applies an ApprovedAction to PaperStore.

    Responsibilities:
    1. Close requested legs (reverse-action trade at simulated fill).
    2. Open new legs (forward trade at simulated fill).
    3. Write an audit row to council_outputs (PB1.6 schema; best-effort).
    4. Return the updated list[PaperPosition] for the strategy.
    """

    def __init__(
        self,
        store: PaperStore,
        simulator: PaperFillSimulator,
        db_path: str,
    ) -> None:
        """Initialise the executor.

        Args:
            store: PaperStore instance for trade persistence.
            simulator: PaperFillSimulator for fill price computation.
            db_path: SQLite DB path (used for audit writes).
        """
        self._store = store
        self._simulator = simulator
        self._db_path = db_path

    def apply(
        self,
        strategy_name: str,
        action: ApprovedAction,
        market: OptionChain,
        approval_id: int,
        vix: float | None = None,
    ) -> list[PaperPosition]:
        """Execute an approved action and return the updated position list.

        Steps:
        1. For each leg_role in action.legs_to_close: record a closing trade
           via PaperStore.record_trade (action = opposite of net position).
        2. For each LegSpec in action.legs_to_open: simulate fill and record
           an opening trade via PaperStore.record_trade.
        3. Write per-leg audit rows to paper_action_audit (best-effort).
        4. Return updated list[PaperPosition] from PaperStore.get_positions().

        Args:
            strategy_name: Paper strategy name (must start with "paper_").
            action: Approved action describing legs to close and open.
            market: Current option chain snapshot (context / future price lookup).
            approval_id: FK to pending_approvals record for audit trail.
            vix: India VIX at execution time; None → default slippage band.

        Returns:
            Updated open positions for the strategy after applying the action.
        """
        trace_id = generate_trace_id()
        bind_trace_id(trace_id)
        log.info(
            "action.dispatch",
            strategy=strategy_name,
            action_type=action.action_type,
            legs_to_close=action.legs_to_close,
            legs_to_open=[s.leg_role for s in action.legs_to_open],
            trace_id=trace_id,
        )
        today = date.today()

        # 1. Close legs
        for leg_role in action.legs_to_close:
            position = self._store.get_position(strategy_name, leg_role)
            if position.net_qty == 0:
                continue  # nothing open for this leg
            close_action = TradeAction.SELL if position.net_qty > 0 else TradeAction.BUY
            mid_price = self._resolve_mid_price(position.instrument_key, market)
            fill = self._simulator.simulate_fill(
                instrument_key=position.instrument_key,
                action=close_action.value,
                quantity=abs(position.net_qty),
                mid_price=mid_price,
                vix=vix,
            )
            trade = PaperTrade(
                strategy_name=strategy_name,
                leg_role=leg_role,
                instrument_key=position.instrument_key,
                trade_date=today,
                action=close_action,
                quantity=fill.quantity,
                price=fill.fill_price,
                notes=f"executor_close approval_id={approval_id}",
                ivr_at_entry=None,
                is_paper=True,
            )
            self._store.record_trade(trade)
            self._write_audit(
                strategy_name,
                action.action_type,
                leg_role,
                fill.fill_price,
                fill.quantity,
                action.rationale,
            )
            log.info(
                "action.fill",
                strategy=strategy_name,
                action_type="close",
                leg_role=leg_role,
                price=str(fill.fill_price),
                qty=fill.quantity,
            )

        # 2. Open legs
        for leg_spec in action.legs_to_open:
            trade_action = TradeAction(leg_spec.action)
            mid_price = self._resolve_mid_price(leg_spec.instrument_key, market)
            fill = self._simulator.simulate_fill(
                instrument_key=leg_spec.instrument_key,
                action=leg_spec.action,
                quantity=leg_spec.quantity,
                mid_price=mid_price,
                vix=vix,
            )
            trade = PaperTrade(
                strategy_name=strategy_name,
                leg_role=leg_spec.leg_role,
                instrument_key=leg_spec.instrument_key,
                trade_date=today,
                action=trade_action,
                quantity=fill.quantity,
                price=fill.fill_price,
                notes=leg_spec.notes or f"executor_open approval_id={approval_id}",
                ivr_at_entry=None,
                is_paper=True,
            )
            self._store.record_trade(trade)
            self._write_audit(
                strategy_name,
                action.action_type,
                leg_spec.leg_role,
                fill.fill_price,
                fill.quantity,
                action.rationale,
            )
            log.info(
                "action.fill",
                strategy=strategy_name,
                action_type="open",
                leg_role=leg_spec.leg_role,
                price=str(fill.fill_price),
                qty=fill.quantity,
            )

        # 3. (audit written inline per leg above)

        log.info(
            "action.complete",
            strategy=strategy_name,
            action_type=action.action_type,
            approval_id=approval_id,
            trace_id=trace_id,
        )

        # 4. Return updated positions
        return self._store.get_positions(strategy_name)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_mid_price(self, instrument_key: str, market: OptionChain) -> Decimal:
        """Resolve mid price for an instrument from the option chain.

        Args:
            instrument_key: Upstox instrument key.
            market: Current option chain snapshot.

        Returns:
            Mid price as ``Decimal``.

        Raises:
            ValueError: When the leg is absent from the chain or carries no
                positive price. Callers must not proceed with a zero-price fill.
        """
        leg = find_option_leg(instrument_key, market)
        if leg is None:
            raise ValueError(f"resolve_mid_price: leg absent from chain for {instrument_key}")
        return resolve_price(leg)

    def _write_audit(
        self,
        strategy_name: str,
        action_type: str,
        leg_role: str,
        price: Decimal,
        qty: int,
        rationale: str | None,
    ) -> None:
        """Write one per-leg audit row to paper_action_audit.

        Best-effort: never raises. Audit failure must not block execution.

        Args:
            strategy_name: Strategy that executed the action.
            action_type: e.g. ``"CLOSE_FULL"``, ``"PROFIT_TARGET"``.
            leg_role: e.g. ``"short_put"``.
            price: Fill price as Decimal.
            qty: Absolute quantity filled.
            rationale: Free-text rationale from the approved action.
        """
        try:
            self._store.record_action_audit(
                strategy_name=strategy_name,
                action_type=action_type,
                leg_role=leg_role,
                price=price,
                qty=qty,
                rationale=rationale,
            )
        except Exception:
            log.warning(
                "action.audit_failed",
                strategy=strategy_name,
                action_type=action_type,
                leg_role=leg_role,
            )
