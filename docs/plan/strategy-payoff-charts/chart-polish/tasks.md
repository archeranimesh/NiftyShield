# Payoff Chart Polish — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: CP-1.**

- [ ] **CP-1** — `format_money_whole` / `format_money_k` / `format_pct_signed` in `formatting.py` + `FORMATTING.md` §5 override rows | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer
  | SHA: —
- [ ] **CP-2** — `payoff_chart_theme.py`: frozen `ChartTheme` + `DARK`, bundled Roboto assets, guarded `chart_font_family` with DejaVu fallback | Owner: Claude | Model: claude-sonnet-5-5 | Review:
  code-reviewer | SHA: —
- [ ] **CP-3** — `payoff_chart_axes.py` pure helpers: `x_range`, `sample_xs`, `strike_ticks` with crowding stagger | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: —
- [ ] **CP-4** — `payoff_chart_header.py`: `HeaderCell` / `Tone` + pure `build_header_cells` (seven cells, sub-lines) | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: —
- [ ] **CP-5** — `payoff_chart_header.py`: pure `pack_header` + measured, centred `draw_header` with two-row fallback | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: —
- [ ] **CP-6** — `payoff_chart_axes.py` drawing helpers: chrome, strike ticks, breakeven dots, spot line, "Now" marker | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: —
- [ ] **CP-7** — Rewire `render_payoff_png` onto the three modules; delete orphaned helpers; migrate tests; import-boundary test | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer |
  SHA: —
- [ ] **CP-8** — `HasSubtitle` Protocol; IC adapter label / title / subtitle; `_build_and_send` passes subtitle | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: —
- [ ] **CP-9** — `scripts/dev/render_payoff_sample.py` CLI; `git rm` the scratch POC | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: —
- [ ] **CP-10** — Animesh on-device sign-off of a real chart on Telegram; record the verdict and any follow-up tweaks | Owner: Animesh | Model: n/a | Review: none | SHA: —
- [ ] **CP-11** — Docs close: `CONTEXT.md` / `CONTEXT_TREE.md` / `DECISIONS.md` / `src/notifications/CLAUDE.md`, epic README, `chart-model-overlay/` MO-4..6 spec re-point | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: none | SHA: —

## Story done when

- **CP-1** — the three formatters exist, reject `float`, match `format_money`'s sign / grouping rules except decimals, and both money overrides are rows in `FORMATTING.md` §5.
- **CP-2** — `DARK` is frozen; `chart_font_family()` returns `"Roboto"` with the bundled files and `"DejaVu Sans"` (plus a logged warning, no raise) when they cannot load; the bundled files carry ₹
  and tabular digits.
- **CP-3** — `x_range` / `sample_xs` / `strike_ticks` are pure, cover spot-less and strike-less payoffs, and `sample_xs` contains every strike and breakeven exactly.
- **CP-4** — `build_header_cells` returns the cells in order, drops each when its input is missing, and shows `Unlimited` / `MIN PROFIT` / `NET DEBIT` correctly.
- **CP-5** — `pack_header` never returns an overflowing layout (shrinks to the floor, then two rows); `draw_header` centres label, value and sub-line on each cell.
- **CP-6** — each draw helper runs against an Agg `Figure` and leaves the expected tick labels, spine visibility and artists.
- **CP-7** — `render_payoff_png` produces the new chart for every existing test structure with an unchanged call signature (plus `subtitle`); no orphaned helper or test remains; import boundaries
  hold.
- **CP-8** — an IC chart's title is `Iron Condor v1|v2`, its subtitle `<Expiry> expiry · <n> DTE`, and an adapter without `HasSubtitle` still sends a chart.
- **CP-9** — the sample CLI renders the demo IC to a path; the scratch POC is gone.
- **CP-10** — Animesh has seen the chart on a phone and recorded accept / tweak in `stories.md`.
- **CP-11** — new modules, decisions and the formatter overrides are recorded; the epic table shows the story ✅; the graph is re-indexed.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update the epic `README.md` **Stories** table status column and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive* — but this story archives with its epic (`chart-model-overlay/` MO-9), not alone.
