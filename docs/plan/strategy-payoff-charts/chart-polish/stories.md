# Payoff Chart Polish — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the epic `README.md` status, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions. **Visual spec:**
> `scratch/telegram_formats/2026-10-08_payoff_chart_polish_poc.py` (deleted by CP-9). Every number below — palette, font sizes, line widths, paddings — is taken from it. Run it with `python
> scratch/telegram_formats/2026-10-08_payoff_chart_polish_poc.py --fonts <dir>` to see the target. Read `docs/refactor/design-principles.md` before CP-2 and `docs/refactor/code-review-checklist.md`
> before every commit.

---

## CP-1 — Whole-rupee and `k` money formatters, signed percent

**Files to change / create:**
- `src/notifications/formatting.py` — add `format_money_whole`, `format_money_k`, `format_pct_signed`.
- `tests/unit/notifications/test_formatting.py` — cover them.
- `FORMATTING.md` — two rows in §5 (money 0dp; `k` axis ticks); no edit to §3 (it already documents `format_pct_signed`).

**Before any code (graph queries — do not write from memory):**
- `get_code_snippet("format_money")` — the sign-before-`₹`, `float` → `TypeError`, comma-thousands contract these must mirror.
- `search_graph("format_pct")` — confirm `format_pct_signed` is genuinely absent (FORMATTING §3 documents it; `src/` has none as of 2026-10-08) and read `format_pct`'s whole-number rule.
- Read `FORMATTING.md` §1, §3, §5, §13.

**What to implement:**

1. `format_money_whole(value: Decimal, *, signed: bool = False) -> str` — identical to `format_money` except 0 dp: quantise `ROUND_HALF_UP`, `float` raises `TypeError`, sign before `₹`, comma
   thousands, a value that rounds to zero prints `₹0` (never `-₹0`). Docstring names it a §5 override of the §3 money default and states the reason (header width budget).
2. `format_money_k(value: Decimal) -> str` — axis-tick form: `|v| >= 1000` → `₹10k` / `-₹50k` (whole thousands, no decimals); `|v| < 1000` → `format_money_whole`; `0` → `₹0`. Same `float` rule; the
   chart converts matplotlib's float tick values to `Decimal` at its own boundary, not here.
3. `format_pct_signed(value: float) -> str` — `format_pct` plus a leading `+` on positives (`+3%`, `+2.7%`, `-1.4%`); zero is unsigned (`0%`). `4` means 4%.
4. `FORMATTING.md` §5: add `Payoff chart header cells — money at 0dp with ₹` and `Payoff chart y-axis ticks — k abbreviation` rows, each citing this story and the width-budget reason. Commit body
   notes the `Daily-snapshot waterfall` `k` row is a separate, still-unreconciled precedent.

**Tests (`tests/unit/notifications/`, no network):**
- `test_money_whole_groups_and_rounds` — `9607 → ₹9,607`, `9607.5 → ₹9,608`, `-48893.4 → -₹48,893`, `1486937 → ₹1,486,937`.
- `test_money_whole_signed_and_zero` — `3200, signed → +₹3,200`; `0.4 → ₹0`; `-0.4 → ₹0`.
- `test_money_whole_rejects_float` — `TypeError`; same for `format_money_k`.
- `test_money_k_ticks` — `10000 → ₹10k`, `-50000 → -₹50k`, `0 → ₹0`, `500 → ₹500`, `-500 → -₹500`.
- `test_pct_signed` — `3.0 → +3%`, `2.7 → +2.7%`, `-1.4 → -1.4%`, `0 → 0%`.

**Commit:** `feat(notifications): add whole-rupee and k money formatters`

---

## CP-2 — `ChartTheme`, `DARK`, bundled Roboto, guarded font loader

**Files to change / create:**
- `src/notifications/payoff_chart_theme.py` — new leaf module.
- `src/notifications/assets/fonts/Roboto-Regular.ttf`, `Roboto-Bold.ttf`, `OFL.txt`, `README.md` — assets + provenance (not a Python package; no `__init__.py`).
- `tests/unit/notifications/test_payoff_chart_theme.py`.

