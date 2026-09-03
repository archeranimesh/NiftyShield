# NiftyShield — AI Assistant Pre-Task Protocol (Antigravity autoload)

> Auto-loaded at session start by tools that discover `AGENTS.md` by name (Antigravity).
> Every step is mandatory.
>
> **This file mirrors `CLAUDE.md`** — the two are kept equivalent on purpose. `CLAUDE.md` is
> the canonical copy; when it changes, this file is re-synced (see the `md-organize` skill,
> Step 7).
> `ANTIGRAVITY.md` holds the tool-level operating rules specific to Antigravity (file-edit
> tools, isolated shell, approval gates) — read it too.
>
> This file holds only what a session needs **before it can act**. Reference material — the
> Council Decision Protocol, the Quick reference table, the AI-collaboration workflow, the
> review/handoff rules, and the module `CLAUDE.md` index — lives in the **`protocol-reference`
> skill** (`.claude/skills/protocol-reference/SKILL.md`). Deferred, not downgraded: read it
> when a step below points there.
>
> **Antigravity deltas** (the only places behaviour differs from `CLAUDE.md`):
> - You cannot spawn `.claude/agents/*` sub-agents. Where the protocol says "spawn agent X",
>   emit the await-signal and hand to a human / Claude — see *Agent AutoTrigger Rules* below
>   and `ANTIGRAVITY.md` §"Commit Protocol".
> - File edits use `multi_replace_file_content` (not `Edit`) and `write_to_file` for new
>   files only — see `ANTIGRAVITY.md` §"File Editing Rules".
> - `run_command` runs in an isolated `bash -c`; no shell inheritance, no persisted cwd,
>   `.env` not auto-loaded, state-mutating commands block for approval — see `ANTIGRAVITY.md`
>   §"Environment & Safety Rules".
> - No `/work` skill. Where `CLAUDE.md` says "invoke `/work`", do the feature/bug routing by
>   hand — see Step 1 below.
> - No skill-invocation mechanism. Where `CLAUDE.md` says "invoke `protocol-reference`", read
>   `.claude/skills/protocol-reference/SKILL.md` directly.

---

## ⛔ Rule 0 — Graph before Read (enforced by PreToolUse hook)

**NEVER read a file under `src/` or `scripts/` without first trying the graph.**
A hook will fire and remind you. It will not block — the decision is yours — but skipping the
graph when it can answer the question wastes tokens and violates this protocol.

**Decision tree — run in order before any source file touch:**
0. "Why does this look like this?" / "What changed recently?" →
   `git log --oneline -10 <file>` (~20 tokens).
   The `Why:` line in each commit encodes intent — often answers the question without reading
   any code at all.
   `git show <sha>` for full diff; `git log --oneline -20` for recent session history.
   **Run this before the graph for any question about intent or recent change.**
1. Need a symbol/function? → `search_graph(query=...)`, then
   `bash python -m scripts.dev.graph_snippet <qualified_name>` — a thin wrapper that
   strips the `fp`/`sp`/`bt` fingerprint fields (~244 tokens/call) the raw
   `get_code_snippet` MCP tool returns unused (`--neighbors` and `--project` pass through).
2. Need callers/callees? → `trace_path(function_name)`
3. Need a grep? → `search_code(pattern)`
4. Need a specific block? → `bash sed -n 'N,Mp' <file>` (cheaper than reading the whole file)
5. Still not enough? → a full file read is permitted — but **state why** the graph was
   insufficient.

Every raw `codebase-memory-mcp` call (`search_graph`, `get_code_snippet`, `trace_path`,
`query_graph`) needs `project=Users-abhadra-myWork-myCode-python-NiftyShield` — and
`index_repository` also needs `repo_path=<abs repo path>`. Omitting it fails the call and
costs a wasted round trip. `scripts.dev.graph_snippet` defaults `--project`; a raw MCP call
does not. Full list: *Tool-call param hygiene* below.

A full file read is the *first* tool only for: markdown files, TOML/YAML config, test fixtures.

A second read of a path already read this session (with no intervening edit) is flagged by
`.claude/hooks/repeat_read.sh` — edit the copy already in context, or use `get_code_snippet` /
`sed -n 'N,Mp'` for a specific block.

---

## ⛔ Rule 1 — Bash Output Discipline

