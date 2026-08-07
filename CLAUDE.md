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
- Writing to `portfolio.sqlite`, adding a new table, or unsure which table already holds data you're looking for → also read `DB_REGISTRY.md` **first** (before assuming a table is empty/missing — see its 2026-08-07 note on `paper_nav_snapshots` vs. `paper_leg_snapshots`)
- Starting a new feature → also read `TODOS.md` + `PLANNER.md`
- Phase 0 backtest / paper trading / strategy / `src/paper/` / `src/risk/` work → also read `BACKTEST_PLAN.md` (Phase 0 only — ~300 lines)
- Phase 1+ work (only after Phase 0.8 gate passes) → also read `BACKTEST_PLAN_PHASE1.md`
- Implementing a metric / ratio / ML technique → also read `LITERATURE.md` entry for the cited LIT code
- Working a specific story → load ONLY that story file + `CONTEXT.md` + module `CLAUDE.md`
- Working inside `src/<module>/` → that module's `CLAUDE.md` loads automatically
- Reviewing or building on Antigravity's work → also read `ANTIGRAVITY.md`
- Authoring or reviewing any task/story/spec mentioning expiry, DTE, or calendar logic → also read `REFERENCES.md` (expiry day changed Thursday→Tuesday, April 2026)
- Adding a new entrypoint script, adding/editing any `logger.*()` call, or touching `src/utils/logging.py` → also read `LOGGING.md` (project root) — canonical logging standard; see `BUG-010` in `docs/bugs/bugs.md` for why it exists

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

**If no:** proceed directly to Step 3.

This checkpoint exists only in the planning phase. Never invoke the council mid-implementation.

## Step 3 — State plan, wait for go-ahead

> Plan: [one sentence] → touches [file1, file2] → tests in [test file] → commit. Proceed?

If plan touches more than 2 files, wait for explicit go-ahead.

The Step 3b implementation-routing fork (Claude vs. Antigravity) applies regardless of file
count — it is independent of the go-ahead gate above. A ≤2-file task still needs a routing
decision; it just skips the go-ahead wait.

## Step 3b — Implementation routing (mandatory after go-ahead)

Once go-ahead is received, decide who implements **before writing any code**.
This is a fork — the two paths do not overlap.

**Claude implements:**
→ Proceed to Step 4. AutoTrigger agents (test-runner, code-reviewer) fire during and after
  implementation. Claude commits via the commit skill.

**Antigravity implements:**
→ Invoke the `handoff-antigravity` skill now. Produce the structured handoff prompt and stop.
  Do not write any code. Antigravity picks up from the handoff, runs its own protocol
  (TDD loop, persona review, commit), and returns a Phase Completion Output block.
  Claude verifies: SHA matches `git log --oneline -1`, test count meets DoD. If both check
  out, the phase is closed. If not, Claude opens a fix session with the failure details.

**When to choose Antigravity:**
- Task spans 3+ files with clear, non-ambiguous spec
- TDD loop needed (write tests first, iterate until green)
- Phase is from BACKTEST_PLAN.md with a fully documented DoD
- Implementation is mechanical — no real-time design decisions expected

**When Claude implements:**
- Single file or 2-file task where inline judgment calls are likely
- Exploratory work where the spec may change as code is written
- Any task requiring graph queries mid-implementation to resolve ambiguity

## Step 4 — Tests are mandatory

Every public function needs: one happy-path test + one error/edge-case test. No network in tests.

**⛔ Before writing any test helper that constructs a domain model (Pydantic / dataclass):**

Never write a `_make_*` / `build_*` / fixture helper from memory. Domain models evolve — required fields are added, enums are renamed, validators change. Writing from memory produces helpers that fail at collection time, wasting two round-trips to diagnose errors you introduced yourself.

Mandatory pre-step — run these before opening the test file:

```
get_code_snippet("<ModelClassName>")   # exact field list, required vs optional, types
search_graph("<EnumName>")             # every enum used in the helper — get all members
```

Concrete failures this prevents (from 2026-04-25 session):
- `Direction.SHORT` → does not exist; members are `BUY` / `SELL`
- `entry_date` → required field on `Leg`; omitting it raises `ValidationError` at collection

One graph call before the first line of test code eliminates both. Do not skip it.

## Agent AutoTrigger Rules

Spawning the correct sub-agent is not optional for the conditions below.
Inline review is not a substitute — each agent runs in an isolated context with the right model.

| Agent | Trigger condition | Blocking? |
|---|---|---|
| `test-runner` (Haiku) | After any code file is edited, before code-reviewer | **Yes** — must pass before proceeding |
| `code-reviewer` (Opus) | Before every commit touching code | **Yes** — CRITICAL/ERROR findings must resolve |
| `greeks-analyst` (Sonnet) | Any change to `src/paper/`, option chain parsing, or delta/gamma fields | **Yes** |
| `roll-validator` (Opus) | Any change to roll logic or `scripts/roll_leg.py` invocation | **Yes** |
| `options-strategist` (Opus) | Council checkpoint (Step 2b) when no real council is warranted | Advisory |

**"Blocking"** means the next protocol step does not proceed until the agent returns clean.
For `code-reviewer`: any `CRITICAL` or `ERROR` finding must be resolved; `WARNING` may be
deferred with a documented reason in the commit message.

On surfaces that structurally cannot spawn `.claude/agents/*` (Antigravity, some subagent
contexts): emit the await-signal per `ANTIGRAVITY.md` and hand control to a human reviewer.
That handoff satisfies the gate — it is human-completed, not skipped. The gate is violated
only if the commit proceeds with neither a real agent run nor a human review having occurred.

