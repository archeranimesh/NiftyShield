# NiftyShield — Antigravity Operating Protocol

> Read this file before touching any code, markdown, or terminal command.
> Cross-reference `CLAUDE.md` for full project context and `docs/antigravity/ai_collaboration_plan.md` for the Claude–Antigravity workflow division.

---

## Pre-Task Protocol (mandatory, every session)

1. Read `CONTEXT.md`. State `CONTEXT.md ✓` before proceeding.
2. **Graph before file reads (Rule 0).** For any `src/` or `scripts/` lookup, query the graph first — do not default to `view_file`:
   - Symbol / function lookup → `mcp__codebase-memory-mcp__search_graph(query=...)`
   - Specific function body → `mcp__codebase-memory-mcp__get_code_snippet(qualified_name=...)`
   - Callers / callees → `mcp__codebase-memory-mcp__trace_path(function_name=...)`
   - Pattern search → `mcp__codebase-memory-mcp__search_code(pattern=...)`
   - `view_file` on `src/` is permitted only when the graph is insufficient — state why before using it.
3. State plan in one sentence → which files change → tests required → then **wait for go-ahead** if more than 2 files are affected.
4. Load additional context when relevant:
   - Architecture change or new module → also read `DECISIONS.md` + `CONTEXT_TREE.md`
   - New feature work → also read `TODOS.md` + `PLANNER.md`
   - Phase 0 backtest / paper trading work → also read `BACKTEST_PLAN.md`
   - Instrument keys, AMFI codes, API quirks → also read `REFERENCES.md`

---

## File Editing Rules

Three tools exist. Use them precisely — the wrong tool on the wrong file is a destructive operation:

| Tool | When to use |
|---|---|
| `write_to_file` | **New files only.** Never on any existing project document. |
| `replace_file_content` | Single contiguous block replacement in an existing file. |
| `multi_replace_file_content` | Multiple non-contiguous edits across a file. Preferred for all doc updates. |

**`write_to_file` is banned on these files** — use `multi_replace_file_content` exclusively:

`CONTEXT.md`, `DECISIONS.md`, `TODOS.md`, `MISSION.md`, `CLAUDE.md`, `ANTIGRAVITY.md`, any `src/*/CLAUDE.md`

Reason: these files carry cumulative state (session logs, architecture decisions, module invariants) that cannot be reconstructed by grepping the codebase. An overwrite is permanent data loss.

---

## Non-Negotiable Code Constraints

**Decimal invariant.** All monetary fields must be `Decimal`, never `float`. SQLite stores monetary values as TEXT. Always read back with `Decimal(row["col"])`. A `float` here is silent corruption — it will not raise an exception, it will just produce wrong numbers.

**BrokerClient protocol.** Never import `UpstoxLiveClient`, `MockBrokerClient`, `UpstoxSandboxClient`, or any concrete broker implementation outside `src/client/factory.py`. All modules depend on the `BrokerClient` protocol (`src/client/protocol.py`) only. Constructor injection only.

**`__init__.py` required.** Every new package directory under `src/`, `scripts/`, or `tests/` must include an `__init__.py`. Without it, `codebase-memory-mcp` silently skips the entire directory — functions become invisible to the graph.

**Type hints and docstrings.** All public functions require type hints on every parameter and return value. Google-style docstrings on all public functions and classes.

**Test constraints.** No network calls in unit tests. Use `MockBrokerClient`. Sandbox tests are opt-in (`@pytest.mark.sandbox`). CI runs offline tests only. Every public function needs one happy-path test and one error/edge-case test.

---

## Environment & Safety Rules

**Isolated shell — no environment inheritance.** `run_command` executes as an isolated `bash -c` process. It does not inherit `.zshrc` exports, custom aliases, or any variables from your interactive shell session.

**`.env` is not auto-loaded.** Python scripts that use `python-dotenv` will load `.env` automatically. Scripts that do not must have required variables prepended explicitly.

**Always set `UPSTOX_ENV` explicitly.** Default to `test` unless Animesh explicitly instructs otherwise:

```bash
# Correct
UPSTOX_ENV=test python scripts/daily_snapshot.py

# Never do this — defaults to prod if env is not set
python scripts/daily_snapshot.py
```

**Live DB is a destructive target.** Any `run_command` that writes to `data/portfolio/portfolio.sqlite` — including `daily_snapshot.py`, `record_trade.py`, `seed_*.py` — must be flagged to Animesh before proposing. Never auto-run these.

**State-mutating commands require approval.** `run_command` will block and wait for explicit UI approval before executing `git add`, `git commit`, `git push`, DB writes, or any network call. This is a system-level gate — do not attempt to work around it.

**`run_command` does not persist working directory.** Each call executes as a fresh `bash -c` process starting at the repo root. A `cd` in one call has no effect on the next. Use absolute paths in all commands, or chain the directory change and the execution in a single call (e.g., `cd /abs/path && python -m pytest`).

---

## Commit Protocol

Execute in this exact order. A written-out commit message is not a commit — the phase is not closed until the SHA is confirmed.