Any bash command that **reads data** (DB query, log file, test run) must pre-aggregate or
filter before output reaches Antigravity context. Raw result sets are appended to the context
window and carried for every subsequent tool call — aggregate at the source, not after.

| Query type | Required pattern |
|---|---|
| Aggregate (total P&L, portfolio value, count) | Single summary row via `SUM` / `MAX` / `COUNT` — never `SELECT *` |
| Diagnostic (which rows have null Greeks?) | Named columns + `LIMIT 10` — never full table dump |
| Test runs | `pytest --tb=no -q` for pass/fail; full `-v` only when debugging a specific failure |
| Log reads | `tail -20 logs/snapshot.log` or `grep ERROR` — never `cat` |
| Discovery `grep`/`sed`/`awk` over a file | Scope with `-c` / `sed -n 'N,Mp'` / `--include` first — an unscoped match over an >800-line file writes a huge result file (`wide_grep.sh` warns) |

Token math: `SELECT *` on a 15-row × 20-column table ≈ 300 tokens that persist all session; a
`GROUP BY / SUM` summary row ≈ 15 tokens. Reference implementation:
`get_cumulative_realized_pnl` — SQL-layer aggregation returning a compact `dict`.

**Shell mechanics.** `run_command` runs in an isolated `bash -c` with no persisted cwd and no
`.env` — pass absolute paths or `git -C <dir>` / `--` path args, never a bare `cd` expecting
it to carry to the next call. Do not rely on `$var` word-splitting for newline lists (use
`while read` / `xargs -0` / a one-shot Python filter). (The Claude-side note here reads
"session shell is zsh"; Antigravity's isolated `bash -c` is the delta.)

---

## Step 1 — Read CONTEXT.md first

**Task-shaped session: route to feature / bug and load the right prompt before any code.**
Antigravity has no `/work` skill — do the routing by hand: for a feature, take the next target
off `TODOS.md` `## Feature Backlog` (priority-ordered `1..N`); for a bug, take it from
`TODOS.md` `## Open Bugs` → `docs/bugs/` (`bugs.md` registry + `task.md` checklist). Load the
story/bug `prompt.md` + first unchecked task + `CONTEXT.md`, then follow the handoff protocol
into Step 2b below. Open-ended discussion needs no routing.

Read `CONTEXT.md` before writing any code. **State `CONTEXT.md ✓` verbatim in your first
user-facing response** — reading the file without the visible acknowledgment leaves no record
Step 1 ran. This step applies the moment code enters scope, not only at session start: an
ops / diagnostic session that turns into a `src/` change stops and reads `CONTEXT.md` before
the first edit. Do not rely on chat history — CONTEXT.md is the single source of truth.
Module tree (file-level descriptions): **`CONTEXT_TREE.md`** — load only when adding new
modules or doing a full codebase survey.

**Load additional files when relevant:**

| When | Also read |
|---|---|
| Adding/changing module architecture | `DECISIONS.md` + `CONTEXT_TREE.md` |
| Instrument keys, AMFI codes, market data | `REFERENCES.md` |
| Writing to `portfolio.sqlite`, adding a table, or unsure which table holds the data | `DB_REGISTRY.md` **first** — never assume a table is empty/missing |
| Phase 0 backtest / paper trading / strategy / `src/paper/` / `src/risk/` work | `BACKTEST_PLAN.md` (Phase 0 only, ~300 lines) |
| Phase 1+ work (only after the Phase 0.8 gate passes) | `BACKTEST_PLAN_PHASE1.md` |
| Implementing a metric / ratio / ML technique | `LITERATURE.md` entry for the cited LIT code |
| Starting a feature or picking up a story | manual routing (no `/work`) — `TODOS.md` Feature Backlog → the story's files; add `PLANNER.md` for roadmap context |
| Authoring or reviewing any task/story/spec mentioning expiry, DTE, or calendar logic | `REFERENCES.md` — expiry day changed Thursday→Tuesday, April 2026 |
| New entrypoint script, any `logger.*()` call, or touching `src/utils/logging.py` | `LOGGING.md` — canonical logging standard (see `BUG-010` in `docs/bugs/bugs.md`) |
| Building or editing any Telegram/notification message text | `src/notifications/CLAUDE.md` §"Instrument Label Formatting" |
| Formatting any value into a Telegram message (money, Greeks, strikes, %, expiries, tables) | `FORMATTING.md` — per-parameter-type standard + the escaping-boundary contract |
| Working inside `src/<module>/` | that module's `CLAUDE.md`, read explicitly — autoload covers only this root file |
| Reviewing or building on Antigravity's own prior work | `ANTIGRAVITY.md` |

On the `DB_REGISTRY.md` row: read it *before* concluding a table is empty or absent — see its
2026-08-07 note on `paper_nav_snapshots` vs. `paper_leg_snapshots` for the failure it prevents.

---

## Python Standards (new module checklist)

Every new Python package directory — whether under `src/`, `scripts/`, or `tests/` — **must
include an `__init__.py`**. A single comment line is sufficient. Without it:
`codebase-memory-mcp` silently skips the entire directory (all functions become invisible to
the graph), type checkers and IDEs lose symbol resolution, and `python -m <package>.<module>`
falls back to fragile namespace-package semantics.

After adding a new package, re-index: `mcp__codebase-memory-mcp__index_repository`.

---

## Logging standard (scripts/)

**Full standard: `LOGGING.md`** — read it before adding any entrypoint script or `logger.*()`
call. It covers the required line shape, event-naming convention, the `setup_logging()`
entrypoint rule, and why raw `print()` / bare stdlib `logging.getLogger()` are banned in
`src/` and `scripts/` (see `BUG-010`, `docs/bugs/bugs.md`, for the audit that found six
incompatible formats in `logs/` before this was written down).

The naming rule specific to `scripts/`, summarized for quick reference: **never** use
`structlog.get_logger(__name__)` there. When a script is run directly, `__name__ ==
"__main__"` and every log line shows `[__main__]` — losing all module context. Always declare
an explicit name:

```python
_SCRIPT_NAME = "scripts.<subdir>.<module>"   # mirrors the file path with dots
logger = structlog.get_logger(_SCRIPT_NAME)
```

Pre-commit hook `no-script-main-logger` enforces this — any `get_logger(__name__)` in
`scripts/` fails the commit. `src/` modules are fine with `__name__` because they are always
imported, never run as `__main__`.

---

## Step 2 — Confirm scope

If the prompt does not name specific files, ask before starting. One clarifying question beats
building the wrong thing. Confirm: which `src/` modules change? Which files are touched? Tests
required? (default: yes)

---

## Step 2b — Council checkpoint (planning gate, mandatory)

Before stating the implementation plan, ask: **does this task contain a decision that warrants
a council call?** A decision qualifies when **all three** hold: (1) load-bearing and costly to
reverse, (2) two defensible approaches with materially different outcomes, (3) spans multiple
disciplines simultaneously.

**If yes:** surface the decision to the user, draft the council question, recommend a
template, and wait for the council output before writing any code. The council output gates
Step 3. **If no:** proceed directly to Step 3.

Council decisions are Claude's responsibility — hand the drafted question back for a Claude
session to run; Antigravity does not trigger the council. This three-condition manual check is
the **sole source of truth** for the checkpoint — `options-strategist` is advisory-only, and a
real council call per `docs/council/README.md` always supersedes it when the three conditions
hold. This checkpoint exists only in the planning phase; never invoke the council
mid-implementation.

**Reading a council file that already exists is a separate mandatory gate — read
`.claude/skills/protocol-reference/SKILL.md` §1 before acting on any `docs/council/` output.**

---

## Step 3 — State plan, wait for go-ahead

> Plan: [one sentence] → touches [file1, file2] → tests in [test file] → commit. Proceed?

If the plan touches more than 2 files, wait for explicit go-ahead.

State the one-sentence plan and the in-scope file list **even when the prompt is highly
prescriptive** — a detailed assignment (files, commits, doc updates spelled out) is not an
explicit go-ahead, and this gate still applies. On a multi-phase story, scope only the first
unstarted phase — do not fold a later or blocked phase's decision into the opening gate. If
the file count grows past what was approved mid-execution (a rename that breaks inbound
references, a cascade), name the newly in-scope files in one line before touching them.

---

## Step 3b — Implementation routing (mandatory after go-ahead)

Decide who implements **before writing any code**. This is a fork — the two paths do not
overlap. It applies regardless of file count: a ≤2-file task still needs a routing decision,
it just skips the Step 3 go-ahead wait.

| Route to | When |
|---|---|
| **Antigravity** | Spans 3+ files with a clear, non-ambiguous spec · TDD loop needed · phase from `BACKTEST_PLAN.md` with a documented DoD · mechanical, no real-time design decisions |
| **Claude** | 1–2 file task with likely inline judgment calls · exploratory work where the spec may change · graph queries needed mid-implementation · any Step 2b council decision |

**Antigravity implements** → proceed to Step 4. The AutoTrigger gates (test-runner,
code-reviewer) still apply — since you cannot spawn `.claude/agents/*`, satisfy them via the
await-signal / human-review handoff described under *Agent AutoTrigger Rules*. Commit via the
commit skill.

**Escalate to Claude** → hand the task back for a Claude session when it needs real-time
design decisions, a council call, or graph queries mid-implementation to resolve ambiguity.
Produce a short handoff note and **stop**. Handoff-prompt requirements and the full
verification checklist: `.claude/skills/protocol-reference/SKILL.md` §3.

Settle this routing call firmly before reading `.claude/skills/handoff-antigravity/SKILL.md`
— its body (~1.5K tokens) is only useful once the decision is "Antigravity"; loading it and
then reversing to "Claude implements" is pure waste.

---

## Step 3c — Before writing code

A task spec's **"Before any code" pre-step is mandatory** — when it says read the target
source, read it (via the graph per Rule 0). You cannot tell a load-bearing invariant from
reference narration by a doc's wording alone; deciding which lines are frozen without the code
open produces a wrong trim.

**When spawning parallel file-editing subagents:** forbid every index / stash-touching git
command explicitly — not just `add` / `commit` / `stash` but `git stash`, `git restore
--staged`, anything that mutates the index — and tell each agent to compute before / after
line counts with `awk` / `grep` only. One agent running `git stash` for a line count sweeps
every other agent's concurrent edits into the stash.

---

## Step 4 — Tests are mandatory

Every public function needs one happy-path test + one error/edge-case test. No network in
tests.

**⛔ Before writing any test helper that constructs a domain model (Pydantic / dataclass):**

Never write a `_make_*` / `build_*` / fixture helper from memory. Domain models evolve —
required fields are added, enums are renamed, validators change. Writing from memory produces
helpers that fail at collection time, wasting two round-trips to diagnose errors you
introduced yourself.

Mandatory pre-step — run these before opening the test file:

```
get_code_snippet("<ModelClassName>")   # exact field list, required vs optional, types
search_graph("<EnumName>")             # every enum used in the helper — get all members
```

Concrete failures this prevents: `Direction.SHORT` does not exist (members are `BUY` /
`SELL`); `entry_date` is a required field on `Leg`, and omitting it raises `ValidationError`
at collection. One graph call before the first line of test code eliminates both. Do not skip
it.

---

## Agent AutoTrigger Rules

The conditions below require an isolated-context agent review. **Antigravity cannot spawn
`.claude/agents/*`** — for each trigger, emit the await-signal and hand to a human / Claude
reviewer per `ANTIGRAVITY.md` §"Commit Protocol". That handoff satisfies the gate; it is
human-completed, not skipped. The gate is violated only if the commit proceeds with neither a
real agent run nor a human review having occurred.

| Agent | Trigger condition | Blocking? |
|---|---|---|
| `test-runner` (Haiku) | Once per task, after code files are edited and before `code-reviewer` / the commit — not per-edit | **Yes** — must pass before proceeding |
| `code-reviewer` (Opus) | Before every commit touching code | **Yes** — CRITICAL/ERROR findings must resolve |
| `greeks-analyst` (Sonnet) | Any change to `src/paper/`, option chain parsing, or delta/gamma fields | **Yes** |
| `roll-validator` (Opus) | Any change to roll logic or `scripts/roll_leg.py` invocation | **Yes** |
| `options-strategist` (Opus) | Council checkpoint (Step 2b) when no real council is warranted | Advisory |

**"Blocking"** means the next protocol step does not proceed until the review returns clean.
For `code-reviewer`: any `CRITICAL` or `ERROR` finding must be resolved; `WARNING` may be
deferred with a documented reason in the commit message.

`test-runner` runs **once** — one authoritative green run per task, spawned when the edits are
done, not after each intermediate edit. Running `pytest tests/unit/` inline in the main
session instead of spawning the agent is flagged by `inline_full_suite.sh` (warn-only). For a
docs/tooling-only change, gate on the targeted test dir rather than the full suite.

**Financial logic commits** (Greeks, P&L, Decimal paths, BrokerClient boundaries): a real
`@code-reviewer` subagent run by a Claude session is mandatory — a persona approximation is
insufficient because it does not load `REVIEW.md` hygiene rules unless explicitly provided.
Emit `CODE REVIEW GATE — awaiting @code-reviewer via Claude` and wait.

---

## Tool-call param hygiene (MCP / AskUserQuestion / ScheduleWakeup)

Three recurring tool-call mistakes, each costing a full retry or a wasted turn:

- **`codebase-memory-mcp` first call** — pass `project=Users-abhadra-myWork-myCode-python-NiftyShield`
  on every raw call, plus `repo_path=<abs repo path>` on `index_repository`. Omitting it
  fails the call; the real call is then a second round trip. `scripts.dev.graph_snippet`
  defaults `--project` — a direct MCP call does not.
- **`AskUserQuestion`** — pass a plain `questions` array whose option/label/description fields
  are short plain strings. No `preview` fields, no `{"raw": <escaped json>}` envelope, no
  multi-line / backtick / brace content in a value — each has repeatedly failed the tool's
  JSON parse and forced a full retry. Plain array, plain strings.
- **`ScheduleWakeup`** — never schedule a wake-up to poll a subagent you spawned.
  Harness-tracked work re-invokes you automatically via task-notification on completion;
  polling burns a turn and reloads per-turn hook overhead for nothing. Just end the turn.

---

## Step 5 — Close the phase (docs → tests → commit)

A phase is not complete until all three are done. Never move to the next phase mid-checklist.

**5a — Update docs** (targeted edits only, never a full-file overwrite): `CONTEXT.md` "What
Exists" if new files were added · `DECISIONS.md` for any new architecture decision ·
`TODOS.md` to mark completed items and add a session-log entry · `docs/plan/README.md` status
column for the story/epic just touched (an epic going stale is almost always this file being
skipped — FR-7 row 15, `docs/plan/full-repo-review/findings/FR-7_synthesis.md`) · the relevant
`src/<module>/CLAUDE.md` if module invariants changed. A completed
`tasks.md` checkbox carries a `| Owner: … | Model: … | Review: … | SHA: …` tail
(`Owner`/`Model`/`Review` set at authoring time, `SHA` on the closing commit); `TODOS.md`
backlog items stay pointer-only. Full rules: `docs/plan/README.md` §Conventions.

**5b — Verify tests green:** run `python -m pytest tests/unit/ --tb=no -q` — all must pass
before committing.

**5c — Commit** (format in `.claude/skills/commit/SKILL.md`): any commit touching `.py` files
under `src/`, `scripts/`, or `tests/` requires the `code-reviewer` gate against
`git diff HEAD` — emit the await-signal and hand to Claude. Resolve every `CRITICAL` /
`ERROR`; a `WARNING` may be deferred with a documented reason. A docs/config-only diff (no
such `.py` files) skips `code-reviewer` and commits immediately after 5a. **Never bundle
changes from separate phases into one commit.** Typical phase boundaries, each getting its own
commit: Model → Store → Tracker/orchestration → Formatting / pure helpers.

**⛔ The commit must be executed, not drafted.** A written-out commit message is not a commit.
The phase is not closed until you have run:

```bash
git add <files>
git commit -m "<message>"
git log --oneline -1   # confirm SHA appears — this is the proof of completion
```

Providing the commit message to the user and stopping is a recurring failure mode. The commit
is the last mandatory action of every phase. Do not hand off to the user to run it.

**5d — Session efficiency close-out:** the `session-close` skill's audit runs at end of
session. Under Claude this is a fresh `general-purpose` subagent handed this session's own
transcript path — never `fork`, which clones the whole conversation and made this step the
single largest token cost of a session. Antigravity cannot spawn that subagent either — run
`.claude/skills/session-close/SKILL.md` inline and report its compact block, or hand to Claude
to run it. This step is never a "legitimate skip" — a read-only/query-only session still
closes with a trivial clean report, per the skill's own Step 5 fallback. See `ANTIGRAVITY.md`
§"Phase Completion Output" for the structured block Antigravity emits so Claude can verify the
phase without re-reading files.

---

## Reference material — `.claude/skills/protocol-reference/SKILL.md`

Moved out of this file to keep the resident protocol load-bearing only. Nothing here is
optional when it applies. Read that file for:

| § | Topic | Covers |
|---|---|---|
| 1 | **Council Decision Protocol** | Reading a `docs/council/` file — Stage 3 first, what to extract, the mandatory post-read `DECISIONS.md` + strategy-doc updates, Aggregate Rankings |
| 2 | **Quick reference** | The canonical file/purpose lookup table — graph project id, live DB path, cron log, exception hierarchy, fixtures, every standard doc |
| 3 | **AI Collaboration** | Claude ↔ Antigravity division of labour, the four mandatory handoff-prompt elements, Phase Completion Output verification, job-type → surface/model routing |
| 4 | **Rules for any review or handoff** | Severity by mission impact · verify your own citations · always state one perspective not covered |
| 5 | **Module `CLAUDE.md` index** | What each module's file covers |

**§1 is a gate, not a lookup** — read it whenever a `docs/council/` file is shared or
referenced, before acting on any of its content. §2–§5 are lookups: read only what you need.

---

## Module CLAUDE.md files

Working inside `src/<module>/` means reading that module's `CLAUDE.md` explicitly — Antigravity
autoload covers only this root file. Eight modules carry one: `portfolio`, `mf`, `client`,
`notifications`, `dhan`, `paper`, `nuvama`, `gamma`. Index of what each covers:
`.claude/skills/protocol-reference/SKILL.md` §5.

---

## Antigravity Reference (supplementary)

Stable, load-bearing conventions worth having inline in an autoloaded file. Everything else
is a pointer — `CONTEXT.md` / `DECISIONS.md` / `REFERENCES.md` / the module `CLAUDE.md` files
are authoritative and must not be restated here (restating invites drift).

**Decimal invariant.** All monetary fields are `Decimal`, never `float`. SQLite stores
monetary values as `TEXT`; read back with `Decimal(row["col"])`. A `float` here is silent
corruption — no exception, just wrong numbers.

**Timestamps** stored as UTC, converted to IST at the display layer only. Historical candles:
Parquet, partitioned by instrument + date.

**Async.** `asyncio` is the primary concurrency model; never mix it with blocking calls in a
hot path. CPU-bound work (backtesting, Greeks) → `ProcessPoolExecutor` dispatched from the
event loop. Every coroutine has explicit timeout handling.

**BrokerClient protocol.** Modules depend only on `src.client.protocol.BrokerClient` (or a
narrow sub-protocol), injected via the constructor. `src/client/factory.py` is the only file
in `src/` that imports a concrete client (`UpstoxLiveClient`, `MockBrokerClient`) directly —
`create_client(env)` wires `prod`/`sandbox` → `UpstoxLiveClient` (different token), `test` →
`MockBrokerClient`. Blocked methods (order exec, portfolio reads, historical candles) raise
`NotImplementedError`. Full implementation table + exception hierarchy (`BrokerError` root):
`src/client/CLAUDE.md`.

**Environment / config.** `src/config.py` `Settings(BaseSettings)` declares every env var;
`.env.example` has the annotated list. `run_command` does not auto-load `.env`. Always set
`UPSTOX_ENV` explicitly (default it to `test`). Two-token constraint: `UPSTOX_ANALYTICS_TOKEN`
(long-lived, market data) vs `UPSTOX_ACCESS_TOKEN` (daily OAuth, portfolio reads — not yet
wired) — see `src/client/CLAUDE.md`.

**Shell / DB safety.** `run_command` is isolated (no `.zshrc`, no persisted cwd), and any
write to `data/portfolio/portfolio.sqlite` must be flagged to Animesh before proposing —
never auto-run `daily_snapshot.py` / `record_trade.py` / `seed_*.py`. Full rules in
`ANTIGRAVITY.md` §"Environment & Safety Rules".

**One finding per session.** When a handover prompt points at a story file, implement only
its first unchecked item, then record + stop — full protocol in `ANTIGRAVITY.md` §"Story File
Execution Protocol" and §"Phase Completion Output".
