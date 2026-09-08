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

- [x] **S1.1a** — `src/signals/models.py` + `src/signals/prompt.py`: redefine `FIIData` from
  index F&O positioning (`net_futures_cr`/`net_options_cr`, unreachable per S5.2a spike) to
  cash-market net flows (`fii_cash_net_cr`/`dii_cash_net_cr`, NSE `fiidiiTradeReact`) + test
  updates. Split out of S5.2a per Animesh (2026-09-07). | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: <pending>

- [x] **S5.2a** — source-discovery spike ✅ done (`scratch/2026-09-07_signal_input_sources.py`,
  commits `c0208c9`..`a60dc29`; all 3 sources confirmed + real FII file downloaded — see
  `signals_stories.md` §S5.2a). **Remaining:** build `src/signals/market_inputs.py` —
  `fetch_gift_nifty` → `get_ltp("GLOBAL_INDEX|SGX NIFTY")`; `fetch_usd_inr` → nearest-monthly
  `NCD_FO` USDINR future via `get_ltp` + `InstrumentLookup`; `fetch_fii_data` → NSE
  `fiidiiTradeReact` JSON (cash-market net) — + offline tests. **Decide first:** redefine
  `FIIData` to `fii_cash_net_cr`/`dii_cash_net_cr` (F&O positioning data is unreachable —
  §S5.2a). **Resolved: done in S1.1a.** Full per-field recipe in the story §Step 2. | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: <pending>
- [x] **S5.2b** — prereqs for the snapshot assembler: add `BrokerClient.get_ohlc(instruments,
  interval="1d")` across `src/client/protocol.py` + `upstox_market.py` + `upstox_live.py` +
  `mock_client.py` (for `prev_*`), and `SignalStore.get_recent_snapshots(n)` in
  `src/signals/store.py` (for `vix_5d_trend`) + tests. Split out of S5.2b per Animesh
  (2026-09-08) — was the "prereq commit" half. Detail in `signals_stories.md` §S5.2b.
  | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: e1b5a0a
- [x] **S5.2c** — `src/signals/snapshot.py`: `assemble_market_snapshot` — the 7 non-S5.2a
  `MarketSnapshot` fields, over the S5.2b prereqs. Full per-field fetch recipe +
  `OptionChainSummary` derivation in `signals_stories.md` §S5.2c. | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: b33a43d
- [x] **S5.2** — `scripts/morning_signal.py`: 09:15 AM pipeline cron — pure wiring over
  `assemble_market_snapshot` + `build_providers` + aggregator + store + Telegram (no unit tests) | SHA: e299a6b
- [x] **S5.3** — `scripts/record_signal_outcome.py`: 03:00 PM outcome recorder (no unit tests) | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: a387349
- [x] **S5.4** — `scripts/signal_report.py`: on-demand performance report with random baseline (no unit tests) | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: <pending>
- [ ] **S5.5** — Operational rollout walkthrough (discussion, no code): cron enablement
  (crontab lines + host + log paths + market-calendar guard for `morning_signal.py` /
  `record_signal_outcome.py` / `signal_report.py`), Telegram message shapes for signal entry
  + outcome/close incl. P&L display, LLM response mechanics (OpenRouter vs direct SDK, the
  JSON schema each model emits, `SIGNAL_PHASE`), and the end-to-end first-run setup (env
  vars, `config/signals.toml`, `SignalStore.init_db`, `.env.example`). Output: an ops runbook
  (location decided in the discussion) + `DECISIONS.md` entry. Must land before S6.
  | Owner: Claude | Model: Sonnet 5 | Review: docs-only | SHA: <pending>
- [ ] **S6** — Docs close: CONTEXT.md tree, DECISIONS.md entry, TODOS.md log
