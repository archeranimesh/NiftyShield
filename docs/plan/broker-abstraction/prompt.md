Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/broker-abstraction/tasks.md` and find the first unchecked box — the first `- [ ]`
line. That is your **only task** for this session. Do not look at any other unchecked item.
Do not attempt to batch or combine tasks. One task. Complete it fully. Move on to nothing else.

**Story spec:** Read `docs/plan/broker-abstraction/stories/<TASK_ID>.md` for the full
implementation spec, pre-baked graph context, test list, and commit message. Follow it exactly.

The pre-baked context block at the bottom of each story file contains pre-run graph query
results — **skip all "Before any code" graph calls listed in the story and use those results
directly** to save tokens.

---

## Core Design Constraint

**Storage format is frozen. Only the fetch + parse layer changes.**

The canonical domain models (`OptionChain`, `OptionChainStrike`, `OptionLeg` in
`src/models/options.py`) are the single representation used by all downstream consumers:
Parquet writers, DB stores, paper trading, backtests. No broker-specific field names ever
appear past the parser boundary.

Each broker integration must:
1. Implement `BrokerClient` protocol (`src/client/protocol.py`) for order/account operations.
2. Implement `MarketDataParser` protocol (`src/client/parsers/protocol.py`) for option chain
   parsing — `parse_option_chain(raw: dict) -> OptionChain`.
3. Provide an `InstrumentKeyAdapter` (`src/client/adapters/<broker>.py`) that maps between
   the canonical `instrument_key` format (Upstox-style `NSE_FO|<token>`) and the
   broker-native symbol format, **without touching stored keys**.

The Parquet schema, SQLite schema, and all model field names are frozen.

---

## Pre-implementation gate

State in one sentence: which task you are implementing (ID + one-line description), which
files will change, and which test file covers it. Do not write any code until this plan is
stated.

## Graph-before-Read rule

Never call `Read` on `src/` or `scripts/` without first trying the graph. Order:
`git log --oneline -10 <file>` → `search_graph` / `get_code_snippet` → `trace_path` →
`search_code` → `bash sed -n 'N,Mp' <file>` → `Read` only if all above are insufficient.

## Before writing any test helper

Run `get_code_snippet('<ModelClassName>')` to get the exact current field list.
Never write model constructors from memory.

## Implementation rules

Follow all rules in `CLAUDE.md` and `REVIEW.md`. Every public function needs one happy-path
test and one edge/error test. No network calls in tests. Monetary fields always `Decimal`,
stored as TEXT in SQLite — never float.

## Agent routing (mandatory check)

Each story file opens with `> Assigned to: Claude` or `> Assigned to: Antigravity`.
- Claude assigned → Antigravity story → invoke `handoff-antigravity` skill and stop.
- Antigravity assigned → Claude story → stop and notify the user.
- Assignment matches → proceed.

## Test gate — blocking

After implementation, before touching anything else:
`python -m pytest tests/unit/ --tb=no -q`
All tests must be green. Fix failures before proceeding.

## Code-reviewer gate — blocking

Run the `code-reviewer` agent against `git diff HEAD`. Address any `CRITICAL` or `ERROR`
findings before committing. `WARNING` may be deferred with a documented reason.

## Commit

Use the format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it.

```bash
git add <files>
git commit -m '<message>'
git log --oneline -1
```

## Verify and record

Copy the SHA from `git log --oneline -1`. Open `docs/plan/broker-abstraction/tasks.md`,
change `- [ ]` to `- [x]` on the completed line, and append `| SHA: <sha>`. Then add one
line to `TODOS.md` under the session log:
`| <YYYY-MM-DD> | broker-abstraction <task-id> — <one-line description> — <SHA> |`

**Stop.** Do not proceed to the next unchecked item.
