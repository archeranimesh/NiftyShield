"""POC: how a nifty-calendar payoff chart forms using IC's renderer plus a scratch Black-76 pricer.

Real data: the 7 Oct 2026 9:53 exit (Sensibull Daily P&L) of the Oct monthly double calendar, 2 lots x 65.
Entry prices are reconstructed from exit LTP and booked leg P&L (assumes LTP ~ fill). No src/ edits:
the renderer's expiry_pnl_at is patched in this process only.

Run: python scratch/chart_poc/2026-10-13_calendar_payoff_poc.py <out_dir>
"""

from __future__ import annotations

import math
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import numpy as np

import src.notifications.payoff_chart as pc
from src.payoff.core import PayoffLeg, StrategyPayoff

QTY = 2 * 65
SPOT_EXIT = 22623.50
NOW = datetime(2026, 10, 7, 9, 53)
NEAR = datetime(2026, 10, 27, 15, 30)
FAR = datetime(2026, 11, 23, 15, 30)

# kind, strike, side (+1 long / -1 short), expiry label, exit LTP, booked leg P&L (rupees)
LEGS = [
    ("CE", 22600, -1, "near", 325.50, 18860),
    ("PE", 22600, -1, "near", 248.15, -2987),
    ("PE", 22200, +1, "far", 222.25, 3819),
    ("CE", 23000, +1, "far", 313.55, -14271),
]


def yrs(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / (365 * 86400)


def _n(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def b76(kind: str, f: float, k: float, t: float, vol: float) -> float:
    """Undiscounted Black-76 price."""
    if t <= 0 or vol <= 0:
        return max(f - k, 0.0) if kind == "CE" else max(k - f, 0.0)
    d1 = (math.log(f / k) + 0.5 * vol * vol * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    if kind == "CE":
        return f * _n(d1) - k * _n(d2)
    return k * _n(-d2) - f * _n(-d1)


def solve_iv(kind: str, f: float, k: float, t: float, price: float) -> float:
    lo, hi = 0.01, 2.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if b76(kind, f, k, t, mid) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


# Forward from put-call parity on the near 22600 pair; carry extrapolated to the far expiry.
t_near, t_far = yrs(NOW, NEAR), yrs(NOW, FAR)
f_near = 22600 + 325.50 - 248.15
carry = math.log(f_near / SPOT_EXIT) / t_near


def fwd(spot: float, t: float) -> float:
    return spot * math.exp(carry * t)


ivs, entries = {}, {}
for kind, k, _side, exp, ltp, _pnl in LEGS:
    t = t_near if exp == "near" else t_far
    ivs[(kind, k)] = solve_iv(kind, fwd(SPOT_EXIT, t), k, t, ltp)
# short: pnl = (entry - exit)*q -> entry = exit + pnl/q ; long: pnl = (exit - entry)*q -> entry = exit - pnl/q
for kind, k, side, _exp, ltp, pnl in LEGS:
    entries[(kind, k)] = ltp + pnl / QTY if side < 0 else ltp - pnl / QTY


def leg_value(kind: str, k: float, exp: str, spot: float, at: datetime) -> float:
    t = yrs(at, NEAR if exp == "near" else FAR)
    return b76(kind, fwd(spot, t), k, t, ivs[(kind, k)])


def pnl_signed(spot: float, at: datetime) -> float:
    """P&L in rupees: long gains when value rises, short gains when value falls."""
    return sum(
        side * QTY * (leg_value(kind, k, exp, spot, at) - entries[(kind, k)])
        for kind, k, side, exp, _l, _p in LEGS
    )


def expiry_curve(spot: float) -> float:
    return pnl_signed(spot, NEAR)


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    print("entries (reconstructed):", {k: round(v, 2) for k, v in entries.items()})
    print("ivs:", {k: round(v, 4) for k, v in ivs.items()}, f"carry={carry:.4f}")
    print(f"check T+0 at exit spot: {pnl_signed(SPOT_EXIT, NOW):.0f} (booked 5421)")
    xs = np.linspace(21800, 23400, 1601)
    ys = np.array([expiry_curve(x) for x in xs])
    peak = xs[ys.argmax()]
    be = [float(xs[i]) for i in range(len(xs) - 1) if ys[i] * ys[i + 1] < 0]
    print(f"expiry curve: max {ys.max():.0f} at {peak:.0f}, min {ys.min():.0f}, breakevens {be}")
    for label, spot, at, actual, sbull in [
        ("5 Oct", 22555.75, datetime(2026, 10, 5, 15, 30), 2473, 3195),
        ("6 Oct", 22776.10, datetime(2026, 10, 6, 15, 30), 4781, 4319),
    ]:
        print(
            f"{label}: model T+0 {pnl_signed(spot, at):.0f} | actual {actual} | Sensibull proj {sbull}"
        )
    print("Sensibull expiry max profit: 5 Oct 54,765 | 6 Oct 51,781; max loss -53,940 / -49,203")

    legs = tuple(
        PayoffLeg(
            kind=kd,
            strike=Decimal(k),
            qty=sd * QTY,
            entry_price=Decimal(str(round(entries[(kd, k)], 2))),
        )
        for kd, k, sd, _e, _l, _p in LEGS
    )
    payoff = StrategyPayoff(
        legs=legs,
        net_premium=-sum((leg.qty * leg.entry_price for leg in legs), Decimal(0)),
        max_profit=Decimal(str(round(ys.max(), 2))),
        max_loss=Decimal(str(round(ys.min(), 2))),
        breakevens=tuple(Decimal(str(round(b, 1))) for b in be),
        rr_ratio=Decimal(str(round(abs(ys.max() / ys.min()), 2))),
        key_spots=tuple(sorted(leg.strike for leg in legs)),
    )
    pc.expiry_pnl_at = lambda _p, s: Decimal(
        str(expiry_curve(float(s)))
    )  # POC patch, process-local
    png = pc.render_payoff_png(
        payoff,
        spot=Decimal(str(SPOT_EXIT)),
        current_pnl=Decimal(str(round(pnl_signed(SPOT_EXIT, NOW)))),
        dte=20,
        margin=Decimal(174000),
        title="NIFTY Monthly Calendar (POC)",
        subtitle="27 Oct / 23 Nov",
    )
    (out / "calendar_poc_ic_renderer.png").write_bytes(png)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5))
    t0 = np.array([pnl_signed(x, NOW) for x in xs])
    ax.plot(xs, ys, color="green", label="near expiry (27 Oct), far legs by Black-76")
    ax.plot(xs, t0, color="blue", ls="--", label="T+0 (7 Oct 9:53)")
    ax.axhline(0, color="grey", lw=0.6)
    ax.axvline(SPOT_EXIT, color="k", lw=0.6)
    ax.set_title("Calendar POC: what the overlay adds (T+0)")
    ax.legend()
    fig.savefig(out / "calendar_poc_with_t0.png", dpi=120)
    print("wrote", out)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
