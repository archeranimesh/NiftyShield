from __future__ import annotations

from collections import Counter
from decimal import Decimal

import structlog

from src.signals.models import (
    DailySignal,
    Direction,
    MarketSnapshot,
    SignalResponse,
    TradeAction,
)

logger = structlog.get_logger(__name__)

NIFTY_STRIKE_STEP = 50


class SignalAggregator:
    """Combine per-model signal responses into one consensus DailySignal.

    Pure / no I/O. Rejected responses are logged and dropped from the
    vote -- they are never treated as a NEUTRAL vote.
    """

    def __init__(
        self,
        min_confidence: int = 3,
        consensus_required: int = 2,
    ) -> None:
        """Configure the confidence gate and the consensus threshold.

        Args:
            min_confidence: Minimum mean confidence of agreeing models for
                a directional trade; below this the action is overridden
                to NO_TRADE.
            consensus_required: Number of validated models that must agree
                on a direction for consensus to form.
        """
        self.min_confidence = min_confidence
        self.consensus_required = consensus_required

    def aggregate(
        self,
        snapshot: MarketSnapshot,
        responses: list[SignalResponse],
    ) -> DailySignal:
        """Produce the day's consensus signal from raw model responses.

        Args:
            snapshot: Market context the responses were generated against.
            responses: One SignalResponse per provider that returned.

        Returns:
            The aggregated DailySignal. trade_action is NO_TRADE unless
            ``consensus_required`` validated models agree on a direction
            whose mean confidence clears ``min_confidence``.
        """
        atm = snapshot.option_chain.atm_strike
        valid_strikes = {atm - NIFTY_STRIKE_STEP, atm, atm + NIFTY_STRIKE_STEP}
        valid = [r for r in responses if self._is_valid(r, valid_strikes)]

        by_direction = _direction_votes(valid)
        for direction in (Direction.BULLISH, Direction.BEARISH):
            agreeing = by_direction.get(direction, [])
            if len(agreeing) >= self.consensus_required:
                return self._consensus_signal(snapshot, responses, direction, agreeing, atm)

        return DailySignal(
            trade_date=snapshot.trade_date,
            responses=responses,
            consensus_direction=Direction.NEUTRAL,
            consensus_confidence=Decimal("0"),
            trade_action=TradeAction.NO_TRADE,
            recommended_strike=None,
            agreeing_models=[],
            dissenting_models=[r.provider for r in responses],
        )

    def _is_valid(
        self,
        response: SignalResponse,
        valid_strikes: set[int],
    ) -> bool:
        """Return True if the response passes strike and confidence checks."""
        if response.recommended_strike not in valid_strikes:
            logger.warning(
                "signal_response_rejected",
                provider=response.provider,
                reason="strike_out_of_band",
                recommended_strike=response.recommended_strike,
            )
            return False
        if not 1 <= response.confidence <= 5:
            logger.warning(
                "signal_response_rejected",
                provider=response.provider,
                reason="confidence_out_of_range",
                confidence=response.confidence,
            )
            return False
        return True

    def _consensus_signal(
        self,
        snapshot: MarketSnapshot,
        responses: list[SignalResponse],
        direction: Direction,
        agreeing: list[SignalResponse],
        atm: int,
    ) -> DailySignal:
        """Build the DailySignal for a formed directional consensus."""
        confidence = sum(Decimal(r.confidence) for r in agreeing) / len(agreeing)
        agreeing_providers = [r.provider for r in agreeing]
        dissenting = [r.provider for r in responses if r.provider not in agreeing_providers]

        if confidence < self.min_confidence:
            return DailySignal(
                trade_date=snapshot.trade_date,
                responses=responses,
                consensus_direction=direction,
                consensus_confidence=confidence,
                trade_action=TradeAction.NO_TRADE,
                recommended_strike=None,
                agreeing_models=agreeing_providers,
                dissenting_models=dissenting,
            )

        action = TradeAction.BUY_CALL if direction is Direction.BULLISH else TradeAction.BUY_PUT
        return DailySignal(
            trade_date=snapshot.trade_date,
            responses=responses,
            consensus_direction=direction,
            consensus_confidence=confidence,
            trade_action=action,
            recommended_strike=_modal_strike(agreeing, atm),
            agreeing_models=agreeing_providers,
            dissenting_models=dissenting,
        )


def _direction_votes(
    valid: list[SignalResponse],
) -> dict[Direction, list[SignalResponse]]:
    """Group validated responses by their direction call."""
    votes: dict[Direction, list[SignalResponse]] = {}
    for r in valid:
        votes.setdefault(r.direction, []).append(r)
    return votes


def _modal_strike(agreeing: list[SignalResponse], atm: int) -> int:
    """Most common strike among agreeing models; ATM wins on a tie."""
    counts = Counter(r.recommended_strike for r in agreeing)
    top = max(counts.values())
    modal = {strike for strike, n in counts.items() if n == top}
    if atm in modal or len(modal) > 1:
        return atm
    return next(iter(modal))
