# Chart Guidelines (matplotlib)

Standard for every generic plot NiftyShield renders (Telegram PNGs, reports, scratch PoCs that may be promoted). It is extracted from the accepted payoff chart (`chart-polish`, accepted on-device
2026-10-13), whose colours and fonts are considered final. Reference implementation: `src/notifications/payoff_chart*.py`. If this doc and that code disagree, the code is the truth — fix the doc.

## Palette and fonts (frozen)

All colours come from the frozen `ChartTheme` in `src/notifications/payoff_chart_theme.py` (`DARK`). The chart is dark-only; there is no light variant.

| Token | Hex | Use |
|---|---|---|
| `bg` | `#0e1117` | Figure and axes background; also the fill of "hole" markers and label backing boxes |
| `ink` | `#e5e7eb` | Primary text, spot line, markers, short-leg emphasis |
| `muted` | `#9ca3af` | Tick labels, zero/baseline line |
| `faint` | `#1f2937` | Grid, spines, secondary vertical guides |
| `green` | `#26b3a0` | Gain / positive series |
| `red` | `#ef5350` | Loss / negative series |

Area fills reuse the line colour with alpha: `fill_alpha_green = 0.22`, `fill_alpha_red = 0.14` (loss is deliberately quieter). Font is bundled Roboto (`assets/fonts/Roboto-Regular.ttf`,
`Roboto-Bold.ttf`), resolved only through `chart_font_family()`, which falls back to `"DejaVu Sans"` and never raises.

Type scale (pt): title 16 bold, subtitle 10, stat label 8.5, stat value 12 bold, stat sub 9, tick labels 9.5, annotations 9–10 (the spot label is 10 bold).

## Do

- Take every colour from a `ChartTheme` instance. A new semantic colour is added to `ChartTheme` (and its tests), not written inline.
- Get the font family once via `chart_font_family()` and pass `family=` to every text artist, including tick labels (`set_xticklabels(..., family=family)`).
- Build figures object-oriented and headless: `Figure(figsize=..., facecolor=theme.bg)` + `FigureCanvasAgg(fig)`. No `pyplot`, no global state, nothing to `plt.close()`.
- Save with `fig.savefig(buf, format="png", dpi=170, facecolor=theme.bg)` into a `BytesIO` and return `bytes`. The base size is 7 x 4.9 in; grow height (5.7) when the header wraps to a second row.
- Keep chrome quiet: hide top and right spines, colour left and bottom spines `faint`, ticks `length=0` in `muted`, horizontal-only grid in `faint` at `lw=0.6` with `set_axisbelow(True)`.
- Colour by sign, not by series: line `lw=1.8` with `solid_capstyle="round"`, split with `np.ma.masked_where` so green and red never overlap; fill under the curve with `fill_between(...,
  interpolate=True, lw=0)`.
- Draw a zero/baseline with `axhline(0, color=muted, lw=0.7)`; vertical reference lines (spot) in `ink` at `lw=0.9`; secondary guides dotted (`ls=":"`, `lw=0.8`) in `faint`.
- Label with `annotate` using `textcoords="offset points"` so offsets survive resizing. Back overlapping labels with `bbox={"fc": theme.bg, "ec": "none", "pad": 1.5}`.
- Use "hole" markers for levels (open dot: `color=theme.bg, mec=theme.ink, ms=5, mew=1.1`) and a filled `ink` dot (`ms=8`) for the current value. Set `zorder` explicitly for markers (5–6) and the spot
  line (4).
- Format money through the shared helpers (`format_money_whole`, `format_money_k`, per `FORMATTING.md` §5): `₹` at 0dp in headers, `k` abbreviation on y ticks. Convert `float` to `Decimal` only at the
  display edge, via `Decimal(str(v))`.
- Compute data (ranges, ticks, breakevens, payoff) in pure, separately tested helpers; keep drawing functions thin. Split by responsibility the way the payoff chart does: theme, axes maths and draw
  helpers, header.
- From async code, render via `asyncio.to_thread(...)` so the event loop is never blocked.
- Wrap rendering so only a project error escapes (`RenderError`), and make chart delivery additive and non-fatal: a failed chart must never suppress the text notification.
- Test offline: assert on theme tokens, pure axis maths and that the output starts with the PNG magic bytes. Never compare pixels against a golden image.

## Don't

- Don't write hex strings, named colours (`"red"`) or matplotlib default colour cycles (`C0`..`C9`) in drawing code.
- Don't use `matplotlib.pyplot` (`plt.subplots`, `plt.figure`, `plt.show`, `plt.savefig`) in `src/`. It drags in global state, a GUI backend and figure-leak bugs under threads.
- Don't rely on matplotlib's default font, and don't call `font_manager.addfont` outside `chart_font_family()`.
- Don't add a light theme, gradients, drop shadows, 3D, or chart borders. Don't add a legend when direct labels do the job.
- Don't use a rainbow or more than two hues for a signed series. Green and red carry sign; everything else is `ink`, `muted` or `faint`.
- Don't use bare `float` for money values that are displayed or stored; `float` is for plotting coordinates only.
- Don't draw a full box grid, vertical gridlines, or visible tick marks. Don't use thick lines (> 2 pt) or tiny markers (< 5 pt).
- Don't let a render error propagate as a matplotlib or numpy type, and don't call `savefig` to disk in production paths (return bytes; the sender owns I/O).
- Don't use `tight_layout()` for the headered layout. Use explicit `subplots_adjust` margins (`left=0.13`, `right=0.97`, plus the top and bottom values for one or two header rows) so the header
  geometry stays deterministic.
- Don't render on the event loop, and don't hold a `Figure` beyond the render call.

## Adapting to a new chart type

Reuse `ChartTheme`, `chart_font_family()`, `style_axes()` and the figure/save recipe above unchanged. Only the data layer and the annotations are new. If a chart genuinely needs a token the theme
lacks (a third semantic colour, say), add it to `ChartTheme` with a test and a row in the table above in the same commit, and get Animesh's approval first, since the current palette is accepted as
final.
