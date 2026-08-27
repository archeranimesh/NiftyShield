# NiftyShield — AI Assistant Pre-Task Protocol (Antigravity autoload)

> Auto-loaded at session start by tools that discover `AGENTS.md` by name (Antigravity).
> Every step is mandatory.
>
> **This file mirrors `CLAUDE.md`** — the two are kept equivalent on purpose. `CLAUDE.md` is
> the canonical copy; when it changes, this file is re-synced (see the `md-cleanup` skill,
> Step 7).
> `ANTIGRAVITY.md` holds the tool-level operating rules specific to Antigravity (file-edit
> tools, isolated shell, approval gates) — read it too.
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

---

## ⛔ Rule 0 — Graph before Read (enforced by PreToolUse hook)

**NEVER read a file under `src/` or `scripts/` without first trying the graph.**
A hook will fire and remind you. It will not block — the decision is yours — but skipping the
graph when it can answer the question wastes tokens and violates this protocol.

**Decision tree — run in order before any source file touch:**
0. "Why does this look like this?" / "What changed recently?" → `git log --oneline -10 <file>` (~20 tokens). The `Why:` line in each commit encodes intent — often answers the question without reading any code at all. `git show <sha>` for full diff. `git log --oneline -20` for recent session history. **Run this before the graph for any question about intent or recent change.**
1. Need a symbol/function? → `search_graph(query=...)` or `get_code_snippet(qualified_name)`
2. Need callers/callees? → `trace_path(function_name)`
3. Need a grep? → `search_code(pattern)`
4. Need a specific block? → `bash sed -n 'N,Mp' <file>` (cheaper than reading the whole file)
5. Still not enough? → a full file read is permitted — but **state why** the graph was insufficient.

A full file read is the *first* tool only for: markdown files, TOML/YAML config, test fixtures.

---

## ⛔ Rule 1 — Bash Output Discipline

Any bash command that **reads data** (DB query, log file, test run) must pre-aggregate or filter before output reaches Antigravity context. Raw result sets are appended to the context window and carried for every subsequent tool call — aggregate at the source, not after.

| Query type | Required pattern |
|---|---|
| Aggregate (total P&L, portfolio value, count) | Single summary row via `SUM` / `MAX` / `COUNT` — never `SELECT *` |
| Diagnostic (which rows have null Greeks?) | Named columns + `LIMIT 10` — never full table dump |
| Test runs | `pytest --tb=no -q` for pass/fail; full `-v` only when debugging a specific failure |
| Log reads | `tail -20 logs/snapshot.log` or `grep ERROR` — never `cat` |

Token math: `SELECT *` on a 15-row × 20-column table ≈ 300 tokens that persist all session. A `GROUP BY / SUM` summary row ≈ 15 tokens. Reference implementation: `get_cumulative_realized_pnl` — SQL-layer aggregation returning a compact `dict`.

---

## Step 1 — Read CONTEXT.md first

**Task-shaped session: route to feature / bug and load the right prompt before any code.**
Antigravity has no `/work` skill — do the routing by hand: for a feature, take the next target
off `TODOS.md` "Priority-Ordered Open Work" (the first 5 items are priority-ordered); for a
bug, take it from `docs/bugs/` (`bugs.md` registry + `task.md` checklist). Load the story/bug
`prompt.md` + first unchecked task + `CONTEXT.md`, then follow the handoff protocol into
Step 2b below. Open-ended discussion needs no routing.

Read `CONTEXT.md` before writing any code. State `CONTEXT.md ✓` in your first response.
Do not rely on chat history — CONTEXT.md is the single source of truth.
Module tree (file-level descriptions): **`CONTEXT_TREE.md`** — load only when adding new modules or doing a full codebase survey.