**Financial logic commits** (Greeks, P&L, Decimal paths, BrokerClient boundaries):
real `@code-reviewer` subagent is mandatory — Antigravity's persona approximation is
insufficient because it does not load `REVIEW.md` hygiene rules unless explicitly provided.



## Step 5 — Close the phase (docs → tests → commit)

A phase is not complete until all three are done. Never move to the next phase mid-checklist.

**5a — Update docs** (targeted `Edit` calls only, never `Write`):
- `CONTEXT.md` — "What Exists" module tree if new files added
- `DECISIONS.md` — any new architecture decisions
- `TODOS.md` — mark completed items, add session log entry
- `docs/plan/README.md` — status column for the story/epic just touched (root cause of the epic going stale is this file not being in this list — see FR-7 row 15, `docs/plan/full-repo-review/findings/FR-7_synthesis.md`)
- The relevant `src/<module>/CLAUDE.md` if module invariants changed

**5b — Verify tests green:**
- Run `python -m pytest tests/unit/ --tb=no -q` — all must pass before committing.

**5c — Commit** (format in `.claude/skills/commit/SKILL.md`):
- Code changes: any commit touching `.py` files under `src/`, `scripts/`, or `tests/` (ANTIGRAVITY.md's precise scope for "code"). Run the `code-reviewer` agent against `git diff HEAD`. Address any `CRITICAL` or `ERROR` findings before committing. `WARNING` may be deferred with a documented reason.
- Docs / config only: no `.py` files under `src/`, `scripts/`, or `tests/` in the diff — skip code-reviewer. Commit immediately after 5a.
- **Never bundle changes from separate phases into one commit.**

**⛔ The commit must be executed, not drafted.** A written-out commit message is not a commit. The phase is not closed until you have run:

```bash
git add <files>
git commit -m "<message>"
git log --oneline -1   # confirm SHA appears — this is the proof of completion
```

Providing the commit message to the user and stopping is a recurring failure mode (2026-04-24, 2026-04-25). The commit is the last mandatory action of every phase. Do not hand off to the user to run it.

Typical phase boundaries (each gets its own commit):
- Model → Store → Tracker/orchestration → Formatting / pure helpers

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

## Quick reference

| What | Where |
|---|---|
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
| Bug registry (confirmed defects) | `docs/bugs/bugs.md` |
| Backtest → paper → live pipeline plan | `BACKTEST_PLAN.md` |
| Council trigger criteria + workflow | `docs/council/README.md` |
| Completed council decisions | `docs/council/YYYY-MM-DD_<topic>.md` |
| Antigravity operating protocol | `ANTIGRAVITY.md` |
| Claude–Antigravity workflow division | `docs/antigravity/ai_collaboration_plan.md` |
| Which surface (Claude Code / Cowork / Antigravity) + model to use, by job type | `docs/plan/full-repo-review/findings/FR-8_practitioner-devex.md` |

## AI Collaboration — Antigravity and human review

This project uses two AI agents. Claude (you) handles planning, graph queries, council decisions, and the mandatory `@code-reviewer` gate. Antigravity handles autonomous multi-file implementation, TDD loops, and commit execution.

**What this means for Claude:**
- Antigravity may have authored uncommitted or recently committed code. When reviewing it, run the real `@code-reviewer` agent against `git diff HEAD` — Antigravity's own review is persona-based and approximate.
- Antigravity follows `ANTIGRAVITY.md` (project root). Its file-editing tools differ from Claude's: it uses `multi_replace_file_content` where Claude uses `Edit`, and `write_to_file` only for new files.
- The workflow division (who does what, in which phase) is in `docs/antigravity/ai_collaboration_plan.md`.
- Council decisions are always Claude's responsibility. Antigravity does not trigger the council.
- Job-type → surface/model routing (BACKTEST_PLAN phase, council-gated decision, mechanical logging fix, golden-test authoring, cron debugging, full-repo review): see `docs/plan/full-repo-review/findings/FR-8_practitioner-devex.md`.

**Rules for any review — Claude reviewing Antigravity's work, `code-reviewer` runs, or human handoffs** (promoted from the full-repo-review epic's prompt, per that epic's FR-1 finding that these three generalize beyond the epic itself — see `docs/plan/full-repo-review/findings/FR-1_protocol-reviewer.md` Step 5):
1. **Rate severity by mission impact, not by finding volume.** Severity is tied to actual business impact (does this expose capital, does this cost a real decision-quality point) — not to how many findings make a review look thorough. A padded list of INFO-level nitpicks is as useless as a review that rubber-stamps everything.
2. **Verify your own citations before asserting them.** Before citing a file, line, or DECISIONS.md entry as "live" or "current," check it against the repo — do not trust a prior pass or your own memory of the codebase.
3. **Every review or handoff states at least one perspective it did not cover** — write "none identified" explicitly if genuinely nothing comes to mind; never omit the section.

---

## Module CLAUDE.md files (auto-loaded when working in that directory)

| Module | Context file |
|---|---|
| `src/portfolio/` | Leg/Trade distinction, Decimal invariant, `apply_trade_positions()`, strategy_name constraint |
| `src/mf/` | Transaction ledger model, AMFI source, Decimal TEXT invariant, MFHolding location |
| `src/client/` | BrokerClient protocol rule, 4 implementations, blocked methods, two-token constraint |
| `src/notifications/` | Non-fatal contract, `build_notifier()` → None, HTML parse_mode |
| `src/dhan/` | LTP via Upstox batch, two-phase fetch, classification config, double-count prevention |