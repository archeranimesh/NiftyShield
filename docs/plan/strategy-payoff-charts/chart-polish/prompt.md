# Payoff Chart Polish — prompt

> Redraw the Telegram payoff PNG in its final visual form: dark theme, bundled Roboto, a one-row centred stat header with percent-of-margin lines, strike-labelled x-axis, exact-kink payoff line, and a
> human title + subtitle. Layout and styling only — no new market data and no option model (that stays in `chart-model-overlay/`).

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

`chart-core/` shipped a correct but plain chart (`6ef2a5f`), and its own *Perspectives not covered* flagged that colours, font sizes and layout were never judged on a real image. Judged now
(2026-10-08, screenshot of `paper_ic_nifty_v2_monthly`), the production chart has concrete defects: the payoff line has a one-sample gap at each breakeven (two masked series never meet); the breakeven
labels collide with the title; the x-range pads 1.5× the strike span so the profit tent fills ~20% of the width; strikes are unlabelled grey lines with no long/short or CE/PE cue; the title is the raw
strategy id with "monthly" printed twice; the two-line bold stat strip is hard to read once Telegram shrinks the image to phone width; and `R:R: 1:0.20` is ambiguous.

Animesh iterated a scratch POC (`scratch/telegram_formats/2026-10-08_payoff_chart_polish_poc.py`, five palettes compared on `compare.png`) and chose the **dark** theme. The header borrows the field
set of the Stockmock reference, restricted to what the repo can already supply: P&L now, Max Profit, Max Loss, Risk:Reward, Est. Margin, Net Credit, Breakevens — with percent-of-margin and
breakeven-distance sub-lines. This story graduates that POC into tested production modules and deletes the POC.

## Design decisions (confirmed with Animesh, 2026-10-08)

- **Dark theme only.** One `ChartTheme` constant (`DARK`). The other four POC palettes (light, paper, midnight, cb_slate) are not shipped and there is no theme switch or config knob (YAGNI).
- **Roboto, bundled** (Regular + Bold static TTFs in-repo) with a DejaVu Sans fallback. No fetch-at-render-time font loading.
- **All seven header cells in one row**, each cell centred on its own width, spaced evenly; fonts shrink uniformly to a floor, and below the floor the header falls back to two rows.
- **Whole-rupee money in the header, `₹10k` ticks on the y-axis** — both registered as `FORMATTING.md` §5 overrides (width budget), not inlined.
- **Risk:Reward is shown risk-first, normalised to reward = 1** (`5.1 : 1`), label `RISK:REWARD`.
- **Title = strategy label, subtitle = `<Expiry> expiry · <n> DTE`**; the raw strategy id leaves the image.

## Scope guard

**In bounds:** three new leaf modules `src/notifications/payoff_chart_theme.py`, `payoff_chart_axes.py`, `payoff_chart_header.py`; bundled font assets under `src/notifications/assets/fonts/`;
`render_payoff_png` rewired onto them (public signature gains only `subtitle`); two new named formatters + `format_pct_signed` in `src/notifications/formatting.py` and their `FORMATTING.md` §5 rows;
`HasSubtitle` Protocol in `src/payoff/registry.py`; `IronCondorPayoffAdapter` title/subtitle and `_build_and_send` passing the subtitle; a `scripts/dev/render_payoff_sample.py` CLI (the POC
graduated); removal of the helpers this orphans.

**Out of bounds:** POP, ±1σ/±2σ bands and the T+0 curve (`chart-model-overlay/`); any other theme or a theme switch; the parked "single photo with the text as caption" change (blocked on the
design-gate epic, `docs/plan/design-discipline/` DG-5); the content of the text messages; wiring any new strategy; the `payoff_registrations` registry mechanics; any DB schema change; Indian
(lakh/crore) digit grouping — `FORMATTING.md` §3 fixes comma thousands for every money value, and a chart that grouped differently would print the same position's number two ways.

Changes `src/` and `scripts/dev/` behaviour (the PNG every wired site sends changes). Not docs/tooling only.

## Design review (2026-10-08, against `docs/refactor/`)

