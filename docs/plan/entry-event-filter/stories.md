# Entry Event Filter (R4) — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## EF-0 — Create story directory

As-built: created `docs/plan/entry-event-filter/prompt.md` + `tasks.md` as part of a batch TODOS.md reorg that split several paragraph-form Near-term Action items into story directories
(`csp-collateral-leg/`, `execution-risk-hardening/`, `monitor-and-close-hardening/`, this one, and others). No code — the story directory itself satisfied the original TODOS.md DoD for the R4 item.
Closing SHA: `0e6700d`.

---

## EF-1 — Design `events.yaml` schema

**Depends on:** ES12 shipping first — verify ES12's current status via `search_graph`/ `TODOS.md` grep before starting; if ES12 no longer exists under that name, find its current equivalent before
proceeding.

**Files to change / create:**
- `src/market_calendar/events.yaml` — new data file, schema only (no loader yet).

**Before any code (graph queries — do not write model constructors from memory):**
- `search_graph("market_calendar")` — confirm whether the module already exists and what sibling loaders (e.g. holiday calendar) look like.
- `get_code_snippet("<existing holiday-calendar loader>")` if found — match its YAML structuring conventions rather than inventing a new one.

**What to implement:**

1. Confirm ES12's shipped status before touching anything.
2. Define the YAML schema: one entry per event with `date`, `event_type` (`budget`/`rbi_mpc`/`election`/`other`), and a `window_days_before` / `window_days_after` pair controlling the soft-warn range.
3. Seed the file with known upcoming events only if the dates are already confirmed elsewhere in the repo (e.g. `REFERENCES.md`) — do not fabricate speculative dates.

**Tests:** none — schema/data-file design only, no loader code yet.

**Commit:** `docs(market-calendar): EF-1 — design events.yaml schema`

---

## EF-2 — Implement the loader

**Files to change / create:**
- `src/market_calendar/` — loader module (check existing module structure first; likely a sibling to the existing holiday-calendar loader, not a new pattern).
- `tests/unit/market_calendar/` — loader tests.

**Before any code (graph queries — do not write model constructors from memory):**
- `get_code_snippet("<ModelClassName>")` — exact field list if a dataclass/Pydantic model represents an event.
- `search_graph("market_calendar")` — confirm the sibling holiday-calendar loader's pattern before building a second one.

**What to implement:**

1. Parse `events.yaml` into typed event objects (per CLAUDE.md conventions: type hints, `frozen=True` dataclass or Pydantic model for the immutable event shape).
2. Expose a lookup: given a date, return whether it falls inside any event's warn window and which event/severity triggered it.
3. Handle a missing/malformed `events.yaml` gracefully — this must never crash the entry path.

**Tests (`tests/unit/...`, no network, no real DB):**
- `test_loader_happy_path` — a date inside a known event window returns the matching event.
- `test_loader_no_match` — a date outside every window returns no match; a malformed YAML file does not raise into the caller.

**Commit:** `feat(market-calendar): EF-2 — implement events.yaml loader`

---

## EF-3 — Wire soft-warning into `record_paper_trade.py`

**Files to change / create:**
- `scripts/record_paper_trade.py` (or current equivalent — confirm exact path via graph).
- Associated test file for the new warning path.

**Before any code (graph queries — do not write model constructors from memory):**
- `get_code_snippet("GateViolation")` (`src/paper/models.py`) — exact field list, do not invent a new warning type from memory.
- `search_graph("ic_entry_gates")` / `get_code_snippet("scripts/strategies/ic/ic_entry_gates.py")` — the established logged-not-blocking pattern to mirror.

**What to implement:**

1. At entry time, call the EF-2 loader with the entry date.
2. On a match, log a `GateViolation`-shaped soft warning (or the exact existing pattern found above) — never raise, never block the entry.
3. Do not invent a new warning mechanism if `GateViolation` already fits; if it genuinely doesn't, flag the divergence for EF-4's `DECISIONS.md` entry.

**Tests (`tests/unit/...`, no network, no real DB):**
- `test_entry_inside_event_window_warns_not_blocks` — entry succeeds, a warning is logged.
- `test_entry_outside_event_window_no_warning` — entry succeeds, no warning logged.

**Commit:** `feat(paper): EF-3 — soft-warn entries inside event windows`

---

## EF-4 — Docs close

**Files to change / create:**
- `TODOS.md` — session log entry.
- `CONTEXT.md` — module tree entry for `events.yaml` + loader.
- `DECISIONS.md` — only if the soft-warning mechanism in EF-3 diverged from `GateViolation`.

**What to implement:**

1. Add the session-log line documenting EF-1 through EF-3's shipped SHAs.
2. Add `src/market_calendar/` to `CONTEXT.md`'s "What Exists" module tree.
3. If EF-3 needed a new warning mechanism, record the decision and why `GateViolation` didn't fit.

**Tests:** none — docs-only.

**Commit:** `docs(plan): EF-4 — close entry-event-filter docs`
