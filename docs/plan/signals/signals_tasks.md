# Signals — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/signals/signals_stories.md`.

---

- [x] **S1.1** — `src/signals/models.py`: Direction, TradeAction, MarketSnapshot, SignalResponse,
  DailySignal, SignalOutcome + tests | Owner: Antigravity | Model: antigravity | Review: persona | SHA: 8d295c6
- [x] **S1.2** — `src/signals/protocol.py` + `src/signals/prompt.py`: SignalProvider protocol +
  build_prompt pure function + tests | Owner: Antigravity | Model: Gemini 3.1 Pro (Low) | Review: persona | SHA: 6ea9028
- [x] **S1.3** — `src/signals/aggregator.py`: SignalAggregator consensus + validation + confidence gate + tests | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: 4c5e7e6
- [x] **S2.1** — `src/signals/store.py`: SignalStore init_db + write methods (record_snapshot,
  record_response, record_signal, record_outcome) + tests | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: 2aa5979
- [x] **S2.2** — `src/signals/store.py`: SignalStore read methods (get_snapshot, get_signal, get_outcome,
  get_all_outcomes) + tests | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: fc4a8d4
- [x] **S3.1** — `src/signals/providers/mock.py`: MockSignalProvider — deterministic, Protocol-compliant + tests | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: 1d5fbbd
- [x] **S3.2** — `src/signals/providers/gpt4o.py`: GPT4oSignalProvider via OpenRouter + tests | SHA: 12ba97a
- [x] **S3.3** — `src/signals/providers/grok.py`: GrokSignalProvider — Phase 1 OpenRouter shim + Phase 2 xAI direct + tests | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: 2b04546
- [x] **S3.4** — `src/signals/providers/gemini.py`: GeminiSignalProvider — Phase 1 OpenRouter shim +
  Phase 2 Google AI SDK + tests | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: 41254dc
- [x] **S4.1** — `src/signals/factory.py`: build_providers — env-driven provider selection with safe fallback + tests | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: 417cb5f
- [x] **S5.1** — `config/signals.toml` + `.env.example`: config + env vars (no tests) | Owner: Claude | Model: Sonnet 5 | Review: docs/config-only | SHA: 80edf53
  <!-- .env.example kept local-only: untracked + blanket-ignored by .gitignore `.env*`; edit applied on disk, not committed -->

- [ ] **S5.2a** — `scratch/2026-09-07_signal_input_sources.py` source-discovery spike (persistent) +
  `src/signals/market_inputs.py`: `fetch_gift_nifty` / `fetch_fii_data` / `fetch_usd_inr` against
  Upstox / Dhan / Nuvama + offline tests | Owner: Claude
- [ ] **S5.2b** — `src/signals/snapshot.py`: `assemble_market_snapshot(broker)` — clean fields
  (spot / VIX / prev-OHLC / option_chain / monthly_expiry / vix_5d_trend) + `market_inputs` calls + tests | Owner: Claude
- [ ] **S5.2** — `scripts/morning_signal.py`: 09:15 AM pipeline cron — pure wiring over
  `assemble_market_snapshot` + `build_providers` + aggregator + store + Telegram (no unit tests)
- [ ] **S5.3** — `scripts/record_signal_outcome.py`: 03:00 PM outcome recorder (no unit tests)
- [ ] **S5.4** — `scripts/signal_report.py`: on-demand performance report with random baseline (no unit tests)
- [ ] **S6** — Docs close: CONTEXT.md tree, DECISIONS.md entry, TODOS.md log
