# Signals LLM cost tracking — prompt

> Capture OpenRouter per-call token usage + credit cost on every signal provider response, persist it, show today's spend on the 09:30 morning Telegram message, and expose a date-range cost aggregate.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The `signals/` pipeline (shipped 2026-09-09, archived) fans out to GPT-4o / Grok / Gemini via OpenRouter every trading morning. Each provider does exactly one `POST /chat/completions` and throws the
response envelope away except for `choices[0].message.content` — so the `usage` block (token counts) and the credit cost of the call are never seen, never stored, and never reported. There is
currently no way to answer "what did the signal pipeline cost this month" without logging into the OpenRouter dashboard, and no per-day or per-provider breakdown at all.

OpenRouter exposes three cost surfaces: inline usage accounting (`"usage": {"include": true}` in the request body → the response envelope carries `usage.cost` in USD plus native token counts, one
round-trip, no lag), the `GET /generation?id=` lookup (a second HTTP call per provider, lagged, needs a retry), and key-lifetime totals (`/credits`, `/activity` — no per-run grain). Animesh chose
**inline usage accounting** for capture (2026-09-09 discussion): zero extra calls, exact cost, and the pipeline already parses the envelope. Aggregation is then a local SQLite `SUM` over a new set of
columns on `signal_responses`.

The morning message shows **today's three-call total only** — the cheap, always-available number. Month-to-date cumulative cost belongs in `signal_report.py` (16:35 cron), not here, and is out of
scope for this story.

## Scope guard

**In bounds:** `src/signals/models.py` (new `SignalUsage` model + optional field on `SignalResponse`), `src/signals/providers/{gpt4o,grok,gemini}.py` (add the payload flag, parse the `usage` block),
`src/signals/store.py` (three new columns on `signal_responses`, write + read-back, one new aggregate method), `scripts/morning_signal.py` (sum today's cost, one new Telegram line in all three message
variants), the matching `tests/unit/` files, and the docs in SCT-4.

**Out of bounds:** the `GET /generation` endpoint (rejected — extra call, lag); month-to-date / cumulative cost reporting (that is a `signal_report.py` change, separate story); the `mock` provider's
cost (it has no real cost — emits `None`); Gemini's Phase-2 non-OpenRouter Google-SDK branch (no OpenRouter cost object — emits `None`); any change to consensus / aggregation / outcome logic; any new
cron or schedule change. This story changes `src/` behaviour (new persisted columns, new message line) but adds no new entrypoint script.

## Session-start load hints

- **`schema.md` — read it before any `SignalStore` work (SCT-2).** Three columns added to `signal_responses`; it also states the `DB_REGISTRY.md` row edit.
- `DB_REGISTRY.md` — the `signal_responses` row is edited in SCT-2, not added.
- `FORMATTING.md` — SCT-3 formats a money value into a MarkdownV2 Telegram message; follow the per-parameter-type standard and the escaping-boundary contract. `_format_signal_notification` in
  `scripts/morning_signal.py` owns its own escaping (escapes per value, emits literal `*`) — the new line must match that, and the caller still sends the result without re-wrapping.
- `LOGGING.md` — only if SCT adds a `logger.*()` call (SCT-3 may log the daily total).
- `src/notifications/CLAUDE.md` §"Instrument Label Formatting" — not directly relevant (no instrument labels), skim only if unsure.
- Archived reference: `docs/archive/plan/signals/signals_schema.md`, `docs/archive/plan/signals/signals_stories.md` — the original pipeline spec.

## Task overview

- **SCT-1** — `SignalUsage` frozen model + optional `usage` field on `SignalResponse`; all three OpenRouter providers send `"usage": {"include": true}` and parse `envelope["usage"]` (tolerant of
  absent).
- **SCT-2** — `signal_responses` gains `prompt_tokens` / `completion_tokens` / `cost_usd`; `record_response` writes them, `_response_from_row` rebuilds; new `SignalStore.get_signal_cost()`
  SQL-aggregate.
- **SCT-3** — `morning_signal.py` sums today's per-provider `cost_usd`, renders one escaped `💵 LLM cost` line in all three message variants.
- **SCT-4** — docs: `DB_REGISTRY.md`, `CONTEXT.md` signals bullet, `DECISIONS.md` (inline-usage-over-generation-endpoint decision).

## Definition of done

Every provider response persisted after this story carries token counts and USD cost (or an explicit `NULL` for the mock / Google-SDK paths). The 09:30 Telegram message shows the day's total LLM spend
across all three variants (consensus, no-consensus, pipeline-failure). `SignalStore.get_signal_cost(from_date, to_date)` returns a compact `{"total_usd", "call_count", "by_provider"}` dict via a
single SQL aggregate. `DB_REGISTRY.md`, `CONTEXT.md`, and `DECISIONS.md` reflect the change. `pytest tests/unit/` green.

## Perspectives not covered

- **Cost/accuracy reconciliation** — OpenRouter's `usage.cost` is what OpenRouter billed, which can differ slightly from the upstream provider's own metering and from post-hoc dashboard figures
  (rounding, credit discounts, BYOK). This story trusts `usage.cost` verbatim; nobody has checked it against a month of dashboard invoices.
- **Backfill** — responses already stored before SCT-2 lands keep `NULL` cost columns forever; `get_signal_cost` silently under-counts any window that includes pre-migration days. No backfill is
  attempted (the envelopes were not retained). SCT-4 docs should note the first date from which cost data is trustworthy.
