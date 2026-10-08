"""POC: polished payoff chart (Roboto, light/dark themes, title+subtitle header, direct labels).

Run (works from any cwd; fonts optional, falls back to DejaVu Sans):
    python scratch/telegram_formats/2026-10-08_payoff_chart_polish_poc.py [--fonts DIR] [--out DIR]

Renders the production chart ("before") plus the POC in light and dark, with and without a
"P&L now" marker, for the IC in the user's screenshot (qty 65, 21000/21900/23000/23500, spot 22348).
"""

import argparse
import io
import sys
import tempfile
from dataclasses import dataclass
from decimal import Decimal as D
from pathlib import Path

import numpy as np
from matplotlib import font_manager
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, so `src` imports work

from src.notifications.payoff_chart import _label, render_payoff_png
from src.payoff.core import PayoffLeg, StrategyPayoff, compute_payoff, expiry_pnl_at


@dataclass(frozen=True)
class Theme:
    """Palette for one chart theme."""

    bg: str
    ink: str
    muted: str
    faint: str
    green: str
    red: str
    fill_alpha_green: float
    fill_alpha_red: float


LIGHT = Theme("white", "#1f2933", "#7b8794", "#e4e7eb", "#2e8b57", "#c0392b", 0.18, 0.12)
DARK = Theme("#0e1117", "#e5e7eb", "#9ca3af", "#1f2937", "#26b3a0", "#ef5350", 0.22, 0.14)
# warm off-white, earthy muted tones: easy on the eyes in a light Telegram chat
PAPER = Theme("#faf6ee", "#2b2a28", "#8a8274", "#e6dfd0", "#3f7d4e", "#b5473a", 0.20, 0.13)
# navy dark with brighter green / coral: more colour than DARK, less stark than near-black
MIDNIGHT = Theme("#0b1530", "#e8ecf8", "#8c9bc2", "#1c2a52", "#3ddc97", "#ff6b6b", 0.20, 0.14)
# colour-blind safe (blue profit / orange loss) on slate: red-green confusion cannot hide the sign
CB_SLATE = Theme("#1b2230", "#eef1f6", "#9aa5b8", "#2a3347", "#4da3ff", "#ff9f43", 0.22, 0.16)
THEMES = {"light": LIGHT, "dark": DARK, "paper": PAPER, "midnight": MIDNIGHT, "cb_slate": CB_SLATE}


def load_roboto(font_dir: Path | None) -> str:
    """Register Roboto Regular/Bold from ``font_dir``; fall back to DejaVu Sans on any failure."""
    if font_dir is None:
        return "DejaVu Sans"
    try:
        for name in ("Roboto-Regular.ttf", "Roboto-Bold.ttf"):
            font_manager.fontManager.addfont(str(font_dir / name))
        return "Roboto"
    except Exception as exc:  # POC: production must log a warning and fall back, never raise
        print(f"font load failed ({exc}); falling back to DejaVu Sans")
        return "DejaVu Sans"


def demo_payoff() -> StrategyPayoff:
    """IC matching the screenshot: put wing 900, call wing 500, net credit ~Rs 9,608."""
    q = 65
    return compute_payoff(
        [
            PayoffLeg("PE", D(21000), q, D("20.0"), "long_put"),
            PayoffLeg("PE", D(21900), -q, D("100.0"), "short_put"),
            PayoffLeg("CE", D(23000), -q, D("95.8"), "short_call"),
            PayoffLeg("CE", D(23500), q, D("28.0"), "long_call"),
        ]
    )


def rupees(value: D, *, signed: bool = False) -> str:
    """Whole-rupee, comma-thousands amount: 9607 -> ₹9,607; -48893 -> -₹48,893."""
    sign = "-" if value < 0 else ("+" if signed and value > 0 else "")
    return f"{sign}₹{abs(int(value.to_integral_value())):,}"


