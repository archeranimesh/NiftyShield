from decimal import Decimal
from src.notifications.payoff_chart_header import Tone, HeaderCell, build_header_cells
from src.payoff.core import StrategyPayoff


def test_full_ic_cells_in_order():
    payoff = StrategyPayoff(
        legs=(),
        net_premium=Decimal("9607"),
        max_profit=Decimal("9607"),
        max_loss=Decimal("-48893"),
        breakevens=(Decimal("21752.4"), Decimal("23147.6")),
        rr_ratio=Decimal("9607") / Decimal("48893"),
        key_spots=(),
    )
    spot = Decimal("22348")
    margin = Decimal("86937")
    pnl = Decimal("3200")

    cells = build_header_cells(payoff, spot=spot, margin=margin, current_pnl=pnl)

    assert [c.label for c in cells] == [
        "P&L NOW",
        "MAX PROFIT",
        "MAX LOSS",
        "RISK:REWARD",
        "EST. MARGIN",
        "NET CREDIT",
        "BREAKEVENS",
    ]

    # P&L NOW
    assert cells[0].value == "+₹3,200"
    assert cells[0].value_tone == Tone.POSITIVE
    assert cells[0].sub == "+3.7%"

    # MAX PROFIT
    assert cells[1].value == "₹9,607"
    assert cells[1].value_tone == Tone.POSITIVE
    assert cells[1].sub == "+11.1%"

    # MAX LOSS
    assert cells[2].value == "-₹48,893"
    assert cells[2].value_tone == Tone.NEGATIVE
    assert cells[2].sub == "-56.2%"

    # RISK:REWARD
    assert cells[3].value == "5.1 : 1"

    # EST. MARGIN
    assert cells[4].value == "₹86,937"

    # NET CREDIT
    assert cells[5].value == "₹9,607"

    # BREAKEVENS
    assert cells[6].value == "21752 – 23148"
    assert cells[6].sub == "-2.7% / +3.6%"


def test_cells_drop_when_input_missing():
    payoff = StrategyPayoff(
        legs=(),
        net_premium=Decimal("-5000"),
        max_profit=Decimal("5000"),
        max_loss=Decimal("-5000"),
        breakevens=(Decimal("22000"),),
        rr_ratio=Decimal("1"),
        key_spots=(),
    )
    cells = build_header_cells(payoff)

    labels = [c.label for c in cells]
    assert "P&L NOW" not in labels
    assert "EST. MARGIN" not in labels

    bp_cell = next(c for c in cells if c.label == "BREAKEVENS")
    assert bp_cell.sub == ""

    mp_cell = next(c for c in cells if c.label == "MAX PROFIT")
    assert mp_cell.sub == ""

    ml_cell = next(c for c in cells if c.label == "MAX LOSS")
    assert ml_cell.sub == ""


def test_unbounded_naked_call():
    payoff = StrategyPayoff(
        legs=(),
        net_premium=Decimal("5000"),
        max_profit=Decimal("5000"),
        max_loss=None,
        breakevens=(Decimal("22000"),),
        rr_ratio=None,
        key_spots=(),
    )
    cells = build_header_cells(payoff)

    ml_cell = next(c for c in cells if c.label == "MAX LOSS")
    assert ml_cell.value == "Unlimited"
    assert ml_cell.value_tone == Tone.NEGATIVE

    assert "RISK:REWARD" not in [c.label for c in cells]


def test_guaranteed_profit_is_min_profit():
    payoff = StrategyPayoff(
        legs=(),
        net_premium=Decimal("5000"),
        max_profit=Decimal("15000"),
        max_loss=Decimal("2000"),
        breakevens=(),
        rr_ratio=None,
        key_spots=(),
    )
    cells = build_header_cells(payoff)

    labels = [c.label for c in cells]
    assert "MAX LOSS" not in labels
    assert "MIN PROFIT" in labels

    mp_cell = next(c for c in cells if c.label == "MIN PROFIT")
    assert mp_cell.value == "₹2,000"
    assert mp_cell.value_tone == Tone.POSITIVE


def test_net_debit_label():
    payoff = StrategyPayoff(
        legs=(),
        net_premium=Decimal("-3000"),
        max_profit=Decimal("10000"),
        max_loss=Decimal("-3000"),
        breakevens=(),
        rr_ratio=None,
        key_spots=(),
    )
    cells = build_header_cells(payoff)

    nd_cell = next(c for c in cells if c.label == "NET DEBIT")
    assert nd_cell.value == "₹3,000"


def test_zero_margin_gives_no_percent():
    payoff = StrategyPayoff(
        legs=(),
        net_premium=Decimal("5000"),
        max_profit=Decimal("5000"),
        max_loss=Decimal("-5000"),
        breakevens=(),
        rr_ratio=None,
        key_spots=(),
    )
    cells = build_header_cells(payoff, margin=Decimal("0"))

    mp_cell = next(c for c in cells if c.label == "MAX PROFIT")
    assert mp_cell.sub == ""


