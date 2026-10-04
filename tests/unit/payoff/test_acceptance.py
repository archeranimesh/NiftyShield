"""Acceptance matrix: hand-computed fixtures for any-strategy payoff math."""

from decimal import Decimal as D

from src.payoff.core import PayoffLeg, compute_payoff, expiry_pnl_at

Q = 65


def _check(legs, max_profit, max_loss, breakevens, spot_pnls):
    p = compute_payoff(legs)
    assert p.max_profit == D(max_profit)
    assert p.max_loss == D(max_loss)
    assert p.breakevens == tuple(D(b) for b in breakevens)
    for spot, pnl in spot_pnls.items():
        assert expiry_pnl_at(p, D(spot)) == D(pnl), spot


_SYM_IC = [
    PayoffLeg("PE", D("22800"), Q, D("20")),
    PayoffLeg("PE", D("23000"), -Q, D("80")),
    PayoffLeg("CE", D("23500"), -Q, D("70")),
    PayoffLeg("CE", D("23700"), Q, D("10")),
]


# Iron Condor (symmetric). Credit/unit = (80-20) + (70-10) = 120
# -> 7800 at qty 65.
# Max loss = (wing 200 - 120) * 65 = 5200. Breakevens 23000-120, 23500+120.
# At 22900: short 23000 PE costs 100-80=20/unit (-1300),
# long 22800 PE -20 (-1300),
# short CE +70 (+4550), long CE -10 (-650) -> +1300.
def test_acceptance_iron_condor_symmetric_rr_and_premium():
    p = compute_payoff(_SYM_IC)
    assert p.rr_ratio == D("1.5")
    assert p.net_premium == D("7800")


def test_acceptance_iron_condor_symmetric():
    _check(
        _SYM_IC, "7800", "-5200", ["22880", "23620"],
        {"23250": "7800", "22880": "0", "22900": "1300", "22000": "-5200",
         "24000": "-5200"},
    )  # fmt: skip


# Iron Condor (V2-style, 500-wide wings). Credit/unit = (80-10) + (70-5) = 135.
# Max profit 135*65 = 8775; max loss = (500-135)*65 = 23725.
# Breakevens 23000-135 = 22865 and 23500+135 = 23635.
def test_acceptance_iron_condor_wide_wings():
    legs = [
        PayoffLeg("PE", D("22500"), Q, D("10")),
        PayoffLeg("PE", D("23000"), -Q, D("80")),
        PayoffLeg("CE", D("23500"), -Q, D("70")),
        PayoffLeg("CE", D("24000"), Q, D("5")),
    ]
    _check(
        legs, "8775", "-23725", ["22865", "23635"],
        {"23250": "8775", "22865": "0", "22000": "-23725", "25000": "-23725"},
    )  # fmt: skip


# Cash-secured put: short 23000 PE @100, qty 65. Profit = 100*65 = 6500.
# Loss bounded by spot -> 0: -(23000-100)*65 = -1,488,500. Breakeven 23000-100.
# At 22000: -(1000-100)*65 = -58,500.
def test_acceptance_cash_secured_put():
    legs = [PayoffLeg("PE", D("23000"), -Q, D("100"))]
    _check(
        legs, "6500", "-1488500", ["22900"],
        {"23000": "6500", "24000": "6500", "22900": "0", "22000": "-58500"},
    )  # fmt: skip


# Covered call: long 65 EQ @23000, short 23500 CE @100.
# Max profit = (500 + 100)*65 = 39,000 (any spot >= 23500).
# Max loss at 0: -23000*65 + 100*65 = -1,488,500. Breakeven 23000-100.
# At 23200: 200*65 + 6500 = 19,500.
def test_acceptance_covered_call():
    legs = [
        PayoffLeg("EQ", None, Q, D("23000")),
        PayoffLeg("CE", D("23500"), -Q, D("100")),
    ]
    _check(
        legs, "39000", "-1488500", ["22900"],
        {"23500": "39000", "24000": "39000", "23200": "19500", "22900": "0"},
    )  # fmt: skip


# Collar: long 65 EQ @23000, long 22500 PE @60, short 23500 CE @70.
# Floor (S <= 22500): -500*65 - 60*65 + 70*65 = -31,850.
# Cap (S >= 23500): +500*65 - 60*65 + 70*65 = 33,150.
# Breakeven: 22500 + 31850/65 = 22990 (EQ -650, PE -3900, CE +4550 = 0).
def test_acceptance_collar_mixed_legs():
    legs = [
        PayoffLeg("EQ", None, Q, D("23000")),
        PayoffLeg("PE", D("22500"), Q, D("60")),
        PayoffLeg("CE", D("23500"), -Q, D("70")),
    ]
    _check(
        legs, "33150", "-31850", ["22990"],
        {"22000": "-31850", "22500": "-31850", "22990": "0", "24000": "33150"},
    )  # fmt: skip
