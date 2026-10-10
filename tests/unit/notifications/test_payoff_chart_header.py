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
