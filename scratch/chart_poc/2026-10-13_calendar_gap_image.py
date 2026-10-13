"""Scratch: annotate the calendar POC chart with what src/ lacks today.

Run: python scratch/chart_poc/2026-10-13_calendar_gap_image.py <poc_png> <out_png>
"""

from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt

BG, FG, GREEN, RED, AMBER = "#0d1117", "#e6edf3", "#2bb59a", "#f0605d", "#e3b341"

HAVE = [
    "IC renderer: dark theme, curve, fills, strike ticks, BE markers, spot, Now marker",
    "Stat header: P&L now, max profit/loss, R:R, margin, net credit, breakevens",
    "Telegram send_photo with caption; payoff registry and adapter plumbing",
    "Paper store: trades, entry prices, legs, margin snapshot",
]
MISSING = [
    (
        "1",
        "Pricer: src/pricing (Black-76 + IV solve). Blocked on greeks-bs-fallback GF-2/GF-3",
        RED,
    ),
    (
        "2",
        "Renderer seam: curve is hardcoded to intrinsic expiry_pnl_at; needs an optional curve arg",
        RED,
    ),
    (
        "3",
        "Calendar adapter: PayoffLeg has no expiry/IV; needs per-leg expiry, IV, forward, entry price",
        RED,
    ),
    ("4", "Header range rule: max loss and R:R depend on the sampling window", AMBER),
    ("5", "Tick label: CE and PE at the same strike show one label", AMBER),
    ("6", "Overlay story: T+0 line, +/-1/2 sigma bands, POP (also OI bars, per-leg table)", AMBER),
]


def badge(ax, x, y, n, color):
    ax.text(
        x,
        y,
        n,
        color="white",
        fontsize=13,
        fontweight="bold",
        ha="center",
        va="center",
        bbox={"boxstyle": "circle,pad=0.3", "fc": color, "ec": "white", "lw": 1.5},
    )


def main(poc: str, out: str) -> None:
    img = mpimg.imread(poc)
    h, w = img.shape[:2]
    fig = plt.figure(figsize=(12, 11.5), facecolor=BG)
    ax = fig.add_axes([0.04, 0.40, 0.92, 0.56])
    ax.imshow(img)
    ax.axis("off")
    for n, (x, y, c) in {
        "1": (655, 255, RED),
        "2": (480, 430, RED),
        "3": (330, 82, RED),
        "4": (400, 125, AMBER),
        "5": (655, 800, AMBER),
        "6": (835, 505, AMBER),
    }.items():
        badge(ax, x, y, n, c)
    xs = [240 + i * 8 for i in range(111)]
    ax.plot(
        xs,
        [580 - 55 * (1 - ((x - 690) / 450) ** 2) for x in xs],
        color="#58a6ff",
        ls="--",
        lw=2,
        alpha=0.9,
    )
    ax.text(870, 508, "T+0 line: not available", color="#58a6ff", fontsize=10, va="center")
    fig.text(
        0.04,
        0.975,
        "NIFTY calendar chart: what exists vs what is missing in src/",
        color=FG,
        fontsize=16,
        fontweight="bold",
        va="top",
    )

    fig.text(0.04, 0.375, "AVAILABLE IN IC TODAY", color=GREEN, fontsize=12, fontweight="bold")
    for i, t in enumerate(HAVE):
        fig.text(0.04, 0.345 - i * 0.04, "✓  " + t, color=FG, fontsize=10.5, va="top")
    fig.text(
        0.04,
        0.175,
        "NOT AVAILABLE (numbers match the badges on the chart)",
        color=RED,
        fontsize=12,
        fontweight="bold",
    )
    for i, (n, t, c) in enumerate(MISSING):
        y = 0.145 - i * 0.026
        fig.text(
            0.04,
            y,
            n,
            color="white",
            fontsize=10,
            fontweight="bold",
            ha="center",
            va="center",
            bbox={"boxstyle": "circle,pad=0.25", "fc": c, "ec": "none"},
        )
        fig.text(0.065, y, t, color=FG, fontsize=10.5, va="center")
    fig.text(
        0.96,
        0.012,
        "red = blocks a production chart, amber = polish or deferred",
        color="#8b949e",
        fontsize=9,
        ha="right",
    )
    fig.savefig(out, dpi=110, facecolor=BG)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
