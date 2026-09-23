"""Pure MVP pick tracking logic: price-breach detection."""

from dataclasses import dataclass
from decimal import Decimal

from src.mvp.models import Pick, PickStatus


@dataclass(frozen=True)
class MVPEvent:
    """A target or stop-loss breach detected for a pick."""

    pick_id: str
    symbol: str
    event_type: PickStatus
    trigger_price: Decimal
    entry_price: Decimal | None


def check_prices(
    picks: list[Pick],
    ltp_map: dict[str, Decimal],
) -> list[MVPEvent]:
    """Detect target/stop-loss breaches for open picks.

    Args:
        picks: Picks to evaluate.
        ltp_map: Last traded price keyed by instrument_key.

    Returns:
        MVPEvent list, one per breach. Empty if none.
    """
    events: list[MVPEvent] = []
    for pick in picks:
        if pick.status != PickStatus.OPEN:
            continue
        if pick.instrument_key is None or pick.instrument_key not in ltp_map:
            continue
        ltp = ltp_map[pick.instrument_key]

        if pick.target_price is not None and ltp >= pick.target_price:
            events.append(
                MVPEvent(
                    pick_id=pick.pick_id,
                    symbol=pick.symbol,
                    event_type=PickStatus.TARGET_HIT,
                    trigger_price=ltp,
                    entry_price=pick.entry_price,
                )
            )
        elif pick.stop_loss is not None and ltp <= pick.stop_loss:
            events.append(
                MVPEvent(
                    pick_id=pick.pick_id,
                    symbol=pick.symbol,
                    event_type=PickStatus.SL_HIT,
                    trigger_price=ltp,
                    entry_price=pick.entry_price,
                )
            )

    return events
