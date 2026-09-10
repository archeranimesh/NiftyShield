# Signals LLM cost tracking — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: none — story complete, archived.**

- [x] **SCT-1** — `SignalUsage` model + `usage` field on `SignalResponse`; providers send `usage.include`, parse it tolerantly | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA:
  a519714
- [x] **SCT-2** — `signal_responses` + 3 cost columns (idempotent ALTER); write + read-back; new `get_signal_cost()` aggregate | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA:
  c7efe54
- [x] **SCT-3** — `morning_signal.py` sums today's `cost_usd`, adds an escaped `💵 LLM cost` line to all 3 message variants | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA:
  1078397
- [x] **SCT-4** — docs: `DB_REGISTRY.md` row edit, `CONTEXT.md` signals bullet, `DECISIONS.md` inline-usage decision, trustworthy-from date note | Owner: Claude | Model: n/a | Review: none | SHA: b70f8fa

## Story done when

- **SCT-1** — every OpenRouter provider response carries a populated `SignalUsage` (tokens + `cost_usd` as `Decimal`); mock and Google-SDK paths carry `usage=None`; parsing a `usage`-less or
  malformed-`usage` envelope does not raise.
- **SCT-2** — `signal_responses` has the three columns, `record_response` persists them (`NULL` when `usage is None`), round-trip through `_response_from_row` preserves them, and
  `get_signal_cost(from_date, to_date)` returns `{"total_usd": Decimal, "call_count": int, "by_provider": dict}` from one SQL statement.
- **SCT-3** — all three `_format_signal_notification` variants (consensus / no-consensus / pipeline-failure) render a `💵 LLM cost: $X.XXXX (N calls)` line, correctly MarkdownV2-escaped, summed only
  over responses with a non-`None` cost.
- **SCT-4** — `DB_REGISTRY.md` `signal_responses` row reflects the new columns; `CONTEXT.md` signals bullet notes cost capture; `DECISIONS.md` records choosing inline `usage.include` over the
  `/generation` endpoint; the "cost trustworthy from <date>" note is written.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in `docs/plan/README.md` and add one line to `TODOS.md` Session Log. When the whole story is done,
follow `docs/plan/README.md` §Conventions *Completion → archive* — do not leave a done story half-archived.
