# NiftyShield — AI Assistant Pre-Task Protocol

> Auto-loaded at session start. Every step is mandatory.

---

## ⛔ Rule 0 — Graph before Read (enforced by PreToolUse hook)

**NEVER call `Read` on `src/` or `scripts/` without first trying the graph.**
A hook will fire and remind you. It will not block — the decision is yours — but skipping the
graph when it can answer the question wastes tokens and violates this protocol.

**Decision tree — run in order before any source file touch:**
0. "Why does this look like this?" / "What changed recently?" → `git log --oneline -10 <file>` (~20 tokens). The `Why:` line in each commit encodes intent — often answers the question without reading any code at all. `git show <sha>` for full diff. `git log --oneline -20` for recent session history. **Run this before the graph for any question about intent or recent change.**
1. Need a symbol/function? → `search_graph(query=...)` or `get_code_snippet(qualified_name)`
2. Need callers/callees? → `trace_path(function_name)`
3. Need a grep? → `search_code(pattern)`
4. Need a specific block? → `bash sed -n 'N,Mp' <file>` (cheaper than `Read` on the whole file)
5. Still not enough? → `Read` is permitted — but **state why** the graph was insufficient.

`Read` is the *first* tool only for: markdown files, TOML/YAML config, test fixtures.

---

## ⛔ Rule 1 — Bash Output Discipline

Any bash command that **reads data** (DB query, log file, test run) must pre-aggregate or filter before output reaches Claude context. Raw result sets are appended to the context window and carried for every subsequent tool call — aggregate at the source, not after.

| Query type | Required pattern |
|---|---|
| Aggregate (total P&L, portfolio value, count) | Single summary row via `SUM` / `MAX` / `COUNT` — never `SELECT *` |
| Diagnostic (which rows have null Greeks?) | Named columns + `LIMIT 10` — never full table dump |
| Test runs | `pytest --tb=no -q` for pass/fail; full `-v` only when debugging a specific failure |
| Log reads | `tail -20 logs/snapshot.log` or `grep ERROR` — never `cat` |

Token math: `SELECT *` on a 15-row × 20-column table ≈ 300 tokens that persist all session. A `GROUP BY / SUM` summary row ≈ 15 tokens. Reference implementation: `get_cumulative_realized_pnl` — SQL-layer aggregation returning a compact `dict`.

---

## Step 1 — Read CONTEXT.md first

Read `CONTEXT.md` before writing any code. State `CONTEXT.md ✓` in your first response.
Do not rely on chat history — CONTEXT.md is the single source of truth.
Module tree (file-level descriptions): **`CONTEXT_TREE.md`** — load only when adding new modules or doing a full codebase survey.

**Load additional files when relevant:**
- Adding/changing module architecture → also read `DECISIONS.md` + `CONTEXT_TREE.md`
- Touching instrument keys, AMFI codes, market data → also read `REFERENCES.md`
- Starting a new feature → also read `TODOS.md` + `PLANNER.md`
- Any task in `src/backtest/`, `src/paper/`, `src/strategy/`, or referenced in BACKTEST_PLAN.md → also read `BACKTEST_PLAN.md`
- Backtest / paper trading / strategy research → also read `BACKTEST_PLAN.md`
- Implementing a metric / ratio / ML technique → also read `LITERATURE.md` entry for the cited LIT code
- Working a specific story → load ONLY that story file + `CONTEXT.md` + module `CLAUDE.md`
- Working inside `src/<module>/` → that module's `CLAUDE.md` loads automatically

## Python Standards (new module checklist)

Every new Python package directory — whether under `src/`, `scripts/`, or `tests/` — **must include an `__init__.py`**. A single comment line is sufficient. Without it:
- `codebase-memory-mcp` silently skips the entire directory (all functions become invisible to the graph)
- Type checkers and IDEs lose symbol resolution
- `python -m <package>.<module>` falls back to namespace package semantics (fragile)

Reminder: after adding a new package, re-index: `mcp__codebase-memory-mcp__index_repository`.

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

## Step 6 — Commit after each logical phase

Once a self-contained phase is complete (tests green + docs updated), **commit before starting the next phase**. Never bundle unrelated changes across phases into a single commit.

Identify phase boundaries in Step 3 when planning. Typical phase boundaries:
- Model → tests green → commit
- Store → tests green → commit
- Tracker/orchestration → tests green → docs updated → commit
- Formatting / pure helpers → tests green → commit

Commit format is in `.claude/skills/commit/SKILL.md`. Before each commit:
1. Run `python -m pytest tests/unit/` — all tests must pass.
2. Invoke the `code-reviewer` agent against the diff (`git diff HEAD` or staged files). It checks Decimal invariant, BrokerClient protocol, async correctness, and general Python hygiene (`REVIEW.md`). Address any `CRITICAL` or `ERROR` findings before committing. `WARNING`-level findings may be deferred with a documented reason.

If a phase touches only docs or config (no logic), skip the code-reviewer; a single commit at the end of the session is acceptable.

---

## Quick reference

| What | Where |
|---|---|
| Graph project ID | `Users-abhadra-myWork-myCode-python-NiftyShield` |
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
| Commit format | `.claude/skills/commit/SKILL.md` |
| Python review checklist | `REVIEW.md` |
| Backtest → paper → live pipeline plan | `BACKTEST_PLAN.md` |

## Module CLAUDE.md files (auto-loaded when working in that directory)

| Module | Context file |
|---|---|
| `src/portfolio/` | Leg/Trade distinction, Decimal invariant, `apply_trade_positions()`, strategy_name constraint |
| `src/mf/` | Transaction ledger model, AMFI source, Decimal TEXT invariant, MFHolding location |
| `src/client/` | BrokerClient protocol rule, 4 implementations, blocked methods, two-token constraint |
| `src/notifications/` | Non-fatal contract, `build_notifier()` → None, HTML parse_mode |
| `src/dhan/` | LTP via Upstox batch, two-phase fetch, classification config, double-count prevention |