**Load additional files when relevant:**
- Adding/changing module architecture → also read `DECISIONS.md` + `CONTEXT_TREE.md`
- Touching instrument keys, AMFI codes, market data → also read `REFERENCES.md`
- Writing to `portfolio.sqlite`, adding a new table, or unsure which table already holds data you're looking for → also read `DB_REGISTRY.md` **first** (before assuming a table is empty/missing — see its 2026-08-07 note on `paper_nav_snapshots` vs. `paper_leg_snapshots`)
- Phase 0 backtest / paper trading / strategy / `src/paper/` / `src/risk/` work → also read `BACKTEST_PLAN.md` (Phase 0 only — ~300 lines)
- Phase 1+ work (only after Phase 0.8 gate passes) → also read `BACKTEST_PLAN_PHASE1.md`
- Implementing a metric / ratio / ML technique → also read `LITERATURE.md` entry for the cited LIT code
- Starting a feature or picking up a story → manual routing (no `/work`): `TODOS.md` "Priority-Ordered Open Work" first-5 → the story's `prompt.md` / `*_tasks.md` / first unchecked task + `CONTEXT.md`; add `PLANNER.md` when multi-sprint roadmap context is needed
- Working inside `src/<module>/` → read that module's `CLAUDE.md` explicitly (autoload covers only this root file)
- Reviewing or building on Antigravity's own prior work → also read `ANTIGRAVITY.md`
- Authoring or reviewing any task/story/spec mentioning expiry, DTE, or calendar logic → also read `REFERENCES.md` (expiry day changed Thursday→Tuesday, April 2026)
- Adding a new entrypoint script, adding/editing any `logger.*()` call, or touching `src/utils/logging.py` → also read `LOGGING.md` (project root) — canonical logging standard; see `BUG-010` in `docs/bugs/bugs.md` for why it exists
- Building or editing any Telegram/notification message text (strategy close/roll/entry alerts, gate-violation alerts) → also read `src/notifications/CLAUDE.md` §"Instrument Label Formatting" — canonical instrument-label formatting rule
- Formatting any value into a Telegram message (money, Greeks, strikes, percentages, expiries, or any fenced monospace table) → also read `FORMATTING.md` (project root) — canonical per-parameter-type formatting standard, including the escaping-boundary contract

## Python Standards (new module checklist)

Every new Python package directory — whether under `src/`, `scripts/`, or `tests/` — **must include an `__init__.py`**. A single comment line is sufficient. Without it:
- `codebase-memory-mcp` silently skips the entire directory (all functions become invisible to the graph)
- Type checkers and IDEs lose symbol resolution
- `python -m <package>.<module>` falls back to namespace package semantics (fragile)

Reminder: after adding a new package, re-index: `mcp__codebase-memory-mcp__index_repository`.

## Logging standard (scripts/)

**Full standard: `LOGGING.md` (project root) — read it before adding any entrypoint script or
`logger.*()` call.** It covers the required line shape, event-naming convention, the
`setup_logging()` entrypoint rule, and why raw `print()` / bare stdlib `logging.getLogger()`
are banned in `src/` and `scripts/` (see `BUG-010`, `docs/bugs/bugs.md`, for the audit that
found six incompatible formats in `logs/` before this was written down).

The naming-convention rule specific to `scripts/`, summarized here for quick reference:

**Never** use `structlog.get_logger(__name__)` in `scripts/`. When a script is run directly,
`__name__ == "__main__"` and every log line shows `[__main__]` — losing all module context.

Always declare an explicit name:

```python
_SCRIPT_NAME = "scripts.<subdir>.<module>"   # mirrors the file path with dots
logger = structlog.get_logger(_SCRIPT_NAME)
```

Pre-commit hook `no-script-main-logger` enforces this — any `get_logger(__name__)` in `scripts/` fails the commit.

`src/` modules are fine with `__name__` because they are always imported (never run as `__main__`).

## Step 2 — Confirm scope

If the prompt does not name specific files, ask before starting. One clarifying question beats building the wrong thing.

Confirm: which `src/` modules change? Which files are touched? Tests required? (default: yes)

## Step 2b — Council checkpoint (planning gate, mandatory)

Before stating the implementation plan, ask: **does this task contain a decision that warrants
a council call?**

Check against `docs/council/README.md#when-to-trigger-the-council`. A decision qualifies when
**all three** hold: (1) load-bearing and costly to reverse, (2) two defensible approaches with
materially different outcomes, (3) spans multiple disciplines simultaneously.

**Authoritative mechanism:** this three-condition manual check is the sole source of truth for
the checkpoint. The AutoTrigger table's `options-strategist` row and
`docs/antigravity/ai_collaboration_plan.md`'s council reference both point back here rather
than restating the criteria — `options-strategist` is advisory-only, and a real council call
per `docs/council/README.md` always supersedes it when the three conditions hold.

**If yes:** surface the decision to the user, draft the council question, recommend a template,
and wait for the council output before writing any code. The council output gates Step 3.
Council decisions are Claude's responsibility — hand the drafted question back for a Claude
session to run; Antigravity does not trigger the council.

