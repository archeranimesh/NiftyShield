Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read `docs/plan/entry-event-filter/tasks.md` and find the first unchecked box. That is your **only task** for this session.
Do not look at any other unchecked item. One task. Complete it fully. Stop.

**Story spec:** Read the matching task section in `docs/plan/entry-event-filter/stories.md` for the full spec before writing any code.

## Why this story exists

R4 (Budget/RBI MPC/election entry filter) is a TODOS.md-originated item: strategy entries taken on days that fall inside a known macro-event window (Union Budget, RBI MPC decision, general/ state
elections) carry materially different gap/vol risk than an ordinary session, and the paper-trading pipeline currently has no awareness of the calendar. This story adds that awareness as a soft warning
— logged, not blocking — so entries on event-window dates are visible in review without hard-coding a business decision to refuse them.

## Scope guard

In bounds: a new `src/market_calendar/events.yaml` data file + loader module, and a soft-warning hook into `record_paper_trade.py` mirroring the existing `GateViolation` pattern. Out of bounds: any
change to entry-gate blocking behavior (this is soft-warn only, never hard-block), any change to the holiday-calendar loader itself beyond using it as a structural reference, and any
strategy-selection or sizing logic. This is `src/` behaviour-changing work (EF-2/EF-3), not docs-only, once EF-1 unblocks.

## Session-start load hints

Module `CLAUDE.md` under `src/paper/` (for `GateViolation`) and `src/strategy/` if `ic_entry_gates.py` lives there. No `DECISIONS.md` row exists yet for this feature — EF-4 adds one only if the
soft-warning mechanism ends up diverging from `GateViolation`. No `schema.md` — this story does not touch `portfolio.sqlite`.

## Task overview

- **EF-0** — Create this story directory. Docs-only. (done)
- **EF-1** — Design the `events.yaml` schema, gated on ES12 shipping.
- **EF-2** — Implement the loader module + tests.
- **EF-3** — Wire the soft-warning into `record_paper_trade.py`.
- **EF-4** — Docs close (`TODOS.md`, `CONTEXT.md`, `DECISIONS.md` if needed).

## Definition of done

`events.yaml` exists with a documented schema; a loader under `src/market_calendar/` reads it with unit-test coverage; `record_paper_trade.py` logs a soft warning (never blocks) when an entry date
falls inside an event window; `TODOS.md`/`CONTEXT.md` reflect the shipped feature.

## Perspectives not covered

This story does not address whether the event list itself (dates, windows) should be maintainable by someone other than a developer — e.g. a config reload without a code deploy. It assumes
`events.yaml` is edited and committed like any other source file, which may not scale if event dates need frequent mid-quarter updates.

**Graph-before-Read rule:** Never call `Read` on `src/` without first using the graph. Order: `git log` → graph query → `search_code` → `sed -n` → `Read` (state why).

**Before writing any test helper that constructs a domain model:** run `get_code_snippet('<ModelClassName>')` first.

**Test gate — blocking:** `python -m pytest tests/unit/ --tb=no -q` All must be green before committing.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
