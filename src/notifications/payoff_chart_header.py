from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from src.notifications.formatting import format_money_whole, format_pct_signed, format_strike
from src.payoff.core import StrategyPayoff


class Tone(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    MUTED = "MUTED"


@dataclass(frozen=True)
class HeaderCell:
    label: str
    value: str
    value_tone: Tone
    sub: str = ""
    sub_tone: Tone = Tone.MUTED


def build_header_cells(
    payoff: StrategyPayoff,
    *,
    spot: Decimal | None = None,
    margin: Decimal | None = None,
    current_pnl: Decimal | None = None
) -> list[HeaderCell]:
    cells = []

    # P&L NOW
    if current_pnl is not None:
        rounded_pnl = current_pnl.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        tone = Tone.NEUTRAL
        if rounded_pnl > 0:
            tone = Tone.POSITIVE
        elif rounded_pnl < 0:
            tone = Tone.NEGATIVE

        sub = ""
        if margin:
            sub = format_pct_signed(float(current_pnl / margin * 100))

        cells.append(
            HeaderCell(
                label="P&L NOW",
                value=format_money_whole(current_pnl, signed=True),
                value_tone=tone,
                sub=sub,
            )
        )

    # MAX PROFIT
    if payoff.max_profit is None:
        cells.append(HeaderCell("MAX PROFIT", "Unlimited", Tone.NEUTRAL))
    else:
        sub = ""
        if margin:
            sub = format_pct_signed(float(payoff.max_profit / margin * 100))
        cells.append(
            HeaderCell(
                label="MAX PROFIT",
                value=format_money_whole(payoff.max_profit),
                value_tone=Tone.POSITIVE,
                sub=sub,
            )
        )

    # MAX LOSS / MIN PROFIT
    if payoff.max_loss is None:
        cells.append(HeaderCell("MAX LOSS", "Unlimited", Tone.NEGATIVE))
    elif payoff.max_loss >= 0:
        cells.append(
            HeaderCell(
                label="MIN PROFIT",
                value=format_money_whole(payoff.max_loss),
                value_tone=Tone.POSITIVE,
            )
        )
    else:
        sub = ""
        if margin:
            sub = format_pct_signed(float(payoff.max_loss / margin * 100))
        cells.append(
            HeaderCell(
                label="MAX LOSS",
                value=format_money_whole(payoff.max_loss),
                value_tone=Tone.NEGATIVE,
                sub=sub,
            )
        )

    # RISK:REWARD
    if payoff.rr_ratio and payoff.rr_ratio != 0:
        val = 1 / float(payoff.rr_ratio)
        cells.append(
            HeaderCell(
                label="RISK:REWARD",
                value=f"{val:.1f} : 1",
                value_tone=Tone.NEUTRAL,
            )
        )

    # EST. MARGIN
    if margin:
        cells.append(
            HeaderCell(
                label="EST. MARGIN",
                value=format_money_whole(margin),
                value_tone=Tone.NEUTRAL,
            )
        )

    # NET CREDIT / NET DEBIT
    is_credit = payoff.net_premium >= 0
    cells.append(
        HeaderCell(
            label="NET CREDIT" if is_credit else "NET DEBIT",
            value=format_money_whole(abs(payoff.net_premium)),
            value_tone=Tone.NEUTRAL,
        )
    )

    # BREAKEVENS
    if payoff.breakevens:
        val_str = " – ".join(format_strike(int(round(b))) for b in payoff.breakevens)

        sub = ""
        if spot:
            subs = []
            for b in payoff.breakevens:
                dist = float((b - spot) / spot * 100)
                subs.append(format_pct_signed(dist))
            sub = " / ".join(subs)

        cells.append(
            HeaderCell(
                label="BREAKEVENS",
                value=val_str,
                value_tone=Tone.NEUTRAL,
                sub=sub,
            )
        )

    return cells