**Before any code:**
- `search_graph("payoff_chart")` / read `src/notifications/payoff_chart.py` imports — this module must import nothing from its siblings (it is the leaf).
- `LOGGING.md` — `structlog.get_logger(__name__)` is correct here (`src/`, always imported).
- `requirements.txt` — `matplotlib` is already present; `fontTools` ships with it (the test uses it, so no new dependency).

**What to implement:**

1. `@dataclass(frozen=True) class ChartTheme` with `bg, ink, muted, faint, green, red: str` and `fill_alpha_green, fill_alpha_red: float`. Module constant `DARK = ChartTheme("#0e1117", "#e5e7eb",
   "#9ca3af", "#1f2937", "#26b3a0", "#ef5350", 0.22, 0.14)` — the POC's `DARK`. No other theme, no registry, no selector.
2. `chart_font_family(font_dir: Path | None = None) -> str` — lazy, `functools.cache`-style plus a `threading.Lock` so the first concurrent renders register once. `font_dir=None` means the bundled
   `assets/fonts/` next to this module. Registers `Roboto-Regular.ttf` and `Roboto-Bold.ttf` with `matplotlib.font_manager.fontManager.addfont` and returns `"Roboto"`. Any exception → log
   `payoff_chart.font_fallback` at WARNING with the error and return `"DejaVu Sans"`; never raise. Never touches `rcParams` or `pyplot`. The cache is keyed on `font_dir` so tests can inject a bad one.
3. Assets: static Regular (wght 400) and Bold (wght 700) cut from `google/fonts` `ofl/roboto/Roboto[wdth,wght].ttf` with `fontTools.varLib.instancer` (`wdth=100`, `updateFontNames=True`) — matplotlib
   cannot select weights from a variable font. `README.md` records the source URL, the exact instancer invocation, and the two verified facts (₹ present; digit advances equal within each weight: 1151
   Regular, 1175 Bold). `OFL.txt` is the licence file from the same source directory.

**Tests:**
- `test_dark_theme_is_frozen` — assigning a field raises `FrozenInstanceError`.
- `test_font_family_returns_roboto_with_bundled_files` — `"Roboto"`, and `findfont("Roboto")` resolves to a bundled path.
- `test_font_family_falls_back_when_missing` — `font_dir=tmp_path` (empty) → `"DejaVu Sans"`, a `payoff_chart.font_fallback` warning is logged, nothing raised.
- `test_font_family_registers_once` — second call with the same dir does not call `addfont` again (patch and count).
- `test_bundled_fonts_have_rupee_and_tabular_digits` — both TTFs contain U+20B9 in the cmap and `0`–`9` share one advance width (fontTools).

**Commit:** `feat(notifications): add dark chart theme and bundled Roboto`

---

## CP-3 — Pure axis helpers

**Files to change / create:**
- `src/notifications/payoff_chart_axes.py` — new; this task adds only the pure functions (CP-6 adds drawing to the same module).
- `tests/unit/notifications/test_payoff_chart_axes.py`.

**Before any code:**
- `get_code_snippet("StrategyPayoff")` and `get_code_snippet("PayoffLeg")` — `key_spots`, `breakevens`, `legs[*].strike/qty/kind`.
- `get_code_snippet("_x_range")` (in `payoff_chart.py`) — the behaviour being replaced (1.5× pad; Decimal return); `trace_path("expiry_pnl_at")`.
- `get_code_snippet("format_strike")` — strike labels use it.

**What to implement:**

1. `x_range(payoff, spot: Decimal | None) -> tuple[float, float]` — `key_spots` padded by **0.4×** their span on each side, widened to include `spot`, floored at 0. Empty `key_spots` (FUT/EQ-only)
   falls back to `spot`, then to the first leg's entry price, with a 10% span; a single strike (span 0) also uses `spot × 0.1` as the span. Plain `float` (display geometry, not money).
