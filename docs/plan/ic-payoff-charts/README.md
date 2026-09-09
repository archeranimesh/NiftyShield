# IC Payoff Charts — epic index

> Attach a Stockmock-style payoff diagram — one PNG per Iron Condor variation — to the
> Telegram messages that already carry each position through its lifecycle: at entry, in the
> daily EOD audit, and at close. It is one epic rather than one story because the full-parity
> chart (blue T+0 curve, ±1σ/±2σ bands, POP) needs a Black-Scholes pricer + implied-vol
> solver that a *separate* not-yet-started story (`greeks-bs-fallback/`) already owns, so the
> model-driven overlay is split off and blocked on that story while everything that needs no
> option model ships first.

## Why this epic exists

Requested by Animesh (2026-09-09 session). The IC Telegram messages are text-only today — leg
tables, Greeks, captured-credit %. A payoff diagram gives an at-a-glance read of where spot
sits relative to the breakevens and short strikes and how much of the credit is banked. The
reference is Stockmock's "Payoff Chart" tab: expiry payoff trapezoid, a T+0 mark-to-market
curve, ±1σ/±2σ expected-move bands, and a stat header (Max Profit, Max Loss, R:R, POP, Net
Credit, Breakevens, Est. Margin).

Nothing in the repo sends images (every Telegram path is text-only `sendMessage`) or plots
anything (no matplotlib). The full-parity chart also needs per-leg option pricing on a
non-expiry date, which needs a Black-Scholes model — and Upstox returns `iv = 0.0` on every
strike for the yearly/leaps bucket, so an implied-vol solver is required to cover all
variations. That pricer + solver is the decided scope of `greeks-bs-fallback/` (new
`src/pricing/` package), not this epic.

## Scope decisions

- **Epic with two sub-stories** (confirmed with Animesh, 2026-09-09). `chart-core/` — the
  expiry payoff chart + image-send plumbing + lifecycle wiring, no option model, ships
  immediately. `chart-model-overlay/` — the T+0 curve + σ bands + POP, blocked on
  `greeks-bs-fallback/`.
- **One PNG per IC variation** (confirmed) — a separate photo after each variation's text
  report, not a combined image and not a Telegram media group.
- **Full parity with the Stockmock reference** is the target for the finished epic (confirmed).
- **The three modeling decisions** the overlay needs — risk-free rate, time-to-expiry
  convention, delta tolerance — are **owned by `greeks-bs-fallback/` GF-1** and inherited
  here, not re-decided (confirmed, 2026-09-09).
- **Tasks kept small** — 1–2 files each (confirmed) — hence 15 tasks in `chart-core/` and 9
  in `chart-model-overlay/` rather than a handful of large ones.
- **matplotlib** is the plotting library (confirmed). Agg backend, render to an in-memory
  PNG buffer. No `scipy` — `math.erf` covers the normal CDF.
- **Est. Margin** is shown only when a `MarginSnapshot` exists for the strategy — it is
  captured post-entry and OAuth-token-gated, so it is absent at entry and that stat is
  simply omitted then.
- **No DB schema change** — this epic only reads existing tables. No `schema.md`.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `chart-core/` | IC payoff math + matplotlib expiry-payoff renderer + `send_photo` on notifier/gateway + wire into entry / EOD snapshot / close | ⬜ Not started | — | — |
| `chart-model-overlay/` | Blue T+0 curve, ±1σ/±2σ bands, POP; thread per-leg IV + DTE through every call site | ⬜ Not started | `chart-core/` done + `greeks-bs-fallback/` GF-2/GF-3 | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view —
per-task checkboxes live only in each sub-story's `tasks.md`.

Story order is fixed and is the row order above. `chart-core/` has no external dependency and
can start now. `chart-model-overlay/` must not begin until `src/pricing/black_scholes.py`
(GF-2) and `src/pricing/implied_vol.py` (GF-3) exist and `chart-core/` is complete.

## Cross-cutting constraints

