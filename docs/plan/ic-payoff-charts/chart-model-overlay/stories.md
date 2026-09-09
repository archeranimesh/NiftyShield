# Chart Model Overlay — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> **First** re-check the block in `prompt.md`: `chart-core/` complete **and**
> `greeks-bs-fallback/` GF-2 + GF-3 shipped. If not, stop.
> After each task: set `SHA:` on the task line + tick the box, update the epic `README.md`
> **Stories** table, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

No DB schema change anywhere in this story — no `schema.md`.

**Shared facts (verified 2026-09-09):**

- `OptionLeg.iv` (`src/models/options.py`) is annualised %, `Decimal | None`; a genuine
  Upstox zero is `Decimal("0")`, not `None`. Upstox returns `iv == 0` on **every** strike for
  the yearly/leaps bucket; monthly/quarterly are fine; weekly is unverified.
- `_sd_sanity_check` (`src/strategy/ic_nifty_v2.py:527`) computes
  `sd = spot * (atm_iv_pct/100) * sqrt(dte/365) * cfg.sd_atm_iv_multiplier`. No drift, no
  rate. `_atm_iv` (`ic_nifty_v2.py:2789`) takes the `iv` of the chain strike nearest spot,
  CE-preferred then PE, in percent. **V1 has neither.**
- The pricer (from `greeks-bs-fallback/`, must exist before this story starts):
  `src/pricing/black_scholes.py` — `call_price`, `put_price`, `call_delta`, `put_delta`,
  `float` math, Hull formulas. `src/pricing/implied_vol.py` — `solve_iv(option_type,
  mid_price, spot, strike, dte, rate) -> float | None`, Newton-Raphson + bisection, never
  raises. Confirm the exact signatures with `get_code_snippet` — they may have shifted
  during that story.
- The three modeling constants (risk-free rate, DTE convention `days/365` vs `days/252`,
  delta tolerance) are settled in `greeks-bs-fallback/` GF-1 — read them there, do not pick
  new ones.
- `chart-core/` shipped: `src/strategy/payoff.py` (`ICPayoff`, `compute_ic_payoff`,
  `expiry_pnl_at`, `expiry_pnl_series`), `src/notifications/payoff_chart.py`
  (`render_expiry_payoff_png`, `build_and_send_ic_payoff`), `send_photo` on the Telegram
  wrappers, and the five wired call sites.

---

## MO-1 — `expected_move` + `pop_between`

**Files to change / create:**
- `src/pricing/expected_move.py` — new (package `src/pricing/` exists from `greeks-bs-fallback/`).
- `tests/unit/pricing/test_expected_move.py` — new.

**Before any code:**
- `get_code_snippet("solve_iv")` and read `src/pricing/black_scholes.py` — match its style
  (`float`, module layout, docstring citation format).
- `bash sed -n '520,575p' src/strategy/ic_nifty_v2.py` — the exact `_sd_sanity_check` formula
  and the DTE basis it uses.
- Read `docs/plan/greeks-bs-fallback/stories.md` for the settled DTE convention.

**What to implement:**

