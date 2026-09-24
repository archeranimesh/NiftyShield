# MVP — prompt

> Multi-bagger Value Picks Tracker: record tipster/analyst picks, simulate a fixed-notional capital deployment per pick, and watch live prices for target/stop-loss breaches.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read `docs/plan/mvp/tasks.md`, find the first unchecked `- [ ]` line — that is your **only** task for this session. Do not
look at any other unchecked item. Do not batch or combine tasks.

**Story spec:** Read the matching story in `docs/plan/mvp/stories.md` (same task ID) for the full implementation spec, "Before any code" graph queries, test list, and commit message. Follow it
exactly.

**Pre-implementation gate:** State in one sentence which task you are implementing (ID + one-line description), which files will change, and which test file covers it. Do not write any code until this
plan is stated.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first trying the graph. Order: `git log --oneline -10 <file>` for intent → `search_graph` / `get_code_snippet` for symbols
→ `trace_path` for callers → `search_code` for grep → `bash sed -n 'N,Mp' <file>` for a specific block → `Read` only if all of the above are insufficient, and state why.

**Before writing any test helper that constructs a domain model:** run `get_code_snippet('<ModelClassName>')` to get the exact current field list. Never write model constructors from memory.

**Implementation:** Follow all rules in `CLAUDE.md` and `REVIEW.md`. Every public function needs one happy-path test and one edge/error test. No network calls in tests. Monetary fields are always
`Decimal`, stored as TEXT in SQLite — never float.

**Test gate — blocking:** After implementation, before touching anything else, run `python -m pytest tests/unit/ --tb=no -q`. All tests must be green. If any fail, fix them before proceeding. Do not
skip this step.

**Commit:** Use the commit format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it and hand it to the user to run. The commit must land:
```
git add <files>
git commit -m '<message>'
git log --oneline -1
```

**Verify and record:** Copy the SHA from `git log --oneline -1`. Open `docs/plan/mvp/tasks.md`, change `- [ ]` to `- [x]` on the completed line, and append `| SHA: <sha>`. Then add one line to
`TODOS.md` under the session log: `- [YYYY-MM-DD] MVP <task-id> — <one-line description> — <SHA>`.

**Stop.** You are done. Do not proceed to the next unchecked item. The next session will pick up from the next unchecked box.

## Why this story exists

Tipster/analyst stock picks (from TV, Telegram, YouTube channels) are currently tracked informally with no systematic record of entry, target, stop-loss, or realized outcome. This story builds a
standalone module (`src/mvp/`, `scripts/mvp.py`, `scripts/mvp_watch.py`) that records picks per provider/category, simulates a fixed ₹1,00,000 notional deployment per pick (lump-sum in the M-A pass,
staggered 4-tranche ladder in M-B), watches live LTP hourly for target/stop-loss/hard-stop breaches, and reports P&L and benchmark alpha via Telegram. Scope and the capital-deployment framing were
resolved with Animesh on 2026-09-09 and refined 2026-09-18 (see the "Design decisions" block in `tasks.md`).

## Scope guard

In bounds: `src/mvp/` (models, store, tracker, backfill), `scripts/mvp.py`, `scripts/mvp_watch.py`, and their unit tests. Changes `data/portfolio/portfolio.sqlite` via five new tables (`schema.md`) —
additive only, no existing table touched. Out of bounds: no `BrokerClient` execution path, no live capital, no changes to any other strategy module. Shared pool / concurrent-position cap across picks
is explicitly out of MVP scope (independent ₹1L notional per pick only). M6 (historical backfill) is Good-to-Have, gated on a new M0 (equity/NIFTY bhavcopy ingest) and out of scope until M5 ships.

## Session-start load hints

`schema.md` — read before any `MVPStore` work; carries the full DDL for all five tables (`mvp_providers`, `mvp_categories`, `mvp_recommendations`, `mvp_tranches`, `mvp_snapshots`). `FORMATTING.md` —
Telegram value/table formatting conventions for M2.2/M4.2. `REFERENCES.md` — instrument key / AMFI code lookups if `InstrumentLookup` resolution needs it. The "Design decisions" block at the top of
`tasks.md` — resolved 2026-09-18, must be read before starting M1 (schema/models rewrite against the capital-deployment framing).

## Task overview

M1.1 data models · M1.2 store init_db + provider/category CRUD · M1.3 store pick CRUD + snapshots · M2.1 `check_prices` pure logic · M2.2 `format_telegram_summary` · M3.1 CLI provider/category
subcommands · M3.2 CLI add/update/close · M3.3 CLI list/summary · M4.1 `mvp_watch.py` LTP fetch + snapshot + auto-close · M4.2 `mvp_watch.py` Telegram alerts · M5 docs close · M0 equity/NIFTY bhavcopy
ingest (M6 prerequisite only) · M6 historical backfill (Good-to-Have, blocked on M0). Full detail per task: `stories.md`.

## Definition of done

M1–M5 shipped: models, store, pure tracker logic, CLI (provider/category/add/update/close/ list/summary), and the hourly watch cron all implemented with tests green, docs updated (`CONTEXT.md`,
`DECISIONS.md`, `TODOS.md`). M-A (lump-sum fill) is the ship bar; M-B (tranche ladder) and M6 (backfill) are follow-on work appended once M-A lands.

## Perspectives not covered

No review of how tipster picks are sourced/ingested into the system (manual CLI entry only in this story — no scraping or feed integration). No load-testing of the hourly watch cron at scale (assumes
a small personal watchlist, not hundreds of picks).