- **Non-fatal send contract** (`src/notifications/CLAUDE.md`) — `TelegramNotifier.send()` /
  `TelegramGateway.send_notification` are called from `try/except` throughout the strategy
  layer; a notification failure must never raise into strategy logic. `send_photo` inherits
  this exactly: a failed photo send logs a warning and returns, never raises.
- **Chart send is additive, never a replacement** — the existing text message is unchanged;
  the PNG is a follow-up send. `sendPhoto`'s caption cap is 1024 chars, well under the
  current message sizes, so the photo carries a short caption or none.
- **The renderer degrades, never errors** — a missing spot, missing DTE, missing margin, or
  (in the overlay) an unsolvable IV drops that one element from the chart; the expiry payoff
  trapezoid always renders.
- **`Decimal` for money** in the payoff math (`src/strategy/payoff.py`). The pricing helpers
  (`src/pricing/`, overlay only) are `float` by the `greeks-bs-fallback/` decision — charting
  and probability only, never a persisted money path.
- **Message budget** — `TelegramNotifier`'s per-session budget (default 10) must not let
  photos starve text in the EOD snapshot run (~8 variants → ~8 text + ~8 photos). PC-8
  addresses this.
- **`greeks-analyst` is a blocking review gate** for every task that touches
  `paper_ic_snapshot.py`, the `IronCondor*` strategy classes, or option-chain IV.

## Supersession / coordination

- **`greeks-bs-fallback/`** — hard dependency for `chart-model-overlay/`. That story builds
  `src/pricing/black_scholes.py` (GF-2: call/put price + delta) and `src/pricing/implied_vol.py`
  (GF-3: Newton-Raphson IV solver). The overlay consumes both. Before starting any `MO-*`
  task, confirm GF-2 and GF-3 are ticked in `docs/plan/greeks-bs-fallback/tasks.md`. Do not
  build a second pricer here.
- **`paper_ic_snapshot.py` dead-query cleanup** — `TODOS.md ## Feature Backlog` item 15
  ("Fix dead IC EOD report query") touches the same file PC-12 wires into. Unrelated change;
  if item 15 lands first, rebase PC-12 onto it, otherwise ignore.
- **`morning_signal.py`** is *not* in scope — it produces a directional signal with a single
  strike, not an IC structure, and has no legs to chart.

## Epic done when

- **`chart-core/`** — `src/strategy/payoff.py` computes `ICPayoff` (max profit / max loss /
  both breakevens / R:R) with tests; `src/notifications/payoff_chart.py` renders the expiry
  payoff PNG (trapezoid + fills + breakeven/short-strike verticals + spot line + current-P&L
  dot + stat strip) via matplotlib Agg; `TelegramNotifier.send_photo` + `TelegramGateway.send_photo`
  exist, are non-fatal, and honour the message budget; the shared `build_and_send_ic_payoff`
  helper is wired into both entry scripts, the EOD snapshot per-variant loop, and both close
  notifications; the docs-close task records the new modules and the matplotlib dependency.
- **`chart-model-overlay/`** — the same renderer additionally draws the blue dashed T+0 P&L
  curve (per-leg Black-Scholes at `dte/365`, solved IV where Upstox gives 0), the ±1σ/±2σ
  vertical lines + shaded bands, and shows POP in the stat strip; per-leg IV + DTE are
  threaded through every call site; every new element degrades cleanly when its input is
  missing; the docs-close task records the `greeks-bs-fallback/` dependency as satisfied.

## Conventions

Same as `docs/plan/README.md` §Conventions. This is an epic root: `prompt.md` here is the
**router** (`/work` loads it, not a sub-story `prompt.md`) and walks `chart-core/` then
`chart-model-overlay/` for the first unchecked box, with the Owner / Model / Review routing
check built in. Each sub-story folder carries `prompt.md` (session entry point), `tasks.md`
(first-unchecked-box protocol, one canonical `| Owner | Model | Review | SHA` line per task),
and `stories.md` (per-task implementation spec). No `schema.md` — the epic changes no DB
schema.