def sample_xs(payoff: StrategyPayoff, lo: float, hi: float, n: int = 240) -> np.ndarray:
    """Grid plus every strike and breakeven, so kinks are sharp and zero crossings exact."""
    extra = [float(k) for k in (*payoff.key_spots, *payoff.breakevens)]
    return np.unique(np.concatenate([np.linspace(lo, hi, n), extra]))


def x_range(payoff: StrategyPayoff, spot: D) -> tuple[float, float]:
    """Key spots padded by 0.4x span (production uses 1.5x), always containing spot."""
    pts = [float(k) for k in payoff.key_spots]
    lo, hi = min(pts), max(pts)
    pad = 0.4 * (hi - lo)
    lo, hi = min(lo, float(spot)), max(hi, float(spot))
    return max(lo - pad, 0.0), hi + pad


Cell = tuple[str, str, str, str, str]  # label, value, value colour, sub-line, sub colour


def _pct(value: D, margin: D | None) -> str:
    """Signed % of margin, or '' when margin is unknown (cell then has no sub-line)."""
    if margin is None or margin == 0:
        return ""
    return f"{value / margin * 100:+.1f}%"


def stat_cells(
    payoff: StrategyPayoff, th: Theme, spot: D, margin: D | None, current_pnl: D | None
) -> list[Cell]:
    """Header cells in reading order; each is omitted when its input is missing."""
    sign = lambda v: th.green if v >= 0 else th.red  # noqa: E731
    cells: list[Cell] = []
    if current_pnl is not None:
        cells.append(
            (
                "P&L NOW",
                rupees(current_pnl, signed=True),
                sign(current_pnl),
                _pct(current_pnl, margin),
                sign(current_pnl),
            )
        )
    cells.append(
        (
            "MAX PROFIT",
            rupees(payoff.max_profit),
            th.green,
            _pct(payoff.max_profit, margin),
            th.green,
        )
    )
    cells.append(
        ("MAX LOSS", rupees(payoff.max_loss), th.red, _pct(payoff.max_loss, margin), th.red)
    )
    cells.append(("RISK:REWARD", f"{1 / payoff.rr_ratio:.1f} : 1", th.ink, "", th.muted))
    if margin is not None:
        cells.append(("EST. MARGIN", rupees(margin), th.ink, "", th.muted))
    word = "NET CREDIT" if payoff.net_premium >= 0 else "NET DEBIT"
    cells.append((word, rupees(abs(payoff.net_premium)), th.ink, "", th.muted))
    be = " – ".join(f"{int(b.to_integral_value())}" for b in payoff.breakevens)
    dist = " / ".join(f"{float((b - spot) / spot * 100):+.1f}%" for b in payoff.breakevens)
    cells.append(("BREAKEVENS", be, th.ink, dist, th.muted))
    return cells


def draw_header(
    fig: Figure, title: str, subtitle: str, cells: list[Cell], th: Theme, fam: str
) -> None:
    """Title, subtitle, then ALL cells in one row, each as wide as its content (space-between).

    Widths are measured with the Agg renderer; if the row would overflow, every font in it is
    scaled down uniformly (down to a floor) instead of wrapping to a second row.
    """
    fig.text(0.03, 0.972, title, fontsize=16, weight="bold", color=th.ink, family=fam, va="top")
    fig.text(0.03, 0.925, subtitle, fontsize=10, color=th.muted, family=fam, va="top")
    sizes = (8.5, 12.0, 9.0)  # label, value, sub
    top, renderer = 0.870, fig.canvas.get_renderer()
    made = []
    for label, value, colour, sub, sub_colour in cells:
        t_l = fig.text(
            0, top, label, fontsize=sizes[0], color=th.muted, family=fam, va="top", ha="center"
        )
        t_v = fig.text(
            0,
            top - 0.030,
            value,
            fontsize=sizes[1],
            color=colour,
            family=fam,
            weight="bold",
            va="top",
            ha="center",
        )
        t_s = fig.text(
            0,
            top - 0.072,
            sub,
            fontsize=sizes[2],
            color=sub_colour,
            family=fam,
            va="top",
            ha="center",
        )
        made.append((t_l, t_v, t_s))
    widths = [max(t.get_window_extent(renderer).width for t in trio) / fig.dpi for trio in made]
    avail, min_gap = fig.get_figwidth() * 0.94, 0.14
    scale = min(1.0, (avail - min_gap * (len(cells) - 1)) / sum(widths))
    scale = max(scale, 0.8)  # floor: below this the header is unreadable on a phone
    for trio in made:
        for t, size in zip(trio, sizes, strict=True):
            t.set_fontsize(size * scale)
    widths = [w * scale for w in widths]
    gap = max((avail - sum(widths)) / (len(cells) - 1), 0.0)
    x = 0.03 * fig.get_figwidth()
    for trio, w in zip(made, widths, strict=True):
        for t in trio:
            t.set_x((x + w / 2) / fig.get_figwidth())  # centre of the cell
        x += w + gap
    print(f"header: scale={scale:.2f} gap={gap:.2f}in widths={[round(w, 2) for w in widths]}")


