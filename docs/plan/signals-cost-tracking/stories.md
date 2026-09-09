# Signals LLM cost tracking — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update `docs/plan/README.md`, add one line to `TODOS.md`.

DDL: use the exact schema in `schema.md`. Do not inline `CREATE TABLE` / `ALTER TABLE` below.

---

## SCT-1 — usage model + provider capture

**Files to change / create:**
- `src/signals/models.py` — new `SignalUsage(BaseModel, frozen=True)`; new optional field `usage: SignalUsage | None = None` on `SignalResponse`.
- `src/signals/providers/gpt4o.py` — add `"usage": {"include": True}` to `payload`; parse `envelope.get("usage")` in `_parse_response`, pass the built `SignalUsage | None` into the
  `SignalResponse(...)` call.
- `src/signals/providers/grok.py` — same two edits (`payload`, `_parse_response`). Only the OpenRouter path; the xAI-direct branch (`use_openrouter=False`) already sets `payload["search"]` — leave
  `usage` off it (no usage-cost contract on xAI direct → `None`).
- `src/signals/providers/gemini.py` — same two edits, but only inside `_call_openrouter` / `_build_signal`. The `_call_google_sdk` path returns a bare `str` and must yield `usage=None` — thread an
  optional `usage` arg through `_build_signal` defaulting to `None`.
- `src/signals/providers/mock.py` — no payload; `MockSignalProvider` emits `SignalResponse(..., usage=None)`. Add nothing if the default already covers it — confirm by reading the file.
- `tests/unit/signals/test_providers_gpt4o.py`, `test_providers_grok.py`, `test_providers_gemini.py` (match the actual filenames in the tree) — new cases below.

**Before any code (graph queries — do not write model constructors from memory):**
- `get_code_snippet("SignalResponse")` — current field list, confirm `frozen=True`, confirm no existing `usage` field.
- `get_code_snippet("MockSignalProvider")` — how it builds its `SignalResponse` today.
- `search_code("_build_signal")` — every call site in `gemini.py` (both the OpenRouter and the SDK path go through it).
- `search_code("\"usage\"")` in `tests/unit/signals/` — check whether any provider test fixture envelope already includes a `usage` key.

**What to implement:**

1. `SignalUsage` — three fields: `prompt_tokens: int`, `completion_tokens: int`, `cost_usd: Decimal`. `frozen=True`. Google-style docstring naming OpenRouter `usage.prompt_tokens` /
   `usage.completion_tokens` / `usage.cost` as the sources. No `total_tokens` field — it is `prompt + completion` and storing it invites drift.
2. Add `usage: SignalUsage | None = None` to `SignalResponse` (last field, after `raw_response`, keeps the positional constructor calls in the providers working — but prefer switching those calls to
   keyword for `usage` regardless).
3. A module-level helper in each provider (or one shared in `src/signals/providers/__init__.py` if the reviewer prefers DRY — your call, note it in the commit): `_usage_from_envelope(envelope: dict)
   -> SignalUsage | None`. Returns `None` when `envelope.get("usage")` is falsy or missing `cost`. Parses `cost` via `Decimal(str(raw["cost"]))`; `int(raw["prompt_tokens"])` /
   `int(raw["completion_tokens"])` with `.get(..., 0)` fallback. Swallows `KeyError` / `TypeError` / `InvalidOperation` → `None` (a malformed usage block must never fail the signal — the parsed
   direction is what matters).
4. Wire the helper result into every `SignalResponse(...)` construction in the OpenRouter code paths.

**Tests (`tests/unit/...`, no network, no real DB):**
- `test_get_signal_parses_usage` — provider given a stubbed envelope with `usage: {"prompt_tokens": 1200, "completion_tokens": 40, "cost": 0.0031}`; assert `response.usage.cost_usd ==
  Decimal("0.0031")` and token ints.
- `test_get_signal_usage_absent_is_none` — same stubbed call, envelope has no `usage` key; assert `response.usage is None` and no exception.
- `test_get_signal_usage_malformed_is_none` — `usage: {"cost": "not-a-number"}`; assert `response.usage is None`, signal still parsed.
- Gemini only: `test_google_sdk_path_usage_none` — the non-OpenRouter branch yields `usage is None`.
- Mock: `test_mock_provider_usage_none`.

**Commit:** `feat(signals): capture OpenRouter token usage and cost per call`

---

## SCT-2 — persist + aggregate