2. `sample_xs(payoff, lo, hi, n=240) -> np.ndarray` — `linspace(lo, hi, n)` unioned with every strike and breakeven, sorted, unique. This is what makes kinks sharp and zero crossings exact.
3. `@dataclass(frozen=True) class StrikeTick: x: float; text: str; short: bool` and `strike_ticks(payoff, span: float) -> list[StrikeTick]` — one per option strike, ascending; `text` is `"<strike>
   <CE|PE>\n<BUY|SELL>"` (`format_strike`); `short` is `qty < 0`. **Crowding rule:** a tick closer than `0.14 × span` to its predecessor drops one row (its `text` gets a leading `"\n"`), unless the
   predecessor is itself lowered — rows alternate, they never stack. Legs with `strike is None` are skipped.

**Tests:**
- `test_x_range_pads_key_spots_by_point_four_span` — IC 21000..23500 with spot 22348 → `(20000.0, 24500.0)`.
- `test_x_range_includes_spot_outside_strikes` / `test_x_range_floors_at_zero`.
- `test_x_range_without_strikes_uses_spot` — a FUT-only payoff; and `test_x_range_single_strike_uses_ten_percent_span`.
- `test_sample_xs_contains_every_strike_and_breakeven_exactly` — each value `in` the array; array strictly increasing.
- `test_strike_ticks_ic_labels_and_sides` — four ticks; short flags match qty; text e.g. `"21900 PE\nSELL"`.
- `test_strike_ticks_stagger_close_neighbours` — 23000 / 23500 on a 4250-wide span → second lowered; a third close tick returns to the upper row (rows alternate).
- `test_strike_ticks_skip_strikeless_legs` — an EQ leg contributes no tick.

**Commit:** `feat(notifications): add pure payoff chart axis helpers`

---

## CP-4 — Header cell builder

**Files to change / create:**
- `src/notifications/payoff_chart_header.py` — new; this task adds the data types and `build_header_cells` only.
- `tests/unit/notifications/test_payoff_chart_header.py`.

**Before any code:**
- `get_code_snippet("build_stat_strip")` and `get_code_snippet("_worst_case_row")` — the existing `Unlimited` / `Min Profit` / `Net Debit` rules this replaces; they must survive (commits `510f1e4`,
  `1a73ac9`). `search_graph("_breakeven_text")` — the distance-from-spot rule.
- CP-1's three formatters; `format_strike`.
- `FORMATTING.md` §4 — missing vs zero vs unresolved: an absent input drops the cell, it does not print `₹0` or `-`.

**What to implement:**

1. `class Tone(str, Enum)`: `POSITIVE`, `NEGATIVE`, `NEUTRAL`, `MUTED` — the cell builder stays theme-free; `draw_header` (CP-5) maps tone → colour.
2. `@dataclass(frozen=True) class HeaderCell: label: str; value: str; value_tone: Tone; sub: str = ""; sub_tone: Tone = Tone.MUTED`.
3. `build_header_cells(payoff, *, spot, margin, current_pnl) -> list[HeaderCell]` — order and rules:
   - `P&L NOW` — only if `current_pnl is not None`; `format_money_whole(signed=True)`; tone by sign (zero → `NEUTRAL`); sub = `format_pct_signed(pnl / margin × 100)` when `margin` truthy.
   - `MAX PROFIT` — `Unlimited` when `None` (no sub, `NEUTRAL`), else whole-rupee, `POSITIVE`, sub = % of margin.
   - Worst case — `MAX LOSS` (negative whole-rupee, `NEGATIVE`, sub = % of margin; `Unlimited` when `None`) or, when `max_loss >= 0` (guaranteed profit), `MIN PROFIT` (`POSITIVE`).
   - `RISK:REWARD` — `f"{1 / rr_ratio:.1f} : 1"`; omitted when `rr_ratio` is `None` or `0`.
   - `EST. MARGIN` — only when `margin` is truthy.
   - `NET CREDIT` / `NET DEBIT` by sign of `net_premium`, absolute whole-rupee, `NEUTRAL`.
   - `BREAKEVENS` — only when any: values joined by ` – ` via `format_strike(int(b))`; sub = `format_pct_signed` of each distance from `spot`, joined by ` / `, only when `spot` is given.

