# Chart Model Overlay — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists and the **blocked-until** check; see `stories.md`
for the per-task implementation spec.

**Open: MO-1 — but first confirm the block in `prompt.md` is clear (`chart-core/` done + `greeks-bs-fallback/` GF-2 + GF-3 shipped).**

- [ ] **MO-1** — `src/pricing/expected_move.py`: `expected_move` + `pop_of_profit` (lognormal mass over the profit regions of any payoff, `math.erf`); pure, typed | Owner: Antigravity | Model: n/a |
  Review: code-reviewer | SHA: —
- [ ] **MO-2** — Shared `atm_iv(chain) -> Decimal | None` (nearest-strike IV, CE-preferred; V1 has none) | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: —
- [ ] **MO-3** — `t0_pnl_series(legs: list[PayoffLeg], ...)` using `src/pricing/black_scholes.py`; `iv == 0` leg → `implied_vol.solve_iv` from the mid | Owner: Antigravity | Model: n/a | Review:
  greeks-analyst | SHA: —
- [ ] **MO-4** — `payoff_chart.py`: draw the blue dashed T+0 curve (new optional arg; no-op when `None`) | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **MO-5** — `payoff_chart.py`: draw ±1σ/±2σ verticals + shaded bands from `expected_move` | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **MO-6** — `payoff_chart.py` stat strip: add POP from `pop_of_profit` | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **MO-7** — `MarketAware` capability Protocol (per-leg IV / mid / DTE) in `src/payoff/registry.py`; `send_payoff_chart` builds T+0 + σ + POP from it | Owner: Claude | Model: claude-sonnet-5 |
  Review: code-reviewer | SHA: —
- [ ] **MO-8** — IC adapters (in `payoff_registrations.py`) implement `market(ctx)` for entry, EOD snapshot and both close paths — no call-site edits expected | Owner: Claude | Model: claude-sonnet-5
  | Review: greeks-analyst | SHA: —
- [ ] **MO-9** — Docs close + archive the `strategy-payoff-charts/` epic folder per §Conventions; re-index graph | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **MO-1** — `pop_of_profit` over a single interval spanning `(0, ∞)` is ~1, is monotonic in interval width, handles several disjoint profit regions (sum of masses), and matches a hand-computed
  lognormal mass for one fixed case; `expected_move` matches `spot·(iv/100)·√(dte/basis)`.
- **MO-2** — `atm_iv` returns the nearest-strike IV (CE preferred, PE fallback) as a `Decimal`, `None` when the chain has no usable IV; works for a V1 and a V2 chain fixture.
- **MO-3** — `t0_pnl_series` accepts any `PayoffLeg` list (IC and a non-IC fixture) and returns matched-length arrays; a leg with `iv == 0` is priced off a `solve_iv` result; an unsolvable leg makes
  it return `None` (renderer skips the curve), never raise.
- **MO-4** — the blue dashed T+0 curve is drawn when the series is passed and omitted when `None`; PNG still valid in both cases.
- **MO-5** — ±1σ and ±2σ verticals + shaded bands are drawn from a passed `sigma`; omitted when `None` or `spot` is `None`.
- **MO-6** — POP shows in the stat strip as a % when passed; omitted when `None`.
- **MO-7 / MO-8** — an adapter implementing the `MarketAware` Protocol supplies per-leg IV + mids + DTE from data the call site already holds; `send_payoff_chart` solves the zeros and builds the T+0
  series + `sigma` + `pop`; an adapter that is not `MarketAware`, or an all-zero-IV chain that cannot be solved, still sends the `chart-core/` expiry-only chart.
- **MO-9** — the epic's docs show both sub-stories ✅; `strategy-payoff-charts/` is archived to `docs/archive/plan/`; the graph is re-indexed.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update the epic `README.md` **Stories** table status column and add one line to `TODOS.md` Session Log. When MO-9 lands, the
whole epic is done — follow `docs/plan/README.md` §Conventions *Completion → archive* and move the entire `strategy-payoff-charts/` folder as a unit.