**If no:** proceed directly to Step 3.

This checkpoint exists only in the planning phase. Never invoke the council mid-implementation.

## Step 3 — State plan, wait for go-ahead

> Plan: [one sentence] → touches [file1, file2] → tests in [test file] → commit. Proceed?

If plan touches more than 2 files, wait for explicit go-ahead.

The Step 3b implementation-routing fork applies regardless of file count — it is independent
of the go-ahead gate above. A ≤2-file task still needs a routing decision; it just skips the
go-ahead wait.

## Step 3b — Implementation routing (mandatory after go-ahead)

Once go-ahead is received, decide who implements **before writing any code**.
This is a fork — the two paths do not overlap.

**Antigravity implements:**
→ Proceed to Step 4. The AutoTrigger gates (test-runner, code-reviewer) still apply — since
  you cannot spawn `.claude/agents/*`, satisfy them via the await-signal / human-review
  handoff described under *Agent AutoTrigger Rules*. Commit via the commit skill.

**Escalate to Claude:**
→ Hand the task back for a Claude session when it needs real-time design decisions, a council
  call, or graph queries mid-implementation to resolve ambiguity. Produce a short handoff
  note and stop.

**When Antigravity implements:**
- Task spans 3+ files with a clear, non-ambiguous spec
- TDD loop needed (write tests first, iterate until green)
- Phase is from BACKTEST_PLAN.md with a fully documented DoD
- Implementation is mechanical — no real-time design decisions expected

**When to escalate to Claude:**
- Single file or 2-file task where inline judgment calls are likely
- Exploratory work where the spec may change as code is written
- Any task requiring graph queries mid-implementation to resolve ambiguity
- Any decision meeting the Step 2b council criteria

## Step 4 — Tests are mandatory

Every public function needs: one happy-path test + one error/edge-case test. No network in tests.

**⛔ Before writing any test helper that constructs a domain model (Pydantic / dataclass):**

Never write a `_make_*` / `build_*` / fixture helper from memory. Domain models evolve — required fields are added, enums are renamed, validators change. Writing from memory produces helpers that fail at collection time, wasting two round-trips to diagnose errors you introduced yourself.

Mandatory pre-step — run these before opening the test file:

```
get_code_snippet("<ModelClassName>")   # exact field list, required vs optional, types
search_graph("<EnumName>")             # every enum used in the helper — get all members
```

Concrete failures this prevents:
- `Direction.SHORT` → does not exist; members are `BUY` / `SELL`
- `entry_date` → required field on `Leg`; omitting it raises `ValidationError` at collection

One graph call before the first line of test code eliminates both. Do not skip it.

## Agent AutoTrigger Rules

The conditions below require an isolated-context agent review. **Antigravity cannot spawn
`.claude/agents/*`** — for each trigger, emit the await-signal and hand to a human / Claude
reviewer per `ANTIGRAVITY.md` §"Commit Protocol". That handoff satisfies the gate; it is
human-completed, not skipped. The gate is violated only if the commit proceeds with neither a
real agent run nor a human review having occurred.

| Agent | Trigger condition | Blocking? |
|---|---|---|
| `test-runner` (Haiku) | After any code file is edited, before code-reviewer | **Yes** — must pass before proceeding |
| `code-reviewer` (Opus) | Before every commit touching code | **Yes** — CRITICAL/ERROR findings must resolve |
| `greeks-analyst` (Sonnet) | Any change to `src/paper/`, option chain parsing, or delta/gamma fields | **Yes** |
| `roll-validator` (Opus) | Any change to roll logic or `scripts/roll_leg.py` invocation | **Yes** |
| `options-strategist` (Opus) | Council checkpoint (Step 2b) when no real council is warranted | Advisory |

**"Blocking"** means the next protocol step does not proceed until the review returns clean.
For `code-reviewer`: any `CRITICAL` or `ERROR` finding must be resolved; `WARNING` may be
deferred with a documented reason in the commit message.

**Financial logic commits** (Greeks, P&L, Decimal paths, BrokerClient boundaries):
a real `@code-reviewer` subagent run by a Claude session is mandatory — a persona
approximation is insufficient because it does not load `REVIEW.md` hygiene rules unless
explicitly provided. Emit `CODE REVIEW GATE — awaiting @code-reviewer via Claude` and wait.