**Tests:**
- `test_full_ic_cells_in_order` — all seven labels in order; values for the 65-qty reference IC (`₹9,607`, `-₹48,893`, `5.1 : 1`, `₹86,937`, `₹9,607`, `21752 – 23148`); P&L sub `+3.7%`.
- `test_cells_drop_when_input_missing` — no margin → no `EST. MARGIN` and no percent subs; no `current_pnl` → no `P&L NOW`; no `spot` → `BREAKEVENS` with empty sub.
- `test_unbounded_naked_call` — max loss `Unlimited`, no `RISK:REWARD`.
- `test_guaranteed_profit_is_min_profit` and `test_net_debit_label`.
- `test_zero_margin_gives_no_percent` and `test_pnl_zero_is_neutral`.

**Commit:** `feat(notifications): add payoff chart header cell builder`

---

## CP-5 — Header packing and centred drawing

**Files to change / create:**
- `src/notifications/payoff_chart_header.py` — add `pack_header` and `draw_header`.
- `tests/unit/notifications/test_payoff_chart_header.py` — extend.

**Before any code:**
- Read the POC's `draw_header` (the measure-then-pack approach: `fig.canvas.get_renderer()`, `Text.get_window_extent`, widths in inches via `fig.dpi`).
- `get_code_snippet("ChartTheme")` (CP-2) — tone → colour map is `{POSITIVE: green, NEGATIVE: red, NEUTRAL: ink, MUTED: muted}`.

**What to implement:**

1. Pure `pack_header(widths: Sequence[float], avail: float, *, min_gap: float = 0.14, floor: float = 0.8) -> HeaderLayout`, where `HeaderLayout` is a frozen dataclass of `rows: list[list[Slot]]` and
   `scale: float`; `Slot(index, left, width)`. One row if `scale = (avail − min_gap·(n−1)) / Σwidths` is `≥ floor` (clamped to ≤ 1), gaps equal and spread to fill `avail` (space-between). Below the
   floor, split the cells into two rows (first `⌈n/2⌉`) and pack each row the same way. Empty input → no rows.
2. `draw_header(fig, title, subtitle, cells, theme, family) -> int` (returns the row count so the caller can size the axes). Title 16 bold, subtitle 10 muted at the top-left margin (x = 0.03); then
   the cells: label 8.5 (muted), value 12 bold (tone colour), sub 9 (tone colour) — every font multiplied by `layout.scale`; **label, value and sub-line are centred (`ha="center"`) on the cell's
   centre** (`left + width/2`). Cell width = widest of its three texts, measured at scale 1. Constants (margins 0.03 / 0.94, row pitch, font sizes) are module-level, not inline.
3. No drawing outside `[0, 1]` figure fractions for any input the tests below cover.

**Tests:**
- `test_pack_one_row_spreads_gaps_equally` — 7 widths summing to 5.2 in `avail=6.58` → one row, scale 1, equal gaps.
- `test_pack_shrinks_before_wrapping` — slight overflow → one row, `0.8 ≤ scale < 1`, every gap ≥ `min_gap`.
- `test_pack_wraps_below_floor` — heavy overflow → two rows, each fitting; order preserved.
- `test_pack_edge_cases` — one cell, zero cells.
- `test_draw_header_centres_each_cell` — on an Agg `Figure`, every cell's three `Text` objects share one x and `get_ha() == "center"`; x strictly increases across cells; all within `(0, 1)`.
- `test_draw_header_returns_row_count` — normal cells → 1; absurdly wide values → 2.

**Commit:** `feat(notifications): lay out payoff chart header in one row`

---

## CP-6 — Axis drawing helpers

**Files to change / create:**
- `src/notifications/payoff_chart_axes.py` — add drawing helpers (each takes the `ChartTheme` and a font family; none reads global state).
- `tests/unit/notifications/test_payoff_chart_axes.py` — extend.

**Before any code:**
- Read the POC's `style_axes`, `strike_ticks` (drawing part), `draw_breakevens`, and the spot / "Now" block of `render_v2`.
- `get_code_snippet("format_money_k")` (CP-1).

**What to implement:**