def style_axes(ax: Axes, th: Theme, fam: str) -> None:
    """Quiet chrome: no top/right spines, muted axes, light horizontal grid, ₹k ticks."""
    ax.set_facecolor(th.bg)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(th.faint)
    ax.tick_params(colors=th.muted, labelsize=9.5, length=0)
    ax.grid(axis="y", color=th.faint, lw=0.6)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(
        FuncFormatter(
            lambda v, _: "₹0" if v == 0 else f"{'-' if v < 0 else ''}₹{abs(v) / 1000:.0f}k"
        )
    )
    for lab in ax.get_yticklabels():
        lab.set_family(fam)


def strike_ticks(ax: Axes, payoff: StrategyPayoff, span: float, th: Theme, fam: str) -> None:
    """x ticks at the strikes ('21900 PE / SELL'); a tick too near its neighbour drops a row."""
    legs = sorted((lg for lg in payoff.legs if lg.strike is not None), key=lambda lg: lg.strike)
    labels, lowered = [], False
    for i, lg in enumerate(legs):
        crowded = i > 0 and float(lg.strike - legs[i - 1].strike) < 0.14 * span
        lowered = crowded and not lowered
        side = "SELL" if lg.qty < 0 else "BUY"
        labels.append(("\n" if lowered else "") + f"{_label(lg.strike)} {lg.kind}\n{side}")
    ax.set_xticks([float(lg.strike) for lg in legs])
    ax.set_xticklabels(labels, family=fam)
    for tick, lg in zip(ax.get_xticklabels(), legs, strict=True):
        short = lg.qty < 0
        tick.set_color(th.ink if short else th.muted)
        tick.set_fontweight("bold" if short else "normal")
        ax.axvline(float(lg.strike), ls=":", lw=0.8, color=th.ink if short else th.faint, zorder=1)


def draw_breakevens(ax: Axes, payoff: StrategyPayoff, spot: D, th: Theme, fam: str) -> None:
    """Open dot on the zero line, value + % distance beside it, outside the profit tent."""
    for be in payoff.breakevens:
        left = be < spot
        text = f"BE {int(be.to_integral_value())}"
        ax.annotate(
            text,
            (float(be), 0),
            xytext=(-7 if left else 7, 5),
            textcoords="offset points",
            ha="right" if left else "left",
            va="bottom",
            fontsize=9,
            color=th.ink,
            family=fam,
        )
        ax.plot([float(be)], [0], "o", ms=5, color=th.bg, mec=th.ink, mew=1.1, zorder=5)