## Step 5 — Close the phase (docs → tests → commit)

A phase is not complete until all three are done. Never move to the next phase mid-checklist.

**5a — Update docs** (targeted edits only, never a full-file overwrite):
- `CONTEXT.md` — "What Exists" module tree if new files added
- `DECISIONS.md` — any new architecture decisions
- `TODOS.md` — mark completed items, add session log entry
- `docs/plan/README.md` — status column for the story/epic just touched (root cause of an epic going stale is this file not being updated — see FR-7 row 15, `docs/plan/full-repo-review/findings/FR-7_synthesis.md`)
- The relevant `src/<module>/CLAUDE.md` if module invariants changed

**5b — Verify tests green:**
- Run `python -m pytest tests/unit/ --tb=no -q` — all must pass before committing.

**5c — Commit** (format in `.claude/skills/commit/SKILL.md`):
- Code changes: any commit touching `.py` files under `src/`, `scripts/`, or `tests/`. The `code-reviewer` gate applies against `git diff HEAD` — emit the await-signal and hand to Claude. Address any `CRITICAL` or `ERROR` findings before committing. `WARNING` may be deferred with a documented reason.
- Docs / config only: no `.py` files under `src/`, `scripts/`, or `tests/` in the diff — skip code-reviewer. Commit immediately after 5a.
- **Never bundle changes from separate phases into one commit.**

**⛔ The commit must be executed, not drafted.** A written-out commit message is not a commit. The phase is not closed until you have run:

```bash
git add <files>
git commit -m "<message>"
git log --oneline -1   # confirm SHA appears — this is the proof of completion
```

Providing the commit message to the user and stopping is a recurring failure mode. The commit is the last mandatory action of every phase. Do not hand off to the user to run it.

Typical phase boundaries (each gets its own commit):
- Model → Store → Tracker/orchestration → Formatting / pure helpers

**5d — Session efficiency close-out:** the `.claude/skills/session-close/SKILL.md` audit runs
at end of session. Under Claude this is a `fork` subagent; Antigravity cannot fork — run the
skill inline and report its compact block, or hand to Claude to run it. This step is never a
"legitimate skip" — a read-only/query-only session still closes with a trivial clean report,
per the skill's own Step 5 fallback. See `ANTIGRAVITY.md` §"Phase Completion Output" for the
structured block Antigravity emits so Claude can verify the phase without re-reading files.

---

## Council Decision Protocol

When a council response file (`docs/council/YYYY-MM-DD_<topic>.md`) is shared or referenced,
follow this parsing and action order — do not treat all three stages equally.

### Reading priority

| Stage | Section header | Role | What to do |
|-------|---------------|------|------------|
| 3 | `## Stage 3 — Chairman Synthesis` | **Authoritative recommendation** | Read this first and fully — this is what gets implemented |
| 2 | `## Aggregate Rankings (Stage 2 Peer Review)` | Peer credibility signal | Use to weight Stage 1 opinions when Stage 3 leaves a nuance unresolved |
| 1 | `## Stage 1 — Individual Responses` | Raw panel opinions | Background context only — do NOT implement from Stage 1 directly |

### Inside Stage 3 — what to extract

1. **Summary Table** (always present at end of Stage 3): canonical before/after for each decision. This is the implementation spec.
2. **Dissenting Notes** section: minority positions that were noted but overruled. Log these in `DECISIONS.md` under "Noted, deferred" — they are first candidates for post-validation testing.
3. **Implementation Sequencing** (if present): lists which docs to update and in what order. Follow it literally.
4. **Additional Rules Surfaced**: supplementary constraints that emerged during review. Treat these as mandatory additions to the relevant plan/strategy doc.

### Mandatory post-read actions

After reading a council file, always:

1. Update `DECISIONS.md` — add a row for each decision in the Summary Table with the council date and topic as the source.
2. Update the relevant plan or strategy doc (named in Implementation Sequencing) — edit it to reflect Stage 3 recommendations, not the original design.
3. Do **not** implement code until DECISIONS.md and the strategy doc reflect the council output. The council decision gates implementation.

### Aggregate Rankings — how to interpret

```
- model-A: avg rank 1.0 (4 votes)   ← panel judged this the strongest response
- model-B: avg rank 2.25 (4 votes)
- model-C: avg rank 2.75 (4 votes)
```