1. `expected_move(spot: float, atm_iv_pct: float, dte: int) -> float` —
   `spot * (atm_iv_pct / 100.0) * sqrt(dte / <basis>)` where `<basis>` is the
   `greeks-bs-fallback/`-settled convention (365 or 252). One standard deviation, no fudge
   multiplier (the chart draws the raw ±1σ/±2σ, unlike `_sd_sanity_check`'s gated check).
2. `_norm_cdf(x: float) -> float` — `0.5 * (1 + erf(x / sqrt(2)))` via `math.erf`.
3. `pop_between(spot: float, lo: float, hi: float, dte: int, iv_pct: float, rate: float = <settled>) -> float`
   — lognormal probability that the underlying is in `[lo, hi]` at `dte`:
   `P = N(d(hi)) - N(d(lo))` with `d(K) = (ln(K/spot) - (rate - 0.5*sigma^2)*T) / (sigma*sqrt(T))`,
   `sigma = iv_pct/100`, `T = dte/<basis>`. Clamp to `[0, 1]`. Return `0.0` for `dte <= 0` or
   `iv_pct <= 0` (POP undefined — the renderer then omits it).
4. Pure functions, full type hints, Google docstrings citing the lognormal / Hull reference.

**Tests:**
- `test_pop_between_full_range` — `pop_between(spot, 1e-6, 1e9, …)` ≈ 1.0.
- `test_pop_between_monotonic_in_width` — wider `[lo, hi]` ⇒ larger POP.
- `test_pop_between_known_value` — one fixed `(spot, lo, hi, dte, iv)` vs a hand / scipy
  reference value committed in the test.
- `test_pop_between_degenerate` — `dte = 0` or `iv = 0` → `0.0`, no error.
- `test_expected_move_formula` — matches the closed form for a fixed input.

**Commit:** `feat(pricing): add expected-move and probability-of-profit helpers`

---

## MO-2 — Shared `atm_iv` accessor

**Files to change / create:**
- `src/pricing/atm_iv.py` **or** a function in `src/strategy/` — decide from where the call
  sites can import without a cycle (`src/pricing/` is leaf-level, prefer it).
- the matching test.

**Before any code:**
- `bash sed -n '2780,2815p' src/strategy/ic_nifty_v2.py` — V2's `_atm_iv`.
- `get_code_snippet("OptionChain")` and `get_code_snippet("OptionChainStrike")` — the
  `strikes` dict shape and `ce` / `pe` access.
- `trace_path("_atm_iv")` — who calls V2's version; decide whether to leave it and add a
  shared one, or have V2 delegate (prefer: add shared, leave V2 alone to keep the diff small
  — note the duplication for a later cleanup).

**What to implement:** `atm_iv(chain: OptionChain) -> Decimal | None` — find the strike
nearest `chain.underlying_spot`, return its `ce.iv` if a positive `Decimal`, else its
`pe.iv` if positive, else scan outward a few strikes, else `None`. Never raise.

**Review:** `greeks-analyst` — blocking (option-chain IV extraction).

**Tests:**
- `test_atm_iv_ce_preferred` — fixture chain where CE and PE both have IV → returns CE's.
- `test_atm_iv_pe_fallback` — nearest CE `iv` is 0/None, PE positive → returns PE's.
- `test_atm_iv_all_zero` — every strike `iv == 0` (yearly-bucket shape) → `None`.

**Commit:** `feat(pricing): add shared ATM-IV chain accessor`

---

## MO-3 — `t0_pnl_series`

**Files to change / create:**
- `src/notifications/payoff_chart.py` (or a sibling `src/pricing/` helper if it keeps
  `payoff_chart.py` free of pricing imports — prefer the sibling, e.g.
  `src/pricing/ic_t0.py`).
- the matching test.

**Before any code:**
- `get_code_snippet("call_price")`, `get_code_snippet("put_price")`, `get_code_snippet("solve_iv")`
  — exact signatures from `greeks-bs-fallback/`.
- Read `greeks-bs-fallback/stories.md` GF-1 for the risk-free rate + DTE convention.

**What to implement:**

`t0_pnl_series(*, legs, lo, hi, n, dte, spot_now, iv_by_leg, mid_by_leg, lot_size, rate) -> tuple[list[float], list[float]] | None`:
- `legs` = the four `(role, strike, kind)` tuples (`role ∈ {short_put, long_put, short_call,
  long_call}`).
- For each leg: `iv = iv_by_leg[role]`; if `iv <= 0`, `iv = solve_iv(kind, mid_by_leg[role],
  spot_now, strike, dte, rate)`. If that is `None` for any leg → **return `None`** (the
  renderer skips the T+0 curve; the expiry chart still renders).
- For each of `n` spot points `S` in `[lo, hi]`: position value today =
  `Σ sign(role) * price(kind, S, strike, T=dte/<basis>, iv, rate)` where `sign` is `+1` for
  shorts (we received premium; a rise in the option price is a loss) — match the sign
  convention already used by `_compute_combined_pnl` (verify with `get_code_snippet`).
  P&L today at `S` = `(entry_credit - value_to_close(S)) * lot_size`.
- Return `(spots, pnls)` as `float` lists.
- Pure, no I/O, never raises (a math domain error → `None`).

**Review:** `greeks-analyst` — blocking.

**Tests:**
- `test_t0_series_matches_expiry_at_zero_dte` — with `dte` very small, the T+0 curve ≈ the
  expiry payoff (within tolerance).
- `test_t0_series_all_iv_present` — no `solve_iv` needed → matched-length arrays, peak near
  the short strikes.
- `test_t0_series_solves_zero_iv` — one leg `iv = 0`, a solvable mid → curve produced.
- `test_t0_series_unsolvable_returns_none` — `solve_iv` returns `None` → function returns
  `None`, no raise.

**Commit:** `feat(pricing): add IC T+0 mark-to-market P&L series`

---

## MO-4 — Draw the T+0 curve

**Files to change / create:**
- `src/notifications/payoff_chart.py` — extend `render_expiry_payoff_png`.
- `tests/unit/notifications/test_payoff_chart.py` — add a case.

**What to implement:** a new optional arg `t0_series: tuple[list[float], list[float]] | None
= None`. When given, plot it as a blue dashed line on the same axes. When `None`, unchanged.
Keep the y-limits sane if the T+0 curve dips below `max_loss` (it can near a long strike
pre-expiry) — clamp the view or expand it, decide visually.

**Tests:** `test_render_with_t0_curve` — pass a series → valid PNG; `test_render_without_t0`
— `None` → identical behaviour to `chart-core/`.

**Commit:** `feat(notifications): draw T+0 curve on IC payoff chart`

---

## MO-5 — ±1σ / ±2σ bands

**Files to change / create:**
- `src/notifications/payoff_chart.py` — extend the renderer.
- test — add a case.

**What to implement:** a new optional arg `sigma: float | None = None`. When given, draw
dashed grey verticals at `spot ± sigma` and `spot ± 2*sigma`, label them `-1σ`, `+1σ`, `-2σ`,
`+2σ`, and lightly shade the `±1σ`–`±2σ` corridors (matching the Stockmock look). Requires
`spot`; no-op when `spot is None` or `sigma is None`.

**Tests:** `test_render_with_sigma_bands` → valid PNG; `test_render_sigma_needs_spot`
(`sigma` set, `spot=None`) → no crash, bands simply absent.

**Commit:** `feat(notifications): draw expected-move sigma bands on IC payoff chart`

---

## MO-6 — POP in the stat strip

**Files to change / create:**
- `src/notifications/payoff_chart.py` — extend the stat strip.
- test — add a case.

**What to implement:** a new optional arg `pop: float | None = None`. When given (0–1), show
`POP  <xx.x%>` in the stat strip next to R:R. Omit the stat when `None`. Format via the
`FORMATTING.md` percent helper.

**Tests:** `test_stat_strip_with_pop` / `test_stat_strip_without_pop`.

**Commit:** `feat(notifications): show POP in IC payoff chart stat strip`

---

## MO-7 — Thread inputs through the entry path

**Files to change / create:**
- `src/notifications/payoff_chart.py` — `build_and_send_ic_payoff` gains `iv_by_leg`,
  `mid_by_leg`, and computes `t0_series` / `sigma` / `pop` internally (so call sites stay
  thin), or accepts them precomputed — pick one and be consistent. Recommended: the helper
  takes `chain` + `atm_iv` + `dte` and does the pricing itself, still swallowing every error.
- `scripts/strategies/ic/paper_ic_entry.py`, `paper_ic_entry_v2.py` — pass the chain / IV.

**What to implement:** extend the helper so that, given the chain (or per-leg IV + mids) and
`dte`, it computes `sigma = expected_move(spot, atm_iv(chain), dte)`,
`pop = pop_between(spot, payoff.lower_breakeven, payoff.upper_breakeven, dte, atm_iv(chain))`,
and `t0_series = t0_pnl_series(...)`, then calls the extended renderer. Any of the three
failing → that element is `None`, the chart still sends. Update the two entry call sites to
pass the extra context (they already hold the fetched chain).

**Tests:** extend the entry-script tests — assert the photo still sends when the chain has
usable IV, and still sends (expiry-only) when IV is all zero and unsolvable.

**Commit:** `feat(scripts): add model overlay to IC entry payoff charts`

---

## MO-8 — Thread inputs through EOD snapshot + close paths

**Files to change / create:**
- `scripts/strategies/ic/paper_ic_snapshot.py` — `process_variant` passes the chain + `dte`.
- `src/strategy/ic_nifty_v1.py`, `src/strategy/ic_nifty_v2.py` — `_send_close_notification`
  passes the chain + `dte`.
- extend the respective tests.

**What to implement:** the same additive change at three call sites — hand
`build_and_send_ic_payoff` the chain (already in scope in all three), `dte`, and let it do
the overlay pricing. No new fetches. One commit (additive, low risk) unless the diff argues
for splitting.

**Review:** `greeks-analyst` — blocking (all three touch strategy / option-chain paths).

**Tests:** extend PC-12 / PC-13 / PC-14's tests to assert the overlay args reach the renderer
and a zero-IV chain degrades to the expiry-only chart.

**Commit:** `feat(strategy): add model overlay to IC EOD + close payoff charts`

---

## MO-9 — Docs close (epic complete)

**Files to change / create (targeted `Edit` only):**
- `CONTEXT.md` — add `src/pricing/expected_move.py` (+ any sibling helper) to "What Exists".
- `DECISIONS.md` — entry: the model overlay shipped; `greeks-bs-fallback/` dependency was
  satisfied by GF-2 + GF-3; note the inherited modeling constants.
- `TODOS.md` — Session Log line; **delete** the `ic-payoff-charts/` line from
  `## Feature Backlog` and append it to `docs/archive/TODOS_ARCHIVE.md` under a dated
  heading.
- `docs/plan/README.md` — collapse the `ic-payoff-charts/` epic entry to a one-line
  `✅ Archived → docs/archive/plan/ic-payoff-charts/` pointer.
- `docs/plan/ic-payoff-charts/README.md` — **Stories** table: both rows ✅ + closing SHAs.
- `git mv docs/plan/ic-payoff-charts/ docs/archive/plan/ic-payoff-charts/` — same commit.
- Re-index the graph.

**Tests:** none. Run `python -m pytest tests/unit/ --tb=no -q` — green.

**Commit:** `docs(plan): close and archive ic-payoff-charts epic`
