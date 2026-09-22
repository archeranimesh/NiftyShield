# Chart Core — prompt

> Deliver the expiry-payoff PNG for an Iron Condor, the Telegram image-send plumbing, and the wiring that attaches one chart per IC variation at entry, in the daily EOD audit, and at close. No option
> pricing model — that is `chart-model-overlay/`.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The IC Telegram messages (entry confirmation, EOD audit, close notification) are text-only. Animesh wants a Stockmock-style payoff diagram attached, one PNG per IC variation, across the whole position
lifecycle. This story builds everything that needs no option model: the payoff math, the matplotlib renderer for the expiry trapezoid + stat strip, `sendPhoto` support on `TelegramNotifier` /
`TelegramGateway`, and the three wire-ins. The T+0 curve, σ bands, and POP are split into `chart-model-overlay/` because they depend on the `greeks-bs-fallback/` pricer.

## Scope guard

**In bounds:** new modules `src/strategy/payoff.py` and `src/notifications/payoff_chart.py`; `send_photo` on `src/notifications/telegram.py` + `src/notifications/telegram_gateway.py` (+ `protocol.py`
if the close path type-checks against `NotificationGateway`); the message- budget adjustment; additive edits to `scripts/strategies/ic/paper_ic_entry.py`, `paper_ic_entry_v2.py`,
`paper_ic_snapshot.py`, and `_send_close_notification` in `src/strategy/ic_nifty_v1.py` + `ic_nifty_v2.py`; `requirements.txt` (add `matplotlib`).

**Out of bounds:** any Black-Scholes / IV / probability code (that is `src/pricing/`, owned by `greeks-bs-fallback/`); the *content* or layout of the existing text messages; the
`paper_ic_monthly_comparison.py` report; `morning_signal.py`; any DB schema change; the `paper_ic_snapshot.py` dead-query cleanup (`TODOS.md` backlog item 15 — unrelated).

Changes `src/` and `scripts/` behaviour (adds a photo send). Not docs/tooling only.

## Session-start load hints

- `src/notifications/CLAUDE.md` — the non-fatal send contract and instrument-label rules.
- `FORMATTING.md` — for any money / Greek / strike / % value rendered into the stat strip or the photo caption, and the escaping-boundary contract.
- `LOGGING.md` — any new `logger.*()` call in the new modules or the wired scripts.
- No `schema.md` — this story changes no DB schema.

## Task overview

- **PC-1** — Scaffold this epic folder (done in the authoring commit).
- **PC-2** — `ICPayoff` dataclass + `compute_ic_payoff`.
- **PC-3** — `expiry_pnl_at` + `expiry_pnl_series`.
- **PC-4** — `render_expiry_payoff_png` (trapezoid + fills + verticals + spot line + current-P&L dot) + matplotlib dep.
- **PC-5** — Stat strip on the chart (Max P/L, R:R, Net Credit, Breakevens + %, Margin if given).
- **PC-6** — `TelegramNotifier.send_photo` (multipart `sendPhoto`).
- **PC-7** — `TelegramGateway.send_photo` (+ protocol if needed).
- **PC-8** — Message-budget fix so photos do not starve text in the EOD run.
- **PC-9** — Shared `build_and_send_ic_payoff` helper.
- **PC-10** — Wire entry V1 (`paper_ic_entry.py`).
- **PC-11** — Wire entry V2 (`paper_ic_entry_v2.py`).
- **PC-12** — Wire EOD snapshot (`paper_ic_snapshot.py` `process_variant`).
- **PC-13** — Wire close V1 (`ic_nifty_v1.py` `_send_close_notification`).
- **PC-14** — Wire close V2 (`ic_nifty_v2.py` mirror).
- **PC-15** — Docs close.

## Definition of done

Mirrors `tasks.md` "## Story done when". In short: the expiry payoff PNG renders from real position data, is sent as a follow-up photo at all three lifecycle points (one per variation), the send is
non-fatal and budget-safe, and the docs record the new modules + dependency.

## Perspectives not covered

- **Visual design review on-device.** The task specs fix the chart's *elements* but not its exact colours, font sizes, or layout proportions against the Stockmock reference — that needs Animesh
  eyeballing a real PNG on Telegram (the verification step). A follow-up tweak task may be filed after the first real send.
- **Rendering latency in the monitor daemon.** `_send_close_notification` runs inside the 90-second `StrategyMonitor` tick; a matplotlib import + render adds ~0.5–1s. Believed acceptable (close is not
  latency-critical and the import is one-time) but not measured.
