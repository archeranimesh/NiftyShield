
# Nifty Positional Calendar (monthly + bi-weekly) — epic index

> Paper-trades the TM Trading "Nifty Positional" structure (near-expiry ATM short straddle, far-expiry OTM wings) in two variants, monthly and bi-weekly, on the existing paper backbone with the same
> infra as Iron Condor (monitor, fills, snapshots, Telegram, payoff chart). One epic because both variants share one pure core and differ only in config, cycle policy and exit rules; the second story
> is deliberately thin.

## Why this epic exists

Research findings (`TradeResearch/findings/14ZZYoV4DBc_combined.md`, built from `14ZZYoV4DBc.md` and `Nifty-Positional-Option-Selling-Strategy_Deployment-Steps.md`) describe a rule-based Nifty
positional framework. It is net-long-vega and near delta-neutral, so it complements the short-vol IC/CSP book rather than duplicating it. The evidence is one trader's unaudited live log (no backtest,
win rate or sample size), so the goal here is a forward paper track that produces our own evidence, not adoption on the presenter's claims.

Where the two source videos differ, part 2 wins: what is traded is a near-month ATM short straddle with far-month OTM wings (a diagonal / far-winged iron fly), not the same-strike double calendar part
1 names.

## Scope decisions

Decided with Animesh on 2026-10-12:

- **Paper only.** No order placement, no live capital. Go-live gate and position sizing beyond 1 lot are a later council question, not this epic.
- **Two stories, one per variant** (`calendar-monthly`, `calendar-biweekly`). Because the core is shared, the monthly story builds it and the bi-weekly story adds only its config, cycle policy and
  exit rules. A separate foundation story was considered and not chosen.
- **Same infra as IC, different strategy.** Entry, exit, EOD snapshot, Telegram messages, payoff chart, margin snapshot and cross-strategy EOD summaries all reuse the existing paths. Nothing is copied
  from `ic_nifty_v2.py` and none of its private helpers are imported (see the design review).
- **Greeks availability is not a risk.** Both variants only ever use this month, next month and weeklies, all inside the ~90 DTE window where Upstox returns Greeks (Dhan is a spare for bi-weekly). The
  shell fails closed if any of the four legs lacks Greeks at entry. No BS fallback for *missing* Greeks. The far legs are repriced with an interim local Black-76 pricer in `src/nifty_calendar/` (next
  bullet).
- **Fills follow IC:** `PaperFillSimulator` (mid plus VIX-regime slippage) with a spread gate. The gate here is an absolute points-per-leg tolerance (video: 1-2 points), not IC's 5% of mid, because
  far wings are cheap.
- **Assumptions recorded, not trusted** (all config, all labelled): breach confirmation = 30-minute close beyond a breakeven; breakevens recomputed live from current IV, not frozen at entry; 1 lot;
  wing start points 600 monthly and 400 bi-weekly, symmetric put and call (Animesh 2026-10-13, from the reference trades; update if a new reference differs).
- **Out of scope:** an offline backtest of the mechanical cycle (the findings recommend one and `src/backtest` has F&O bhavcopy ingest; candidate follow-up epic); live execution; sizing; any edit to
  `ic_nifty_v1/v2.py`.

## Architecture and design review

Run against `docs/refactor/design-principles.md` and `code-deduplication-and-taxonomy.md`:

- **SRP / the "unbounded strategy file" seam.** `IronCondorV2` is 2,935 lines because variant logic accumulated inside one class (`strategy-refactor-blueprint/` is planning its decomposition). The
  shell here (`src/strategy/nifty_calendar_v1.py`) holds sequencing only. Decisions are injected `Protocol` collaborators: `StructureSelector`, `ExitRule`, `CyclePolicy`. Each is a pure function or
  small frozen class with no I/O.
- **OCP.** A variant is a frozen `CalendarVariantConfig` plus a `CyclePolicy` / `ExitRule` implementation, registered in a module-level `dict`. Adding bi-weekly edits nothing in the monthly code, and
  there is no `if variant == ...` branch in the shell. Bi-weekly-only rules (200-point rule, same-pair redeploy) live in bi-weekly implementers.
- **DIP.** The shell receives broker, `PaperStore`, notifier, simulator and the three collaborators through its constructor, typed as protocols. No collaborator is built inside it.
- **Leaf package, one-way dependencies.** The pure core lives in a new leaf package `src/nifty_calendar/` (models, payoff, selector, cycle, exit rules) that imports only `src/models` (option types),
  `src/market_calendar` and the stdlib. It never imports `src/strategy`, `src/paper` or `src/notifications`. The shell in `src/strategy/` and the scripts depend inward. The package has an
  `__init__.py`, is re-indexed in the graph, and wraps its failures in a small `CalendarError` hierarchy.