1. `run_command: git diff HEAD` — review all uncommitted changes.
2. **Code-reviewer gate:**
   - **Any commit touching `.py` files** (`src/`, `scripts/`, `tests/`): **stop here**. Emit the signal:
     `CODE REVIEW GATE — awaiting @code-reviewer via Claude`. Tell Animesh to switch to Claude and run
     the real `@code-reviewer` agent against `git diff HEAD`. Do not approximate with persona adoption —
     you are a Gemini engine and cannot spawn Claude agents. Wait for Animesh to confirm the review is
     clean before proceeding to `git add`.
   - **Docs / config only** (no `.py` files changed): `view_file: .claude/agents/code-reviewer.md` +
     `view_file: REVIEW.md` — adopt the combined persona and evaluate the diff. Both files must be in
     context; REVIEW.md hygiene rules are missed without it.
3. Resolve any `CRITICAL` or `ERROR` findings before proceeding. `WARNING` findings may be deferred
   with a documented reason recorded in the commit `Why:` line.
4. `view_file: .claude/skills/commit/SKILL.md` — read the required commit format.
5. Propose `git add <files>` followed by `git commit -m "<message>"` via `run_command`. The UI will
   block for Animesh's approval before execution.
6. After approval, run `git log --oneline -1` to confirm the SHA appears — this is proof of completion.

**Never bundle changes from separate phases into one commit.** Each phase (model → store → tracker → helpers) gets its own commit.

---

## Bash Output Discipline (Rule 1)

`run_command` output is appended to the active context window and carried for every subsequent call. Aggregate at the source — never after.

| Query type | Required pattern |
|---|---|
| Aggregate (P&L, portfolio value, count) | `SUM` / `COUNT` / `MAX` — single summary row only |
| Diagnostic (which rows have null Greeks?) | Named columns + `LIMIT 10` — never `SELECT *` |
| Test runs | `python -m pytest tests/unit/ --tb=no -q` for pass/fail; add `-v` only when debugging a specific failure |
| Log reads | `tail -20 logs/snapshot.log` or `grep ERROR logs/snapshot.log` — never `cat` on log files |

`SELECT *` on a 15-row × 20-column table ≈ 300 tokens that persist all session. A `GROUP BY / SUM` row ≈ 15 tokens.


---

## Story File Execution Protocol (Single-Finding Mode)

Use this protocol whenever a handover prompt points to a story file (e.g. `docs/plan/story_audit_remediation.md`) and asks you to work the next unchecked item.

**One finding. No exceptions.**
Find the first `- [ ]` line in the story file. That is your only task. Do not look at any other unchecked item. Do not batch, combine, or preview adjacent findings regardless of how trivial they appear.

**Pre-implementation gate — state before writing any code:**
> "I am implementing finding [N] — `<one-line description>`. Files that will change: `<list>`. Tests in: `<test file>`."
Do not write a single line of code until this statement is made.

**Implementation:** Follow all rules in `CLAUDE.md` and `REVIEW.md`. Every public function touched needs one happy-path test and one error/edge-case test. Before writing any test helper that constructs a domain model, run `get_code_snippet('<ModelClassName>')` to get the exact current field list — never construct models from memory.

**Test gate — blocking:**
After implementation, before touching anything else, run:
```bash
python -m pytest tests/unit/ --tb=no -q
```
All tests must be green. Fix failures before proceeding. Do not skip this step.

**Commit:** Follow the commit format in `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it. The `Why:` line must reference the audit finding number and link to the review file. Run `git log --oneline -1` and copy the SHA.

**Record and stop:**
1. Re-read the story file (`view_file: <story_file>`) — do not rely on working memory for the current checkbox state.
2. Change `- [ ]` to `- [x]` on the completed line, appending `| SHA: <sha>`.
3. Add one line to `TODOS.md` under the session log: `- [YYYY-MM-DD] audit finding [N] — <description> — <SHA>`.
4. Commit the doc update.
5. **Stop.** You are done. Do not proceed to the next unchecked item. The next session picks up from the next unchecked box.

---

## Phase Completion Output (mandatory)

At the end of every phase, produce this structured block before stopping.
Claude uses this to verify your work without re-reading changed files.
The SHA is proof of completion; the test count is the DoD check.

```
PHASE COMPLETE
files_changed:
  - <path relative to repo root>
  - <path relative to repo root>
tests_added: <N>
tests_passing: <N of M total>
commit_sha: <7-char SHA from git log --oneline -1>
```

**How to populate:**
- `files_changed`: list every file staged in the commit (from `git diff --name-only HEAD~1`)
- `tests_added`: count of new test functions introduced this phase (`grep -c "def test_" <new test file>`)
- `tests_passing`: from `pytest --tb=no -q` final summary line (e.g. `47 passed`)
- `commit_sha`: from `git log --oneline -1` — the first 7 chars of the SHA

If any field cannot be populated (e.g. docs-only commit with no tests), state `n/a` with a one-word reason.
