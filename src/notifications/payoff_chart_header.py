import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matplotlib.figure import Figure

    from .payoff_chart_theme import ChartTheme

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
    current_pnl: Decimal | None = None,
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


@dataclass(frozen=True)
class Slot:
    index: int
    left: float
    width: float


@dataclass(frozen=True)
class HeaderLayout:
    rows: list[list[Slot]]
    scale: float


def pack_header(
    widths: Sequence[float], avail: float, *, min_gap: float = 0.14, floor: float = 0.8
) -> HeaderLayout:
    if not widths:
        return HeaderLayout(rows=[], scale=1.0)

    def calc_scale(w_list):
        if sum(w_list) == 0:
            return 1.0
        return min(1.0, (avail - min_gap * (len(w_list) - 1)) / sum(w_list))

    def build_row(w_list, scale, index_offset):
        if len(w_list) == 1:
            return [Slot(index_offset, 0.0, w_list[0])]

        total_scaled = sum(w * scale for w in w_list)
        gap = (avail - total_scaled) / (len(w_list) - 1)
        slots = []
        curr = 0.0
        for i, w in enumerate(w_list):
            slots.append(Slot(index_offset + i, curr, w))
            curr += (w * scale) + gap
        return slots

    scale = calc_scale(widths)
    if scale >= floor:
        return HeaderLayout(rows=[build_row(widths, scale, 0)], scale=scale)

    n1 = math.ceil(len(widths) / 2)
    w1 = widths[:n1]
    w2 = widths[n1:]

    final_scale = min(calc_scale(w1), calc_scale(w2))
    row1 = build_row(w1, final_scale, 0)
    row2 = build_row(w2, final_scale, n1)

    return HeaderLayout(rows=[row1, row2], scale=final_scale)


MARGIN_X = 0.03
AVAIL_WIDTH_FRAC = 0.94
TITLE_SIZE = 16
SUBTITLE_SIZE = 10
LABEL_SIZE = 8.5
VALUE_SIZE = 12
SUB_SIZE = 9

TITLE_Y = 0.94
SUBTITLE_Y = 0.89

CELL_START_Y = 0.82
ROW_PITCH = 0.12
LABEL_DY = 0.0
VALUE_DY = -0.035
SUB_DY = -0.07


def get_tone_color(tone: Tone, theme: "ChartTheme") -> str:
    if tone == Tone.POSITIVE:
        return theme.green
    elif tone == Tone.NEGATIVE:
        return theme.red
    elif tone == Tone.MUTED:
        return theme.muted
    return theme.ink


def draw_header(
    fig: "Figure",
    title: str,
    subtitle: str,
    cells: list[HeaderCell],
    theme: "ChartTheme",
    family: str,
) -> int:
    fig.text(
        MARGIN_X,
        TITLE_Y,
        title,
        fontsize=TITLE_SIZE,
        fontweight="bold",
        color=theme.ink,
        fontfamily=family,
        va="baseline",
        ha="left",
    )
    if subtitle:
        fig.text(
            MARGIN_X,
            SUBTITLE_Y,
            subtitle,
            fontsize=SUBTITLE_SIZE,
            color=theme.muted,
            fontfamily=family,
            va="baseline",
            ha="left",
        )

    if not cells:
        return 0

    renderer = fig.canvas.get_renderer()

    widths = []
    for cell in cells:
        t1 = fig.text(0, 0, cell.label, fontsize=LABEL_SIZE, fontfamily=family)
        t2 = fig.text(0, 0, cell.value, fontsize=VALUE_SIZE, fontweight="bold", fontfamily=family)
        t3 = fig.text(0, 0, cell.sub, fontsize=SUB_SIZE, fontfamily=family)

        w1 = t1.get_window_extent(renderer).width / fig.dpi
        w2 = t2.get_window_extent(renderer).width / fig.dpi
        w3 = t3.get_window_extent(renderer).width / fig.dpi if cell.sub else 0

        widths.append(max(w1, w2, w3))

        t1.remove()
        t2.remove()
        t3.remove()

    avail_inches = fig.get_figwidth() * AVAIL_WIDTH_FRAC
    layout = pack_header(widths, avail_inches)

    fig_width = fig.get_figwidth()

    for row_idx, row in enumerate(layout.rows):
        y_base = CELL_START_Y - row_idx * ROW_PITCH

        for slot in row:
            cell = cells[slot.index]
            x_center = MARGIN_X + (slot.left + (slot.width * layout.scale) / 2) / fig_width

            fig.text(
                x_center,
                y_base + LABEL_DY,
                cell.label,
                fontsize=LABEL_SIZE * layout.scale,
                color=theme.muted,
                fontfamily=family,
                ha="center",
                va="baseline",
            )
            fig.text(
                x_center,
                y_base + VALUE_DY,
                cell.value,
                fontsize=VALUE_SIZE * layout.scale,
                fontweight="bold",
                color=get_tone_color(cell.value_tone, theme),
                fontfamily=family,
                ha="center",
                va="baseline",
            )
            if cell.sub:
                fig.text(
                    x_center,
                    y_base + SUB_DY,
                    cell.sub,
                    fontsize=SUB_SIZE * layout.scale,
                    color=get_tone_color(cell.sub_tone, theme),
                    fontfamily=family,
                    ha="center",
                    va="baseline",
                )

    return len(layout.rows)