**Files to change / create:**
- `src/signals/store.py` — `_SCHEMA` `CREATE TABLE signal_responses` gains the three columns (per `schema.md`); `init_db()` gains three idempotent `ALTER TABLE` guards mirroring the existing
  `daily_signals.entry_premium` one; `record_response` INSERT gains the three columns + params; `_response_from_row` rebuilds a `SignalUsage` (or `None`); new method `get_signal_cost`.
- `tests/unit/signals/test_store.py` (match actual filename) — new cases below.

**Before any code:**
- `get_code_snippet("SignalStore.init_db")` — the exact `try/except sqlite3.OperationalError` "duplicate column name" idiom to copy.
- `get_code_snippet("SignalStore.record_response")` — current column list + param tuple.
- `get_code_snippet("SignalStore._response_from_row")` — current row→model mapping; where to add the `usage=` kwarg.
- `get_code_snippet("get_cumulative_realized_pnl")` — the reference SQL-layer-aggregation pattern named in `CLAUDE.md` Rule 1 (compact dict return, `SUM` at the source).
- `get_code_snippet("SignalUsage")` — field names/types from SCT-1.

**What to implement:**

1. `_SCHEMA`: add `prompt_tokens INTEGER`, `completion_tokens INTEGER`, `cost_usd TEXT` to the `signal_responses` `CREATE TABLE IF NOT EXISTS` (nullable, no default).
2. `init_db()`: after the `executescript`, three more `try: conn.execute("ALTER TABLE signal_responses ADD COLUMN ...") except sqlite3.OperationalError` guards, each re-raising unless `"duplicate
   column name" in str(exc).lower()`. Consider a small local loop over the three `ADD COLUMN` statements to avoid three near-identical blocks.
3. `record_response`: extend the INSERT column list and the value tuple. When `response.usage is None`, bind `None, None, None`; else `response.usage.prompt_tokens, response.usage.completion_tokens,
   str(response.usage.cost_usd)`.
4. `_response_from_row`: build `usage = None if row["cost_usd"] is None else SignalUsage(prompt_tokens=row["prompt_tokens"], completion_tokens=row["completion_tokens"],
   cost_usd=Decimal(row["cost_usd"]))`; pass `usage=usage` to the `SignalResponse(...)`. Guard on `"cost_usd" in row.keys()` is unnecessary — `init_db` always runs first — but a `try/except
   (IndexError, KeyError)` is acceptable defensive coding if a reviewer asks.
5. `get_signal_cost(self, from_date: date | None = None, to_date: date | None = None) -> dict[str, object]`:
   - One SQL statement: `SELECT provider, COUNT(*) AS n, COALESCE(SUM(CAST(cost_usd AS REAL)), 0) AS c FROM signal_responses WHERE cost_usd IS NOT NULL [AND trade_date >= ?] [AND trade_date <= ?]
     GROUP BY provider`.
   - Build the return in Python: `by_provider = {row["provider"]: Decimal(str(row["c"])).quantize(Decimal("0.0001")) for row in rows}`; `total_usd = sum(by_provider.values(), Decimal("0"))`;
     `call_count = sum(row["n"] for row in rows)`.
   - Return `{"total_usd": total_usd, "call_count": call_count, "by_provider": by_provider}`.
   - `CAST(cost_usd AS REAL)` for the `SUM` is a deliberate, documented precision compromise — costs are ~1e-3 USD, four-dp output, float error is ~1e-15; the per-row values stay exact `TEXT`. Note
     this in the docstring.

**Tests (`tests/unit/...`, no network — use a `tmp_path` SQLite file, that is the house pattern for `SignalStore` tests, not a real DB):**
- `test_record_response_persists_usage` — record a response with `usage`, read it back via `get_responses`, assert `cost_usd` / tokens survive round-trip as `Decimal` / `int`.
- `test_record_response_null_usage` — record with `usage=None`, read back, assert `response.usage is None`.
- `test_get_signal_cost_aggregates` — three responses across two dates/providers, assert `total_usd`, `call_count`, and `by_provider` keys.
- `test_get_signal_cost_date_filter` — bound `from_date` past one row, assert it drops out of both total and count.
- `test_get_signal_cost_empty` — no rows, assert `{"total_usd": Decimal("0"), "call_count": 0, "by_provider": {}}`.
- `test_init_db_idempotent_with_cost_columns` — call `init_db()` twice, no error.

**Commit:** `feat(signals): persist per-call LLM cost and add cost aggregate`

---

## SCT-3 — morning Telegram line

