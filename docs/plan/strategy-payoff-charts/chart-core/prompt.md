# Chart Core — prompt

> Deliver a strategy-agnostic expiry-payoff PNG, an opt-in registry so any strategy can get one by registering itself, the Telegram image-send plumbing, and the wiring that attaches one chart per Iron
> Condor variation at entry, in the daily EOD audit, and at close. No option pricing model — that is `chart-model-overlay/`.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The paper-strategy Telegram messages (entry confirmation, EOD audit, close notification) are text-only. Animesh wants a Stockmock-style payoff diagram attached across the whole position lifecycle, for
Iron Condors first and then for any strategy with minimal effort: **registering a strategy should be all it takes to start getting its chart.** This story builds everything that needs no option model:
the generic payoff math, the matplotlib renderer for the expiry payoff + stat strip, the opt-in registry and non-raising `send_payoff_chart` entry point, `sendPhoto` support on `TelegramNotifier` /
`TelegramGateway`, and the Iron Condor registration + wire-ins. The T+0 curve, σ bands, and POP are split into `chart-model-overlay/` because they depend on the `greeks-bs-fallback/` pricer.

## Design decisions (confirmed with Animesh, 2026-10-03)

- **Opt-in registry, not auto-coverage.** Iron Condors register themselves as part of this story; every future strategy adds an explicit `@register_payoff(...)` during its own development. An
  unregistered strategy gets no chart and no error.
- **Acceptance structures:** Iron Condor, Cash-Secured Put, Covered Call, Collar (PC-4) — they exercise bounded, one-sided / spot-bounded-at-zero, and mixed EQ + option legs.
- **Unbounded sides are reported, not invented:** `max_profit` / `max_loss` is `None` (rendered "Unlimited") when the payoff slope past the highest strike is non-zero.

## Scope guard

**In bounds:** new modules `src/strategy/payoff.py`, `src/strategy/payoff_registry.py` and `src/notifications/payoff_chart.py`; `send_photo` on `src/notifications/telegram.py` +
`src/notifications/telegram_gateway.py` (+ `protocol.py` if the close path type-checks against `NotificationGateway`); the message-budget adjustment; IC registration in `src/strategy/ic_nifty_v1.py` +
`ic_nifty_v2.py`; additive edits to `scripts/strategies/ic/paper_ic_entry.py`, `paper_ic_entry_v2.py`, `paper_ic_snapshot.py`, and `_send_close_notification` in both IC strategy classes;
`requirements.txt` (add `matplotlib`); the recipe in `src/strategy/CLAUDE.md`.

**Out of bounds:** registering any strategy other than the two Iron Condors (CSP / CC / Collar etc. are acceptance *tests* of the math, not wired charts — each registers when its own wiring is
requested); any Black-Scholes / IV / probability code (that is `src/pricing/`, owned by `greeks-bs-fallback/`); the *content* or layout of the existing text messages; the
`paper_ic_monthly_comparison.py` report; `morning_signal.py`; any DB schema change; the `paper_ic_snapshot.py` dead-query cleanup (`TODOS.md` backlog item 15 — unrelated).

Changes `src/` and `scripts/` behaviour (adds a photo send). Not docs/tooling only.

## Session-start load hints

- `src/notifications/CLAUDE.md` — the non-fatal send contract and instrument-label rules.
- `FORMATTING.md` — for any money / Greek / strike / % value rendered into the stat strip or the photo caption, and the escaping-boundary contract.
- `LOGGING.md` — any new `logger.*()` call in the new modules or the wired scripts.
- No `schema.md` — this story changes no DB schema.

## Task overview

- **PC-1** — Scaffold this epic folder (done in the authoring commit).
- **PC-2 / PC-3** — `PayoffLeg` / `StrategyPayoff` / `compute_payoff`; `expiry_pnl_at` / `expiry_pnl_series`.
- **PC-4** — Acceptance matrix: IC, CSP, CC, Collar.
- **PC-5 / PC-6** — Generic renderer + stat strip (+ matplotlib dep).
- **PC-7 / PC-8 / PC-9** — `send_photo` on notifier and gateway; message-budget fix.
- **PC-10 / PC-11** — Opt-in registry + default adapter; `send_payoff_chart` entry point.
- **PC-12** — Hook audit (is there a central open / EOD / close hook?).
- **PC-13** — Register the Iron Condors.
- **PC-14 – PC-18** — Wire entry V1/V2, EOD snapshot, close V1/V2 (shape depends on PC-12).
- **PC-19** — Docs close + the "register a strategy" recipe.

## Definition of done

Mirrors `tasks.md` "## Story done when". In short: the payoff PNG renders from real position data for any registered strategy, both Iron Condors are registered and get one chart per variation at all
three lifecycle points, the send is non-fatal and budget-safe, a new strategy needs only a registration line, and the docs record the new modules + dependency.

## Perspectives not covered

- **Visual design review on-device.** The task specs fix the chart's *elements* but not its exact colours, font sizes, or layout proportions against the Stockmock reference — that needs Animesh
  eyeballing a real PNG on Telegram (the verification step). A follow-up tweak task may be filed after the first real send.
- **Rendering latency in the monitor daemon.** `_send_close_notification` runs inside the 90-second `StrategyMonitor` tick; a matplotlib import + render adds ~0.5–1s. Believed acceptable (close is not
  latency-critical and the import is one-time) but not measured.
- **Strike resolution for the default adapter.** `PaperPosition` carries no strike; the default adapter depends on `InstrumentLookup` resolving every held key. A delisted / unresolvable key drops that
  leg (logged), which would silently produce a wrong payoff for a partly-resolved set. PC-10 must decide whether a partial leg set aborts the chart rather than rendering a misleading one.
- **Multi-leg-group strategies.** Strategies that run several independent structures under one name (the 3-track bootstrap, overlays) may need an adapter that selects a leg group; the default adapter
  charts all open positions as one structure.