def render_v2(
    payoff: StrategyPayoff,
    *,
    spot: D,
    title: str,
    subtitle: str,
    fam: str,
    theme: Theme,
    current_pnl: D | None = None,
    margin: D | None = None,
) -> bytes:
    """Render the POC chart to PNG bytes (OO Figure API, no pyplot)."""
    th = theme
    fig = Figure(figsize=(7, 4.9), facecolor=th.bg)
    FigureCanvasAgg(fig)
    fig.subplots_adjust(left=0.13, right=0.97, top=0.70, bottom=0.14)
    draw_header(fig, title, subtitle, stat_cells(payoff, th, spot, margin, current_pnl), th, fam)
    ax = fig.add_subplot(111)
    lo, hi = x_range(payoff, spot)
    xs = sample_xs(payoff, lo, hi)
    ys = np.array([float(expiry_pnl_at(payoff, D(str(x)))) for x in xs])
    ax.fill_between(
        xs, ys, 0, where=ys >= 0, interpolate=True, color=th.green, alpha=th.fill_alpha_green, lw=0
    )
    ax.fill_between(
        xs, ys, 0, where=ys <= 0, interpolate=True, color=th.red, alpha=th.fill_alpha_red, lw=0
    )
    ax.plot(xs, np.ma.masked_where(ys < 0, ys), color=th.green, lw=1.8, solid_capstyle="round")
    ax.plot(xs, np.ma.masked_where(ys > 0, ys), color=th.red, lw=1.8, solid_capstyle="round")
    ax.axhline(0, color=th.muted, lw=0.7)
    style_axes(ax, th, fam)
    ax.set_xlim(lo, hi)
    strike_ticks(ax, payoff, hi - lo, th, fam)
    draw_breakevens(ax, payoff, spot, th, fam)
    ax.axvline(float(spot), color=th.ink, lw=0.9, zorder=2)
    ax.annotate(
        f"SPOT {_label(spot)}",
        (float(spot), 1.0),
        xycoords=("data", "axes fraction"),
        xytext=(0, 4),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=10,
        weight="bold",
        color=th.ink,
        family=fam,
    )
    if current_pnl is not None:
        ax.plot([float(spot)], [float(current_pnl)], "o", ms=8, color=th.ink, zorder=6)
        ax.annotate(
            "Now",
            (float(spot), float(current_pnl)),
            xytext=(0, -24),
            textcoords="offset points",
            ha="center",
            fontsize=9.5,
            color=th.ink,
            family=fam,
            bbox={"fc": th.bg, "ec": "none", "pad": 1.5},
        )
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170, facecolor=th.bg)
    return buf.getvalue()


def contact_sheet(out: Path, names: list[str], cols: int = 2) -> None:
    """Tile ``after_<name>.png`` into ``compare.png`` (half size) so themes sit side by side."""
    from PIL import Image  # pillow ships with matplotlib

    tiles = [Image.open(out / f"after_{n}.png").convert("RGB") for n in names]
    tiles = [t.resize((t.width // 2, t.height // 2), Image.LANCZOS) for t in tiles]
    w, h = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w + (cols + 1) * 12, rows * h + (rows + 1) * 12), "#888888")
    for i, t in enumerate(tiles):
        sheet.paste(t, (12 + (i % cols) * (w + 12), 12 + (i // cols) * (h + 12)))
    sheet.save(out / "compare.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", type=Path, default=None, help="dir with Roboto-Regular/Bold.ttf")
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "payoff_poc")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    fam = load_roboto(args.fonts)
    payoff, spot = demo_payoff(), D(22348)
    before = render_payoff_png(
        payoff, spot=spot, title="paper_ic_nifty_v2_monthly · monthly · 19DTE"
    )
    (args.out / "before.png").write_bytes(before)
    for tname, th in THEMES.items():
        png = render_v2(
            payoff,
            spot=spot,
            title="Iron Condor v2",
            subtitle="Monthly expiry · 19 DTE",
            fam=fam,
            theme=th,
            current_pnl=D("3200"),
            margin=D("86937"),
        )
        (args.out / f"after_{tname}.png").write_bytes(png)
        print(f"after_{tname}", len(png), "bytes")
    contact_sheet(args.out, list(THEMES))
    print("out dir", args.out)


if __name__ == "__main__":
    main()
