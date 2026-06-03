Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/historical-data-abstraction/tasks.md` and find the first unchecked box —
the first `- [ ]` line. That is your **only task** for this session. Do not look at any
other unchecked item. One task. Complete it fully. Stop.

**Story spec:** Read `docs/plan/historical-data-abstraction/stories/<TASK_ID>.md` for the
full implementation spec, pre-baked graph context, test list, and commit message.

---

## Core Design Constraint

**Storage format is frozen. Only the fetch layer changes.**

Canonical storage:
- VIX: Parquet at `data/historical/ohlc/india_vix/`, daily closes, columns `date/open/high/low/close`
- OHLC candles: Parquet at `data/historical/ohlc/<instrument>/`, same schema
- Bhavcopy: Parquet at `data/offline/options_ohlcv/`, `BhavRecord` schema from `src/backtest/bhavcopy_ingest.py`

None of these schemas change. The `HistoricalCandleFetcher` protocol produces rows that
feed the existing Parquet writers unchanged.

**Cost discipline — mandatory for HD-0 (evaluation) and HD-1 (probe scripts):**
Every API call to a paid historical data source must be preceded by a dry-run check.
Probe scripts must accept `--dry-run` to print what would be fetched without calling the API.
Probe scripts must print estimated cost (calls × rate) before any paid fetch.
Never run paid probes against a full date range — probe with a 5-day window only.

---

## Pre-implementation gate

State in one sentence: which task (ID + description), which files change, which test file
covers it. No code before this is stated.

## Graph-before-Read rule

`git log --oneline -10 <file>` → `search_graph` → `trace_path` → `search_code` →
`bash sed -n 'N,Mp' <file>` → `Read` only if all above insufficient.

## Before writing any test helper

`get_code_snippet('<ModelClassName>')` — never write model constructors from memory.

## Implementation rules

`CLAUDE.md` + `REVIEW.md` apply. Every public function: one happy-path + one edge/error test.
No network calls in tests. Monetary/price fields always `Decimal`, stored as TEXT in SQLite.
Parquet price columns use `float64` (existing schema — do not change to Decimal in Parquet).

## Agent routing

Each story opens with `> Assigned to: Claude` or `> Assigned to: Antigravity`.

## Test gate — blocking

`python -m pytest tests/unit/ --tb=no -q` — all green before proceeding.

## Code-reviewer gate — blocking

`code-reviewer` agent against `git diff HEAD`. CRITICAL/ERROR must resolve before commit.

## Commit

Format from `.claude/skills/commit/SKILL.md`. Execute — do not draft.

```bash
git add <files>
git commit -m '<message>'
git log --oneline -1
```

## Verify and record

Tick `docs/plan/historical-data-abstraction/tasks.md`, append `| SHA: <sha>`.
Add one line to `TODOS.md` session log:
`| <YYYY-MM-DD> | historical-data-abstraction <task-id> — <one-line description> — <SHA> |`

**Stop.**