**Files to change / create:**
- `scripts/morning_signal.py` — after the `store.record_response` loop, sum `r.usage.cost_usd` over `valid` where `r.usage is not None`; pass `(day_cost, n_priced)` into `_format_signal_notification`;
  render one line in each of the three return branches; optionally one `logger.info("morning_signal.llm_cost", ...)` line.
- `tests/unit/scripts/test_morning_signal.py` (match actual filename / add if the format tests live elsewhere — check `tests/unit/signals/`) — new cases below.

**Before any code:**
- `get_code_snippet("_format_signal_notification")` — its current signature, the three return branches, how it escapes (`_E = escape_markdown`, per-value, literal `*` for bold).
- `search_code("_format_signal_notification")` — the single call site in `run()`.
- `get_code_snippet("format_money")` — signature + output shape (`src/notifications/formatting.py`); decide whether it fits a sub-cent USD value or whether a local `_format_usd` helper (4dp, `$`
  prefix) is needed. It is an INR-oriented helper — a local helper is likely correct; confirm by reading it.
- Read `FORMATTING.md` — money-value rule + the escaping-boundary contract (this formatter is inside the boundary — it escapes, the caller does not).

**What to implement:**

1. In `run()`, after the response loop: `day_cost = sum((r.usage.cost_usd for r in valid if r.usage is not None), Decimal("0"))`; `n_priced = sum(1 for r in valid if r.usage is not None)`.
2. `_format_signal_notification(signal, n_providers, day_cost, n_priced)` — extend the signature. Default `day_cost=Decimal("0")`, `n_priced=0` is acceptable to keep existing tests compiling, but
   update the call site.
3. Cost line, built once near the top: `cost_line = _E(f"💵 LLM cost: {_format_usd(day_cost)} ({n_priced} call{'s' if n_priced != 1 else ''})")` where `_format_usd` renders e.g. `$0.0042` (quantize to
   `Decimal("0.0001")`, `f"${v:.4f}"`).
4. Append `cost_line` to all three variants:
   - **consensus block** — as a new trailing line after the Model Votes section.
   - **no-consensus block** — after the votes list.
   - **pipeline-failure block** — after "Check logs before the next run" (here `n_priced` is 0 → `$0.0000 (0 calls)`; that is fine, it confirms nothing was billed).
5. Keep the "caller sends WITHOUT re-wrapping in `escape_markdown`" contract — `cost_line` is already escaped.

**Tests (`tests/unit/...`, no network):**
- `test_notification_consensus_shows_cost` — directional signal, two priced responses; assert `💵 LLM cost: $` and `(2 calls)` in the output.
- `test_notification_no_consensus_shows_cost` — split vote; assert the line present.
- `test_notification_pipeline_failure_shows_zero_cost` — no responses; assert `$0.0000 (0 calls)`.
- `test_notification_cost_line_escaped` — a cost that stringifies with a `.` (always) — assert the `.` is backslash-escaped per MarkdownV2 (`\.`), proving it went through `_E`.
- `test_notification_singular_call` — `n_priced == 1` → `(1 call)` not `(1 calls)`.

**Commit:** `feat(signals): show daily LLM spend on morning signal message`

---

## SCT-4 — docs

**Files to change (targeted `Edit` only, never `Write`):**
- `DB_REGISTRY.md` — edit the existing `signal_responses` row per `schema.md` §"DB_REGISTRY.md row to edit"; add the lettered note with the closing SHA of SCT-2 and the trustworthy-from date.
- `CONTEXT.md` — the `src/signals/` bullet: add a clause that provider responses now record OpenRouter token usage + USD cost, aggregated by `SignalStore.get_signal_cost()` and surfaced on the 09:30
  message.
- `DECISIONS.md` — one entry under the signals / reporting section: chose OpenRouter **inline usage accounting** (`"usage": {"include": true}`) over the `GET /generation?id=` lookup (extra HTTP call
  per provider, response lag) and over `/credits` + `/activity` (no per-run grain). Dated 2026-09-09, requested by Animesh.
- This story's `prompt.md` §"Perspectives not covered" already records the backfill gap — the "cost trustworthy from <date>" note goes in the `DB_REGISTRY.md` lettered note (above) and one line in
  `CONTEXT.md`.

**Before any code:** none — docs only. Confirm the SCT-2 SHA is in `git log --oneline -5` before writing the note.

**Tests:** none — docs-only diff, no `.py` under `src/` / `scripts/` / `tests/`, so `code-reviewer` is skipped and this commits straight after the edits.

**Commit:** `docs(signals): record LLM cost tracking columns and decision`