def test_pnl_zero_is_neutral():
    payoff = StrategyPayoff(
        legs=(),
        net_premium=Decimal("5000"),
        max_profit=Decimal("5000"),
        max_loss=Decimal("-5000"),
        breakevens=(),
        rr_ratio=None,
        key_spots=(),
    )
    cells = build_header_cells(payoff, current_pnl=Decimal("0.4"))
    pnl_cell = next(c for c in cells if c.label == "P&L NOW")
    assert pnl_cell.value_tone == Tone.NEUTRAL

import math
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from src.notifications.payoff_chart_header import pack_header, draw_header

class MockTheme:
    bg = "#0e1117"
    ink = "#e5e7eb"
    muted = "#9ca3af"
    faint = "#1f2937"
    green = "#26b3a0"
    red = "#ef5350"
    fill_alpha_green = 0.22
    fill_alpha_red = 0.14

def test_pack_one_row_spreads_gaps_equally():
    widths = [0.8, 0.7, 0.9, 0.6, 0.8, 0.7, 0.7] # 7 widths summing to 5.2
    avail = 6.58
    layout = pack_header(widths, avail)
    assert len(layout.rows) == 1
    assert layout.scale == 1.0
    row = layout.rows[0]
    assert len(row) == 7
    # Gaps equal and spread to fill avail
    # min_gap = 0.14. total_w = 5.2. remaining = 1.38. gap = 0.23
    assert math.isclose(row[1].left - (row[0].left + row[0].width), 0.23)
    assert math.isclose(row[-1].left + row[-1].width, 6.58)

def test_pack_shrinks_before_wrapping():
    # 7 widths summing to 6.2, avail = 6.58
    # min_gap = 0.14 -> 6 * 0.14 = 0.84
    # required = 6.2 + 0.84 = 7.04 > 6.58
    # scale = (6.58 - 0.84) / 6.2 = 5.74 / 6.2 = 0.9258 >= 0.8
    widths = [0.9] * 6 + [0.8]
    layout = pack_header(widths, 6.58)
    assert len(layout.rows) == 1
    assert 0.8 <= layout.scale < 1.0
    row = layout.rows[0]
    gap = row[1].left - (row[0].left + row[0].width * layout.scale)
    assert math.isclose(gap, 0.14)

def test_pack_wraps_below_floor():
    # sum = 8.0, avail = 6.58. 
    # scale = (6.58 - 0.84) / 8.0 = 0.7175 < 0.8
    widths = [1.2, 1.1, 1.2, 1.1, 1.2, 1.1, 1.1]
    layout = pack_header(widths, 6.58)
    assert len(layout.rows) == 2
    assert len(layout.rows[0]) == 4
    assert len(layout.rows[1]) == 3

def test_pack_edge_cases():
    l1 = pack_header([], 6.58)
    assert len(l1.rows) == 0

    l2 = pack_header([2.0], 6.58)
    assert len(l2.rows) == 1
    assert l2.rows[0][0].left == 0.0

def test_draw_header_centres_each_cell():
    fig = Figure(figsize=(7, 4.9))
    FigureCanvasAgg(fig)
    cells = [
        HeaderCell("LABEL1", "VALUE1", Tone.POSITIVE, "SUB1", Tone.MUTED),
        HeaderCell("L2", "V2", Tone.NEGATIVE)
    ]
    
    rows = draw_header(fig, "Title", "Subtitle", cells, MockTheme(), "sans-serif")
    assert rows == 1
    
    texts = fig.texts
    
    # Title and subtitle
    assert texts[0].get_text() == "Title"
    assert texts[1].get_text() == "Subtitle"
    
    # Cell 0: Label, Value, Sub
    cell0_label = texts[2]
    cell0_value = texts[3]
    cell0_sub = texts[4]
    
    # Cell 1: Label, Value (no sub)
    cell1_label = texts[5]
    cell1_value = texts[6]
    
    assert cell0_label.get_ha() == "center"
    assert cell0_value.get_ha() == "center"
    assert cell0_sub.get_ha() == "center"
    
    assert cell1_label.get_ha() == "center"
    assert cell1_value.get_ha() == "center"
    
    # Check they share the same X
    assert cell0_label.get_position()[0] == cell0_value.get_position()[0] == cell0_sub.get_position()[0]
    assert cell1_label.get_position()[0] == cell1_value.get_position()[0]
    
    # Check X increases
    assert cell0_label.get_position()[0] < cell1_label.get_position()[0]
    
    # Check within (0, 1)
    assert 0 < cell0_label.get_position()[0] < 1
    assert 0 < cell1_label.get_position()[0] < 1

def test_draw_header_returns_row_count():
    fig = Figure(figsize=(7, 4.9))
    FigureCanvasAgg(fig)
    cells = [
        HeaderCell("LABEL1", "VALUE1" * 10, Tone.POSITIVE),
        HeaderCell("LABEL2", "VALUE2" * 10, Tone.NEGATIVE),
        HeaderCell("LABEL3", "VALUE3" * 10, Tone.NEUTRAL)
    ]
    # Absurdly wide values should force wrapping
    rows = draw_header(fig, "Title", "", cells, MockTheme(), "sans-serif")
    assert rows == 2