| # | Finding | Principle | Resolution | Task |
|---|---|---|---|---|
| 1 | `payoff_chart.py` (~310 lines) already mixes send, render and strip; this story would add more | SRP | Three leaf modules, one-way deps; AST import-boundary test | CP-2..7 |
| 2 | Palette as `if theme == ...` branches is the OCP trigger on day two | OCP | Frozen `ChartTheme` injected into every draw helper; one `DARK` constant | CP-2 |
| 3 | Layout math buried in drawing code is testable only by eye | DIP / testability | Pure functions returning plain data (`x_range`, `sample_xs`, `strike_ticks`, `pack_header`) | CP-3, CP-5 |
| 4 | Font registration mutates global `fontManager`; render runs in `asyncio.to_thread` | async rules | Lazy, locked, cached `chart_font_family(font_dir)`; never import-time or `rcParams` | CP-2 |
| 5 | A font failure must not take the chart (and the Telegram send) down | non-fatal contract | EAFP in `chart_font_family`: log `payoff_chart.font_fallback`, return `"DejaVu Sans"` | CP-2 |
| 6 | A subtitle method on the one adapter Protocol would force stubs | ISP | Separate `HasSubtitle` Protocol beside `HasTitle` | CP-8 |
| 7 | `strategy_label()` maps three-track ids only and raises on others, which would drop the chart | prior-art audit | Not reused; the IC adapter carries its own label (V1 / V2 config split) | CP-8 |
| 8 | `fmt_inr` (Indian grouping) is the obvious reuse, but every other money value is comma-thousands | FORMATTING §1, §3 | Rejected; two named formatters beside `format_money` | CP-1 |
| 9 | `FORMATTING.md` documents `format_pct_signed` but `src/` has no such function | docs vs code | Implement it, rather than inlining `f"{v:+.1f}%"` in the header | CP-1 |
| 10 | The scratch POC would live on as a second copy of the converged design | `SCRATCH.md` convergence | `git rm` the POC in the commit that lands the sample CLI | CP-9 |

Council checkpoint (CLAUDE.md Step 2b): **no** — cosmetic, cheap to reverse; fails condition (1).

## Session-start load hints

- `src/notifications/CLAUDE.md` — non-fatal contract; chart modules' invariants.
- `FORMATTING.md` — §1 (one rule), §3 (canonical rules), §5 (override registry), §13 (changing it).
- `LOGGING.md` — any new `logger.*()` call (`payoff_chart.font_fallback`) and the `scripts/dev` entrypoint rule for CP-9.
- `docs/refactor/design-principles.md` + `code-deduplication-and-taxonomy.md` before CP-2 (new modules) and `code-review-checklist.md` before each commit.
- The scratch POC is the visual spec until CP-9 deletes it; its `compare.png` contact sheet is in the authoring session's scratchpad only (not versioned) — regenerate with the POC if needed.
- No `schema.md` — no DB schema change.

## Task overview

- **CP-1** — `format_money_whole`, `format_money_k`, `format_pct_signed` + `FORMATTING.md` §5 rows.
- **CP-2** — `ChartTheme` / `DARK` + bundled Roboto + guarded `chart_font_family`.
- **CP-3** — pure axis helpers: `x_range`, `sample_xs`, `strike_ticks` (with crowding stagger).
- **CP-4** — pure `build_header_cells` (the seven cells, sub-lines, tones).
- **CP-5** — pure `pack_header` + measured, centred `draw_header` with one-row → two-row fallback.
- **CP-6** — axis drawing helpers: chrome, strike ticks, breakeven dots, spot line, "Now" marker.
- **CP-7** — rewire `render_payoff_png`; delete the orphaned helpers; migrate tests.
- **CP-8** — `HasSubtitle`; IC adapter title / subtitle; `_build_and_send` passes it.
- **CP-9** — `scripts/dev/render_payoff_sample.py`; delete the scratch POC.
- **CP-10** — Animesh on-device sign-off (gate, no code).
- **CP-11** — Docs close.

## Definition of done

Mirrors `tasks.md` "## Story done when". In short: every wired site sends the new dark Roboto chart; the payoff line is continuous through both breakevens; the seven-cell header fits one row for a
normal IC and degrades to two rows (never overflows) for large numbers; every value is formatted by a registered formatter; a missing font, margin, spot, P&L or an unbounded side degrades the chart,
never raises; and Animesh has judged it on a phone.

## Perspectives not covered

- **On-device legibility.** All judging so far was on a desktop at full size and a half-size contact sheet. Telegram's own downscale and phone pixel density are untested until CP-10; line widths
  (payoff 1.8, spot 0.9, strikes 0.8) were thinned on desktop judgment and may need to go back up.
- **Dark image in a light Telegram theme.** Telegram does not tell a bot the viewer's theme. A dark card reads as an image in either theme, but it is a taste call, not a measured one.
- **Many-strike structures.** The tick-crowding rule alternates two label rows, which is fine for a four-strike IC and untested beyond it. Butterflies, ratio spreads and six-leg structures may need a
  third row or label thinning; no such strategy is registered yet.
- **Label wording.** The chart title says "Iron Condor v2" while the entry message headline says "IC v2". Two spellings of one strategy across messages is the kind of drift `FORMATTING.md` §1 exists
  to prevent — Animesh to pick one at CP-10.
- **Font binaries in git.** ~315 KB of TTF added to the repo, cut from the variable Roboto with `fontTools.varLib.instancer` (the exact commands go in the assets README, judged a one-off, not a
  recurring operation). If Roboto is ever re-cut, that note is the only record.
- **Header growth.** Seven cells fit one row with ~0.2 in gaps at today's value widths. A debit structure, a lakh-scale margin or the future POP cell (`chart-model-overlay/` MO-6) eat that slack;
  CP-5's two-row fallback is the safety valve, not a layout goal.
