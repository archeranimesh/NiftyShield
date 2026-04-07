# NiftyShield — AI Assistant Pre-Task Protocol

> This file is auto-loaded at session start. Follow this protocol before any code change.

---

## Step 1 — Read CONTEXT.md first

Always read `CONTEXT.md` before writing any code or making any file changes.
State `CONTEXT.md ✓` in your first response to confirm it has been read.
Do not rely on chat history or session summaries — CONTEXT.md is the single source of truth.

## Step 2 — Confirm scope before starting

If the prompt does not name specific files or modules, ask before starting.
Do not infer scope from vague descriptions. One clarifying question is better than
building the wrong thing.

Minimum scope to confirm:
- Which `src/` module(s) are being added or changed?
- Which existing files are touched?
- Are new tests required (default: yes, always)?

## Step 3 — State your plan in one sentence

Before writing any code, state what you will build and which files will change.
If the plan touches more than 2 files, wait for explicit go-ahead before proceeding.

Format:
> Plan: [what is being built] → touches [file1, file2]. Tests in [test file]. Proceed?

## Step 4 — Test coverage is not optional

Every implementation must include offline unit tests. Default coverage if not specified:
- One happy path test per new public function
- One error/edge case per new public function
- No network calls in tests — use fixtures or mocks

## Step 5 — Update CONTEXT.md after implementation

After completing any implementation:
- Add new architectural decisions to the "Architecture Decisions" section
- Update "What Exists" if new modules/files were added
- Update "What Does NOT Exist Yet" to remove completed items
- Add a session log entry
- Use targeted `Edit` calls — never rewrite CONTEXT.md with `Write`

---

## Current constraints (check before suggesting any approach)

| Constraint | Impact |
|---|---|
| Order execution blocked (static IP required) | All order logic via MockBrokerClient only |
| Expired Instruments API blocked (paid tier) | No backtesting against expired option contracts |
| Greeks columns null in DB | `_fetch_greeks()` is a no-op until OptionChain model is defined |
| `upstox_market.py` violates BrokerClient protocol | Do not add further modules depending on it directly |

---

## Quick reference — key paths

| What | Where |
|---|---|
| Authoritative project state | `CONTEXT.md` |
| Immediate TODOs (priority order) | `CONTEXT.md` → Immediate TODOs |
| Strategy definitions | `src/portfolio/strategies/finideas/` |
| Shared DB connection | `src/db.py` |
| Exception hierarchy | `src/client/exceptions.py` |
| API fixtures | `tests/fixtures/responses/` |
| Live DB | `data/portfolio/portfolio.sqlite` |
| Cron log | `logs/snapshot.log` |
| Run all tests | `python -m pytest tests/unit/` |