1. `style_axes(ax, theme, family)` — top / right spines hidden; left / bottom in `theme.faint`; ticks length 0, `labelsize=9.5`, colour `theme.muted`; horizontal grid `theme.faint` at **0.6** width,
   below the artists; y tick labels via `FuncFormatter(lambda v, _: format_money_k(Decimal(str(round(v)))))` (the float → `Decimal` conversion lives here and is commented as display-only).
2. `draw_strike_ticks(ax, ticks, theme, family)` — x ticks at each `StrikeTick.x` with its `text`; short ticks bold in `ink`, long ones regular in `muted`; a dotted vertical per strike at **0.8**
   width, `ink` for short, `faint` for long. No ticks → leave matplotlib's default numeric x ticks (FUT/EQ-only payoffs).
3. `draw_breakevens(ax, breakevens, spot, theme, family)` — per breakeven: open dot on the zero line (`ms=5`, face `theme.bg`, edge `ink`, `mew=1.1`) and a `BE <n>` label 5 pt above it, offset 7 pt
   outward (left of the dot for the lower breakeven, right for the higher; with `spot is None`, by order — first = left, last = right), font 9.
4. `draw_spot(ax, spot, theme, family)` — a solid vertical at **0.9** width in `ink` and a bold 10 pt `SPOT <n>` label centred just above the axes (axes-fraction y = 1.0, +4 pt).
5. `draw_now_marker(ax, spot, pnl, theme, family)` — filled dot (`ms=8`) at `(spot, pnl)` and a `Now` label 24 pt below with a `theme.bg` bbox so the spot line does not strike through it.

**Tests (Agg `Figure`, no network):**
- `test_style_axes_hides_top_right_spines_and_formats_ticks` — spines, and a formatted tick label equals `₹10k` / `-₹50k`.
- `test_draw_strike_ticks_labels_and_weights` — tick label texts equal the input texts; short ones bold.
- `test_draw_strike_ticks_empty_keeps_default_ticks`.
- `test_draw_breakevens_places_dot_and_label_each_side` — two dots at y = 0; the lower label right-aligned, the higher left-aligned.
- `test_draw_breakevens_without_spot_uses_order`.
- `test_draw_spot_and_now_marker_add_artists` — expected line / text / marker counts.

**Commit:** `feat(notifications): add payoff chart axis drawing helpers`

---

## CP-7 — Rewire `render_payoff_png`

**Files to change / create:**
- `src/notifications/payoff_chart.py` — `render_payoff_png` rebuilt on the three modules; orphaned helpers deleted.
- `tests/unit/notifications/test_payoff_chart.py` — migrate; add the import-boundary test.

**Before any code:**
- `trace_path("render_payoff_png")` — five wired sites call `send_payoff_chart`, not `render_payoff_png` directly; confirm no other caller. `search_graph("build_stat_strip")` — callers are tests only.
- Read `test_payoff_chart.py` in full — every existing render test is a degrade-gracefully contract that must still pass against the new code.
- `src/payoff/test_import_boundary` (`tests/unit/payoff/test_import_boundary.py`) — the AST pattern to copy.

**What to implement:**

1. Signature: unchanged kwargs (`spot`, `current_pnl`, `dte`, `margin`, `title`) plus `subtitle: str = ""`. `dte` is no longer unused: the displayed subtitle is `" · ".join` of the non-empty parts of
   `subtitle` and `f"{dte} DTE"`.
2. Body: `family = chart_font_family()`; `Figure(figsize=(7, 4.9 or 5.7), facecolor=DARK.bg)` + `FigureCanvasAgg` (OO API only — no `pyplot`; the existing `test_render_does_not_touch_pyplot` must
   pass); `rows = draw_header(...)`; one-row layout `subplots_adjust(left=0.13, right=0.97, top=0.70, bottom=0.14)` at height 4.9, two-row `top=0.585, bottom=0.12` at height 5.7. Payoff drawn on
   `sample_xs` with `expiry_pnl_at` per point: green / red fills (`theme` alphas, `lw=0`), green line where `y ≥ 0` and red where `y ≤ 0` at **1.8** width, zero line `muted` at **0.7**.
   `savefig(dpi=170, facecolor=DARK.bg)`.
