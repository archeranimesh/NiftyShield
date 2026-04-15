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

**Before opening any source file — use these tools first to reduce token usage:**

**codebase-memory-mcp (graph-first):** The entire `src/` and `scripts/` tree is indexed. Query the graph before reaching for `Read`. Key calls:
- `search_graph(query=...)` — find a symbol by name or natural language
- `get_code_snippet(qualified_name)` — read only the target function, not the whole file
- `trace_path(function_name, direction="outbound")` — full call graph without reading source
- `search_code(pattern)` — grep enriched with structural ranking in one call
Fall back to `Read` only for files the graph cannot resolve: markdown, config, test fixtures.

**git log (commit history first):** Commit messages in this repo follow a structured format that encodes the *reason* for every change — faster than reading code cold.
- `git log --oneline -15 <file>` — what changed in a specific file and when
- `git show <sha>` — full diff + intent for any commit
- `git log --oneline -20` — recent session history across the whole repo
Check git log before asking "why does this code look like this?" — the answer is usually in a commit message.

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

## Module CLAUDE.md files (auto-loaded when working in that directory)

| Module | Context file |
|---|---|
| `src/portfolio/` | Leg/Trade distinction, Decimal invariant, `apply_trade_positions()`, strategy_name constraint |
| `src/mf/` | Transaction ledger model, AMFI source, Decimal TEXT invariant, MFHolding location |
| `src/client/` | BrokerClient protocol rule, 4 implementations, blocked methods, two-token constraint |
| `src/notifications/` | Non-fatal contract, `build_notifier()` → None, HTML parse_mode |
| `src/dhan/` | LTP via Upstox batch, two-phase fetch, classification config, double-count prevention |
