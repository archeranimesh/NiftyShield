
# Calendar Monthly - shared core + monthly variant — prompt

> Build the shared pure core, the strategy shell and the IC-equivalent infra wiring for the Nifty positional calendar, and ship the monthly variant on top of them.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The epic `README.md` carries the motivation and scope decisions; read it first. In short: the research spec (`~/myWork/myCode/AI/TradeResearch/findings/14ZZYoV4DBc_combined.md` (sibling repo)) defines
a net-long-vega, near delta-neutral Nifty structure with explicit entry filters, DTE-based exits and a single re-centre rule. NiftyShield has no long-vega positional track. This story builds
everything both variants need, then the monthly variant: first session after the previous monthly expiry (the Wednesday, entry at 10:30 IST), sell next month's ATM straddle, buy far-month OTM wings
from the month after, ₹3,000/lot target, planned hold 7 days, hard close day 10.

## Scope guard

**In bounds:**
- New leaf package `src/nifty_calendar/` (pure core), new `src/strategy/nifty_calendar_v1.py` (shell), tests under `tests/unit/nifty_calendar/` and `tests/unit/strategy/`.
- Additive changes to shared infra only: `EntryMessage` two-expiry support, an optional `curve` argument on the payoff renderer, a calendar payoff adapter, `payoff_registrations.py`,
  `monitor_daemon.py` registration, EOD summary pick-up.
- New entrypoints `scripts/strategies/nifty_calendar/` (entry, EOD snapshot).

**Out of bounds:**
- Any edit to `ic_nifty_v1.py` / `ic_nifty_v2.py` or their private helpers. Do not import from them.
- Bi-weekly rules (200-point rule, same-pair redeploy, ₹1,600 target) — `calendar-biweekly/`.
- Order placement, live capital, sizing above 1 lot, an offline backtest.
- Schema changes. If CM-0 finds that cycle state cannot be derived from `paper_trades`, stop and add a `schema.md` task with Animesh's go-ahead first.

## Design review

Recorded in the epic `README.md` §Architecture and design review (SOLID triggers, leaf-package dependency direction, prior-art audit). Outcome for this story: pure core in `src/nifty_calendar/`, three
injected `Protocol` collaborators (`StructureSelector`, `ExitRule`, `CyclePolicy`), variants as frozen config plus implementers in a `dict` registry, no `if variant` branch in the shell. CM-0
re-verifies the audit against the code before CM-1 starts and amends this section if anything differs.

**CM-0 amendment (2026-10-13).** `StrategyMonitor` calls `check_signals` once per expiry group with only that expiry's chain and legs, so the shell never sees the whole structure in one call. The
shell acts only on the near-expiry call, reads all its positions from the injected `PaperStore`, and fetches the far chain through the injected broker; `StrategyMonitor` and IC stay untouched. The
pure core cannot import `src.strategy._price_utils`, so it carries its own `mid` and `spread_points`. Findings and open decisions: `stories.md` §"CM-0 findings".

## Session-start load hints

- `docs/plan/nifty-calendar/README.md` and the combined findings file above.
- `src/strategy/CLAUDE.md`, `src/paper/CLAUDE.md`, `src/notifications/CLAUDE.md`, `FORMATTING.md`, `LOGGING.md` (any script or logger call).
- `DB_REGISTRY.md` before any Store write. `REFERENCES.md` for the Tuesday expiry rule.
- `docs/refactor/design-principles.md`, `code-deduplication-and-taxonomy.md` (new seams), `code-review-checklist.md` (before commit).
- Every domain-model test helper: `get_code_snippet` on the model and `search_graph` on its enums first (CLAUDE.md Step 4).

## Task overview

CM-0 audit and readiness probe · CM-1 models and payoff maths · CM-2 structure selector · CM-3 cycle calendar and variant config · CM-4 monthly exit rule · CM-5 strategy shell · CM-6 Telegram messages
and payoff chart · CM-7 scripts, daemon and EOD wiring · CM-8 close-out docs and cutover note · CM-9 swap the interim pricer for `src/pricing` (blocked on `greeks-bs-fallback` GF-2/GF-3). CM-1 to CM-4
are pure and spec-complete, so they are routed to Antigravity; CM-0 and CM-5 to CM-8 involve judgment calls against live infra, so they are Claude's.

## Definition of done

All tasks ticked with SHAs; `python -m pytest tests/unit/ --tb=no -q` green; a paper monthly cycle can be entered and closed by the monitor daemon against `MockBrokerClient` fixtures, producing the
trades, NAV and leg snapshots, margin snapshot, entry and close Telegram text and a payoff chart (interim Black-76 pricer) as IC produces; docs updated per CLAUDE.md Step 5a.

## Perspectives not covered

No adversarial read of the strategy's edge itself: the source is a single unaudited live log, and a paper track over a few months cannot distinguish skill from one calm regime. The tail risk (gap
through both wings, as in the presenter's ~800-point event) is only partly covered because wings are the sole protection and margin for the winged structure is unknown until CM-0 checks it.