The chairman draws heavily on the top-ranked response. If Stage 3 feels thin on a topic,
the highest-ranked Stage 1 response is the right place to look for supporting detail.
Never use a lower-ranked response to contradict Stage 3.

---

## Rules for any review or handoff

(Promoted from the full-repo-review epic per its FR-1 finding that these generalize —
`docs/plan/full-repo-review/findings/FR-1_protocol-reviewer.md` Step 5.)

1. **Rate severity by mission impact, not by finding volume.** Severity is tied to actual
   business impact (does this expose capital, does this cost a real decision-quality point) —
   not to how many findings make a review look thorough.
2. **Verify your own citations before asserting them.** Before citing a file, line, or
   DECISIONS.md entry as "live" or "current," check it against the repo — do not trust a
   prior pass or your own memory of the codebase.
3. **Every review or handoff states at least one perspective it did not cover** — write
   "none identified" explicitly if genuinely nothing comes to mind; never omit the section.

---

## Quick reference

| What | Where |
|---|---|
| Start-of-task routing (feature / bug → load prompt) | manual — `TODOS.md` first-5 or `docs/bugs/` (the `/work` skill is Claude-only) |
| Graph project ID | `Users-abhadra-myWork-myCode-python-NiftyShield` |
| Project state | `CONTEXT.md` |
| Architecture decisions | `DECISIONS.md` |
| Instrument keys / AMFI codes / API quirks | `REFERENCES.md` |
| SQLite table registry (writer, cadence, purpose per table — check before any DB write) | `DB_REGISTRY.md` |
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
| Session close / protocol audit | `.claude/skills/session-close/SKILL.md` |
| Python review checklist | `REVIEW.md` |
| Logging standard (entrypoint rule, line shape, event naming) | `LOGGING.md` |
| Telegram value/table formatting standard (decimals, alignment, sign display) | `FORMATTING.md` |
| Bug registry (confirmed defects) | `docs/bugs/bugs.md` |
| Backtest → paper → live pipeline plan | `BACKTEST_PLAN.md` |
| Council trigger criteria + workflow | `docs/council/README.md` |
| Completed council decisions | `docs/council/YYYY-MM-DD_<topic>.md` |
| Antigravity operating protocol | `ANTIGRAVITY.md` |
| Claude–Antigravity workflow division | `docs/antigravity/ai_collaboration_plan.md` |
| Which surface + model to use, by job type | `docs/plan/full-repo-review/findings/FR-8_practitioner-devex.md` |

## AI Collaboration — Claude and Antigravity

This project uses two AI agents. **Claude** handles planning, graph queries, council
decisions, and the mandatory `@code-reviewer` gate. **Antigravity (you)** handles autonomous
multi-file implementation, TDD loops, and commit execution.

**What this means for Antigravity:**
- Claude may have authored the plan, the council decision, or a prior phase's code. Follow
  the story file and any council output verbatim — they gate implementation.
- Your file-editing tools differ from Claude's: `multi_replace_file_content` where Claude
  uses `Edit`, `write_to_file` for new files only. See `ANTIGRAVITY.md` §"File Editing Rules".
- The `@code-reviewer` gate is real and Claude-run. Emit the await-signal and wait — your own
  persona review is approximate and does not load `REVIEW.md` unless explicitly provided.
- Council decisions are always Claude's responsibility. You do not trigger the council.
- Job-type → surface/model routing: see `docs/plan/full-repo-review/findings/FR-8_practitioner-devex.md`.
- The full workflow division (who does what, in which phase) is in
  `docs/antigravity/ai_collaboration_plan.md`.

---

## Module CLAUDE.md files (read explicitly when working in that directory)

| Module | Context file |
|---|---|
| `src/portfolio/` | Leg/Trade distinction, Decimal invariant, `apply_trade_positions()`, strategy_name constraint |
| `src/mf/` | Transaction ledger model, AMFI source, Decimal TEXT invariant, MFHolding location |
| `src/client/` | BrokerClient protocol rule, 4 implementations, blocked methods, two-token constraint |
| `src/notifications/` | Non-fatal contract, `build_notifier()` → None, HTML parse_mode |
| `src/dhan/` | LTP via Upstox batch, two-phase fetch, classification config, double-count prevention |

Also present on disk (read when working there): `src/paper/CLAUDE.md`, `src/nuvama/CLAUDE.md`,
`src/gamma/CLAUDE.md`.

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