3. The spot-dependent elements (`draw_spot`, `draw_now_marker`, distance sub-lines) appear only when `spot` is given; `draw_now_marker` additionally needs `current_pnl`. Every other input degrades as
   before. All failures still wrap in `RenderError` (EAFP at the boundary, unchanged).
4. Delete what this orphans: `build_stat_strip`, `_worst_case_row`, `_draw_stat_strip`, `_breakeven_text`, `_pnl_dot_label`, `_draw_verticals`, `_plot_line`, `_x_range`, and any now-unused import /
   constant (`_GREEN`, `_RED`, `_POINTS`). `send_payoff_chart`, `_build_and_send`, `PhotoSender` are untouched.
5. `test_payoff_chart_modules_import_boundary` (AST): `payoff_chart_theme` imports no sibling chart module; `payoff_chart_axes` and `payoff_chart_header` import only the theme (and `formatting` /
   `src.payoff`), never `payoff_chart`.

**Tests:**
- Keep and run unchanged: every `test_render_*` degrade test (minimal, unbounded, naked call, single-strike pnl, no margin, no spot, locked profit, wraps failures, no pyplot).
- Delete `test_stat_strip_*` (superseded by CP-4's cell tests).
- `test_render_full_inputs_returns_valid_png` — all optional inputs, PNG signature, size under 250 KB.
- `test_render_with_font_fallback` — patch `chart_font_family` to return `"DejaVu Sans"`; still a valid PNG.
- `test_render_two_row_header_on_huge_values` — absurd margin / loss → valid PNG, taller than the one-row render (decode height).
- `test_render_five_strike_structure` — a six-leg fixture renders without error.

**Commit:** `feat(notifications): render payoff chart in dark Roboto layout`

---

## CP-8 — Subtitle Protocol and IC title / subtitle

**Files to change / create:**
- `src/payoff/registry.py` — `HasSubtitle` Protocol beside `HasTitle`.
- `src/strategy/payoff_registrations.py` — `IronCondorPayoffAdapter` gains `label`; `title()` / `subtitle()`; `ensure_registered` passes the label.
- `src/notifications/payoff_chart.py` — `_build_and_send` passes `subtitle`.
- `tests/unit/payoff/test_registry.py`, `tests/unit/strategy/test_payoff_registrations.py`, `tests/unit/notifications/test_payoff_chart.py` — migrate / extend.

**Before any code:**
- `get_code_snippet("HasTitle")` — copy its `@runtime_checkable` shape. `get_code_snippet("IronCondorPayoffAdapter")` and `get_code_snippet("_ic_strategy_names")`.
- `search_graph("STRATEGY_LABELS")` — confirm the IC ids are **not** in it (design review #7); if they are by the time this runs, reuse is still wrong because an unmapped id raises — keep the
  adapter-owned label.
- `trace_path("title")` on the adapter — find tests pinning the old `"<name> · <expiry> · <n>DTE"` string.

**What to implement:**

1. `HasSubtitle(Protocol)`: `def subtitle(self, ctx: PayoffContext) -> str`, `@runtime_checkable`, exported next to `HasTitle`.
2. `IronCondorPayoffAdapter(expiry_type, resolver, label)`: `title()` returns `label` (`"Iron Condor v1"` / `"Iron Condor v2"`); `subtitle()` returns `f"{expiry_type.capitalize()} expiry"`. The DTE
   leaves the adapter entirely (the renderer composes it from its `dte` argument), so `ctx.extras["dte"]` is no longer read here.
3. `_ic_strategy_names()` returns `(strategy_name, expiry_type, label)`, deriving the label from which config table (`CONFIGS` → v1, `CONFIGS_V2` → v2) the entry came from.
4. `_build_and_send`: `subtitle = adapter.subtitle(ctx) if isinstance(adapter, HasSubtitle) else ""`, passed to `render_payoff_png`. An adapter without `HasSubtitle` still charts.

**Tests:**
- `test_ic_adapter_title_and_subtitle` — V1 and V2 adapters, weekly and monthly.
- `test_ensure_registered_labels_v1_and_v2` — registered adapters carry the right label for a V1 and a V2 strategy name.
- `test_build_and_send_passes_subtitle` — patch the renderer, assert the kwarg.
- `test_build_and_send_adapter_without_subtitle` — a `HasTitle`-only adapter yields `subtitle=""` and still sends.

**Commit:** `feat(payoff): add chart subtitle protocol and IC labels`

---

## CP-9 — Sample CLI; retire the scratch POC

**Files to change / create:**
- `scripts/dev/render_payoff_sample.py` — new CLI (`__init__.py` already present in `scripts/dev/`; confirm).
- `tests/unit/` — a CLI test.
- `scratch/telegram_formats/2026-10-08_payoff_chart_polish_poc.py` — `git rm`.

**Before any code:**
- `LOGGING.md` and an existing `scripts/dev/` entrypoint for the `_SCRIPT_NAME = "scripts.dev.render_payoff_sample"` + `setup_logging()` pattern (never `get_logger(__name__)` in `scripts/`).
- `SCRATCH.md` convergence rule — this is the promotion it describes; the memory note "no throwaway scripts for repeatable ops" applies (re-run on every future chart tweak).

**What to implement:**

1. `python -m scripts.dev.render_payoff_sample --out PATH [--no-margin] [--no-pnl] [--no-spot]` renders the reference IC (65 × 21000 / 21900 / 23000 / 23500 with the POC's premiums; spot 22348; margin
   ₹86,937; P&L ₹3,200; 19 DTE; title `Iron Condor v2`, subtitle `Monthly expiry`) through the production `render_payoff_png` and writes the PNG. The flags let a reviewer see each degrade path.
2. Prints the output path (interactive script — allowed to), logs `render_payoff_sample.done` with the byte size.
3. `git rm` the scratch POC in this commit — nothing else imports it.

**Tests:**
- `test_sample_cli_writes_png` — `main(["--out", tmp])` → file starts with the PNG signature.
- `test_sample_cli_flags_degrade` — `--no-margin --no-pnl --no-spot` still writes a valid PNG.

**Commit:** `feat(dev): add payoff chart sample renderer CLI`

---

## CP-10 — On-device sign-off (Animesh)

**Owner: Animesh. No code. No commit by Claude beyond recording the outcome.**

1. Render with `python -m scripts.dev.render_payoff_sample --out <file>`; send it to yourself on Telegram (phone) and, ideally, also look at the next real chart from the EOD snapshot cron.
2. Judge: stat-header legibility at phone width; payoff / spot line weight (thin lines may look faint — 1.8 / 0.9 / 0.8 are desktop judgments); dark card in your Telegram theme; the strike-label
   stagger; title wording (`Iron Condor v2` vs the entry message's `IC v2`).
3. Record in this file under **Outcome:** *accept* or a bullet list of tweaks. Tweaks become follow-up tasks `CP-10a…` appended to `tasks.md` (constants live in the modules from CP-2..CP-6, so most
   are one-line edits).

**Outcome:** _pending_

---

## CP-11 — Docs close

**Files to change:**
- `CONTEXT.md` ("What Exists": `src/notifications/` line), `CONTEXT_TREE.md` (three new modules, `assets/fonts/`, `scripts/dev/render_payoff_sample.py`), `DECISIONS.md` (one entry: dark-only theme,
  bundled Roboto, whole-rupee / `k` overrides, `fmt_inr` rejected, `format_pct_signed` added), `src/notifications/CLAUDE.md` (chart modules + font-fallback invariant), the epic `README.md` (story ✅ +
  SHA, design-review rows), `docs/plan/README.md` status line, `TODOS.md`.
- `docs/plan/strategy-payoff-charts/chart-model-overlay/stories.md` — re-point MO-4 / MO-5 / MO-6 at the new structure: the T+0 curve and σ bands are drawn from `payoff_chart.py` using the CP-6 helper
  conventions (`ChartTheme` colours, no inline hex), and the POP stat is a new `HeaderCell` appended by `build_header_cells(pop=...)` (CP-4) — not "next to R:R in the stat strip".

**What to do:** targeted `Edit`s only; run `python -m scripts.dev.reflow_md` on every touched `docs/plan` file; re-index the graph (`index_repository`). No code in this task.

**Commit:** `docs(plan): close payoff chart polish story`
