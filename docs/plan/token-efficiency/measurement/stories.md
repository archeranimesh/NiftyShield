# Token Efficiency — Measurement — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, update the epic `README.md`
> Stories status column, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## MEAS-1 — `token_audit.py`: attribute a session's tokens by bucket

**Files to change / create:**
- `scripts/dev/token_audit.py` — new entrypoint script
- `tests/unit/scripts/dev/test_token_audit.py` — new
- `tests/fixtures/transcripts/` — a small hand-built fixture transcript JSONL (2–3 turns,
  one subagent spawn, a couple of tool calls) — enough to exercise every bucket

**Before any code:**
- Open a real transcript first. Claude Code writes session JSONL under the project state
  dir; the harness names the path in the scratchpad/system context, and each `Agent` spawn's
  result line prints an `output_file` path for that subagent's transcript. Confirm the record
  shapes (message roles, `usage` blocks, tool-use / tool-result pairing, the
  task-notification records that carry `subagent_tokens`) by reading ~50 lines of one before
  writing the parser — do not write the schema from memory.
- `search_code("setup_logging")` — reuse the canonical logging entrypoint per `LOGGING.md`.

**What to implement:**

1. `resolve_transcript(arg: str) -> Path` — accept an explicit path or a session id and
   locate the JSONL. Raise a clear error if neither resolves.
2. `parse_records(path: Path) -> list[Record]` — one lightweight frozen dataclass per
   JSONL line that carries tokens or spawns work: role, tool name (if a tool result), token
   count (from the record's own `usage` / cache fields where present, else an estimate via a
   tokenizer-free heuristic — document which), and a `kind` tag.
3. `attribute(records) -> dict[str, int]` — fold records into buckets:
   - `system_prompt` — the fixed harness preamble + tool schemas
   - `project_docs` — `CLAUDE.md` + `AGENTS.md` + `MEMORY.md` + auto-injected module
     `CLAUDE.md` blocks (match on the known headers / file markers)
   - `tool_results:<tool>` — grouped per tool name (`Read`, `Bash`, `Grep`,
     `mcp__codebase-memory-mcp__*`, …)
   - `subagent_reports` — the final report payloads returned into the main thread
   - `subagent_internal` — summed `subagent_tokens` from task-completion records (these do
     not sit in main context but are real account cost — label them as such)
   - `assistant_text` — the model's own output
4. `render_table(buckets) -> str` — the compact table format from the 2026-09-01 audit:
   bucket, tokens, short note. Sorted by tokens descending.
5. `--json` — emit the same data as a JSON object for scripting / diffing two sessions.
6. `main()` — `argparse`, `setup_logging(...)`, `_SCRIPT_NAME = "scripts.dev.token_audit"`,
   `logger = structlog.get_logger(_SCRIPT_NAME)`.

**Tests (`tests/unit/scripts/dev/`, no network, fixture transcript only):**
- `test_attribute_sums_to_total` — every record lands in exactly one bucket; bucket sum
  equals the record-token sum
- `test_subagent_internal_counted_separately` — a task-completion record's `subagent_tokens`
  goes to `subagent_internal`, not `tool_results`
- `test_resolve_transcript_bad_arg_raises` — a path that is neither a file nor a resolvable
  session id raises `ValueError` / `FileNotFoundError` with a message naming the arg
- `test_render_table_orders_by_tokens_desc` — largest bucket first
- `test_json_mode_round_trips` — `--json` output parses and carries the same totals as the
  table

**Commit:** `feat(scripts): add token_audit.py session cost attribution tool`

---

## MEAS-2 — run the tool, write the baseline

**Files to change / create:**
- `docs/plan/token-efficiency/README.md` — add a `## Baseline` section (before
  `## Cross-cutting constraints` or after `## Why this epic exists`, wherever it reads best)

**Before any code:** none — this is a measure-and-write task.

**What to implement:**

1. Pick 4–5 recent real session transcripts spanning a range: a code task, a docs task, a
   query-only session, and at least one that spawned several subagents.
2. Run `token_audit.py` on each. Record per-bucket numbers.
3. Write the `## Baseline` section: a table of the per-bucket medians (or a small
   per-session table if the spread is large), then 2–3 sentences naming the biggest
   avoidable items — the ones `fixed-overhead/` and `suggestions-sweep/` will attack. Quote
   the ROLL-7 session's ~740K / ~285K-fork figure as the worked example that started the
   epic.
4. State the measurement method in one line (which sessions, tool version / commit) so the
   baseline is reproducible.

**Tests:** none (docs-only change; `check_md_line_length` + `check_story_structure` run at
commit).

**Commit:** `docs(plan): record token-efficiency baseline from token_audit.py`
