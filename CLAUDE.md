# NiftyShield — AI Assistant Pre-Task Protocol

> Auto-loaded at session start. Every step is mandatory.

---

## Step 1 — Read CONTEXT.md first

Read `CONTEXT.md` before writing any code. State `CONTEXT.md ✓` in your first response.
Do not rely on chat history — CONTEXT.md is the single source of truth.

**Load additional files when relevant:**
- Adding/changing module architecture → also read `DECISIONS.md`
- Touching instrument keys, AMFI codes, market data → also read `REFERENCES.md`
- Starting a new feature → also read `TODOS.md` + `PLANNER.md`
- Working inside `src/<module>/` → that module's `CLAUDE.md` loads automatically

## Step 2 — Confirm scope

If the prompt does not name specific files, ask before starting. One clarifying question beats building the wrong thing.

Confirm: which `src/` modules change? Which files are touched? Tests required? (default: yes)

## Step 3 — State plan, wait for go-ahead

> Plan: [one sentence] → touches [file1, file2]. Tests in [test file]. Proceed?

If plan touches more than 2 files, wait for explicit go-ahead.

## Step 4 — Tests are mandatory

Every public function needs: one happy-path test + one error/edge-case test. No network in tests.

## Step 5 — Update docs after implementation

After any implementation, use targeted `Edit` calls (never `Write`) to update:
- `CONTEXT.md` — "What Exists" module tree if new files added
- `DECISIONS.md` — any new architecture decisions
- `TODOS.md` — mark completed items, add session log entry
- The relevant `src/<module>/CLAUDE.md` if module invariants changed

---

## Quick reference

| What | Where |
|---|---|
| Project state | `CONTEXT.md` |
| Architecture decisions | `DECISIONS.md` |
| Instrument keys / AMFI codes / API quirks | `REFERENCES.md` |
| Open TODOs + session log | `TODOS.md` |
| Multi-sprint roadmap | `PLANNER.md` |
| Strategy definitions (code) | `src/portfolio/strategies/finideas/` |
| Shared DB connection | `src/db.py` |
| Exception hierarchy | `src/client/exceptions.py` |
| API fixtures | `tests/fixtures/responses/` |
| Live DB | `data/portfolio/portfolio.sqlite` |
| Cron log | `logs/snapshot.log` |
| Run all tests | `python -m pytest tests/unit/` |
