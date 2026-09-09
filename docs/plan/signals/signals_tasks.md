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
- [x] **S5.5** — Rollout state recorded + Telegram message-format scope settled (discussion,
  no code). **Runbook dropped** (Animesh 2026-09-09) — all three crons are already live on the
  Mac host, so a separate enablement runbook is redundant:
  ```
  30 09 * * 1-5  scripts.morning_signal             >> logs/morning_signal.log
  00 16 * * 1-5  scripts.record_signal_outcome --auto >> logs/record_signal_outcome.log
  35 16 * * 1-5  scripts.signal_report              >> logs/signal_report.log
  ```
  Rollout phase: **Phase 1 `openrouter_only`** (single `OPENROUTER_API_KEY`, all three models
  via OpenRouter). `DECISIONS.md` carries the rollout bullet (2026-09-09). Remaining work is
  Telegram message formatting, tracked in the boxes below:
  - ✅ **09:15 directional signal** — finalized, spec in S5.5c, on-device validated
    (`scratch/2026-09-08_signal_telegram_messages.py` messages 1–3): CONSENSUS / NO CONSENSUS /
    PIPELINE FAILED, bold header + blank line + emoji lines.
  - ⏸ **entry + exit / P&L messages** — moved to `signals-paper-track` SPT-3 (entry) and
    SPT-5 (exit); the signals track is becoming a real paper trade (Animesh 2026-09-08), so
    the 15:00 "outcome" message is replaced by an actual exit message. Candidates in
    `docs/plan/signals-paper-track/stories.md` §SPT-3 / §SPT-5 — **still to correct/finalize
    there.**
  - ⬜ **`signal_report.py` 16:35 digest to Telegram** — decided (Animesh 2026-09-09): push
    **every weekday** run, the **full 5-section report** in a MarkdownV2 fenced code block
    (escaped per the `FORMATTING.md` boundary contract). Implementation tracked as **S5.5d**.
  | Owner: Claude | Model: Sonnet 5 | Review: docs-only | SHA: <pending>

- [ ] **S5.5a** — **SUPERSEDED → `signals-paper-track` SPT-5.** The 15:00 `SignalOutcome`
  Telegram message is replaced by SPT-5's exit message now that the track paper-trades for
  real (entry/exit, not a would-have-done row). Do not implement here. `/work` skips this box;
  close it in S6 with `SHA: n/a (won't-do → SPT-5)`. Reference renderer
  `format_outcome_notification` in `scratch/2026-09-08_signal_telegram_messages.py` carries
  forward to SPT-5. | Owner: Claude | Model: n/a | Review: none | SHA: <pending>
- [ ] **S5.5b** — NSE-holiday guard: `is_trading_day(market_today())` early-exit (log + return 0)
  at the top of `scripts/morning_signal.py` and `scripts/signal_report.py`, mirroring
  `scripts/pipeline/upstox_chain_snapshot.py`. No new tests (matches existing cron pattern).
  | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: <pending>
- [ ] **S5.5c** — reformat `morning_signal.py` entry message to the agreed layout (discussion
  2026-09-08):
  A blank line follows the bold header in every variant; a blank line separates sections.
  ```
  *📈 CONSENSUS: BULLISH*

  🎯 Strike: 24800
  📊 Confidence: 3.5 / 5.0
  💰 Entry band: ₹58.00 – ₹72.00

  *Model Votes:*
  👍 Agree: grok, gpt4o
  👎 Dissent: gemini
  ```
  Direction emoji: 📈 BULLISH / 📉 BEARISH.

  NO_TRADE, responses present (split / low-confidence / majority-neutral) — one emoji line per
  model (📈 BULLISH / 📉 BEARISH / ➖ NEUTRAL):
  ```
  *⏸ NO TRADE · NO CONSENSUS*

  📈 grok: BULLISH
  📉 gpt4o: BEARISH
  ➖ gemini: NEUTRAL
  ```

  NO_TRADE, zero valid responses (`not signal.responses`) — operational alert, worded as what
  the pipeline actually does (it does NOT pause; next day's cron runs normally). The `0 / N`
  count uses `len(providers)`, not a literal 3:
  ```
  *🚨 SIGNAL PIPELINE FAILED*

  ❌ 0 / 3 models responded
  ⏸ No signal issued today

  👉 Check logs before the next run
  ```

  Reference renderer: `format_directional_v3` in `scratch/2026-09-08_signal_telegram_messages.py`
  (messages 1–3, validated on-device 2026-09-08).
  Entry band = **mean of the agreeing models' `entry_premium_low` / `_high`** (consistent with
  `record_signal_outcome._consensus_entry_premium`), not a single model's band.
  Bold header requires moving the escaping boundary: `_format_signal_notification` escapes its
  own dynamic parts (`escape_markdown` per value) and emits literal `*` for markup; the caller
  in `morning_signal.py` stops wrapping the whole string. Strike via `format_strike` (identifier
  — no thousands separator, `FORMATTING.md`); premium band via `format_money`. Register the
  formatter in `tests/unit/notifications/test_escaping_guard.py`. Extend the no-network
  formatter tests (directional + NO_TRADE render). Key reason / key risk: **dropped from the
  message** per discussion 2026-09-08 (kept in `signal_responses` DB rows for the report).
  | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: <pending>

- [ ] **S5.5d** — `scripts/signal_report.py`: push the full 5-section report to Telegram on
  every 16:35 weekday run (currently `print()`-only). Wrap the existing `"\n".join(out)` body
  in a MarkdownV2 fenced code block, escape per the `FORMATTING.md` boundary contract, send
  via `build_notifier()` after the `print()` (non-fatal if no notifier configured, mirroring
  `morning_signal._notify`). Keep the `"No signal outcomes recorded"` early-return
  terminal-only. NSE-holiday guard is S5.5b. Extend the no-network formatter test.
  | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: <pending>

- [ ] **S6** — Docs close: CONTEXT.md tree, DECISIONS.md entry, TODOS.md log
