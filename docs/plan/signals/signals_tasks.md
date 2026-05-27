# Signals — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/signals/signals_stories.md`.

---

- [ ] **S1.1** — `src/signals/models.py`: Direction, TradeAction, MarketSnapshot, SignalResponse, DailySignal, SignalOutcome + tests
- [ ] **S1.2** — `src/signals/protocol.py` + `src/signals/prompt.py`: SignalProvider protocol + build_prompt pure function + tests
- [ ] **S1.3** — `src/signals/aggregator.py`: SignalAggregator consensus + validation + confidence gate + tests
- [ ] **S2.1** — `src/signals/store.py`: SignalStore init_db + write methods (record_snapshot, record_response, record_signal, record_outcome) + tests
- [ ] **S2.2** — `src/signals/store.py`: SignalStore read methods (get_snapshot, get_signal, get_outcome, get_all_outcomes) + tests
- [ ] **S3.1** — `src/signals/providers/mock.py`: MockSignalProvider — deterministic, Protocol-compliant + tests
- [ ] **S3.2** — `src/signals/providers/gpt4o.py`: GPT4oSignalProvider via OpenRouter + tests
- [ ] **S3.3** — `src/signals/providers/grok.py`: GrokSignalProvider — Phase 1 OpenRouter shim + Phase 2 xAI direct + tests
- [ ] **S3.4** — `src/signals/providers/gemini.py`: GeminiSignalProvider — Phase 1 OpenRouter shim + Phase 2 Google AI SDK + tests
- [ ] **S4.1** — `src/signals/factory.py`: build_providers — env-driven provider selection with safe fallback + tests
- [ ] **S5.1** — `config/signals.toml` + `.env.example`: config + env vars (no tests)
- [ ] **S5.2** — `scripts/morning_signal.py`: 09:15 AM pipeline cron (no unit tests)
- [ ] **S5.3** — `scripts/record_signal_outcome.py`: 03:00 PM outcome recorder (no unit tests)
- [ ] **S5.4** — `scripts/signal_report.py`: on-demand performance report with random baseline (no unit tests)
- [ ] **S6** — Docs close: CONTEXT.md tree, DECISIONS.md entry, TODOS.md log