- **Prior-art audit (reuse, do not rebuild):** `PaperFillSimulator`, `PaperExecutor`, `PaperStore` (trades, NAV and leg snapshots, exit events, margin snapshot), `cycle_pnl`, `ReEntryMixin`,
  `_price_utils.resolve_price`, `src/market_calendar`, `entry_message` / `exit_message`, `payoff` registry, `StrategyMonitor` registration. **Not reusable as-is:** IC's `_mid_price` / `_spread_pct`
  are private methods on the IC class (the shared equivalent is `_price_utils.resolve_price` plus a new pure spread helper in the core); `ic_entry_gates.py` is IC-specific (IVR + a monthly DTE window)
  and `paper_ic_snapshot.process_variant` is coupled to IC classes, so NC gets its own thin entry and snapshot scripts that reuse the shared renderers (`build_leg_table`, `send_payoff_chart`).
- **Calendar payoff chart ships now with an interim pricer (Animesh, 2026-10-13).** Chart scope is what the 2026-10-13 POC (`reference/`, `scratch/chart_poc/`) showed: the near-expiry curve with far
  legs priced by Black-76, through IC's renderer, with its strike ticks, breakevens, spot, Now marker and stat header. The pricer is a small local module `src/nifty_calendar/pricing.py`, marked
  interim and swapped for `src/pricing` (`greeks-bs-fallback` GF-2/GF-3) by task CM-9 once that ships. Additive shared-infra changes only: an optional `curve` argument on the renderer (existing
  callers unchanged), a calendar adapter and registration, a header range rule for max loss and R:R, and strike-tick dedupe for a CE and PE at one strike. Still out of scope, left to
  `docs/plan/strategy-payoff-charts/chart-model-overlay/`: the T+0 line, ±σ bands, POP, OI bars and the per-leg table.
- **Known gaps in shared infra** (each is a named task, not a surprise): `EntryMessage` carries one `expiry` / `dte` and a calendar has two expiries; `DefaultPositionAdapter` charts every position as
  one intrinsic-payoff structure and never checks expiry (it raises `InvalidLegsError` only for an unknown type or an unresolved strike), so a calendar needs its own adapter or it would chart a
  misleading payoff.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `calendar-monthly/` | Shared pure core, strategy shell, IC-equivalent infra wiring, monthly variant | 🔄 In progress | — | — |
| `calendar-biweekly/` | Bi-weekly config, cycle policy, exit rules, wiring, full-cycle integration test | 🔄 In progress (CB-1, CB-2 done; CB-3..4 open) | `calendar-monthly` | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`.

## Cross-cutting constraints

- `Decimal` for all money; strategy names start with `paper_` (`paper_nifty_calendar_monthly`, `paper_nifty_calendar_biweekly`); offline-first tests with a `MockBrokerClient`.
- Nifty monthly and weekly expiry is **Tuesday** (since April 2026, `REFERENCES.md`); the cycle calendar is holiday-aware through `src/market_calendar`.
- Every new entrypoint script follows `LOGGING.md` (`_SCRIPT_NAME`, `setup_logging`). Telegram text follows `FORMATTING.md` and `src/notifications/CLAUDE.md`.
- Exit and target decisions value the position at **executable** prices (mid net of slippage), never raw LTP. Source: displayed P&L of ₹11.3k realised as ₹7-8k in the video.
- Live cron entries are not version-controlled: the wiring task documents a parallel-run-then-flip cutover instead of a same-day swap.

## Supersession / coordination

- `strategy-refactor-blueprint/` is decomposing `ic_nifty_v2.py`. This epic must not depend on any IC internals it might move, which is why only shared modules are reused.
- `yearly-overlays/`, `dhan-far-expiry-chain/` and `design-discipline/` are unrelated, but `design-discipline/` DG-gate checks apply to this epic's Design review sections.

## Epic done when

- **calendar-monthly** — the monthly variant runs end to end in paper on the monitor daemon: structure selected under the six filters, entry and close Telegram messages, payoff chart (interim pricer),
  EOD snapshot, margin snapshot, cycle P&L and EOD summary pick-up, with unit tests green and docs closed.
- **calendar-biweekly** — the bi-weekly variant does the same with its own rules, and an offline fixture test walks a full month (monthly, back-to-back bi-weeklies, monthly again) with the correct
  variant active on each date.
