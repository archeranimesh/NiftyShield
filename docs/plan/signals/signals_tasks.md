# Signals — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line under **Remaining work**. That is your
> only task for this session. Tick the box and append `| SHA: <sha>` when done. Add one line
> to `TODOS.md`.
> Full story spec for each task: `docs/plan/signals/signals_stories.md` (same task ID).

---

## Remaining work — in execution order

The pipeline is code-complete through S5.4 and all three crons are live (Phase 1
`openrouter_only`). What is left is the Telegram message layer, then a holiday guard, then
the docs close. **Do these in order — 1 → 5.**

| # | Task | File(s) | Gist |
|---|---|---|---|
| 1 | **S5.5c** | `scripts/morning_signal.py` | 09:15 directional message → agreed vertical layout |
| 2 | **S5.5a** | `scripts/record_signal_outcome.py` | 16:00 outcome message (executed / would-be / NO_TRADE) |
| 3 | **S5.5d** | `scripts/signal_report.py` | 16:35 full report pushed to Telegram |
| 4 | **S5.5b** | `scripts/morning_signal.py` + `scripts/signal_report.py` | NSE-holiday early-exit guard |
| 5 | **S6** | docs only | Close the story — CONTEXT.md / DECISIONS.md / TODOS.md / README |

After S6 the `signals/` story is closed. Next work moves to
**`docs/plan/signals-paper-track/`**, starting at **SPT-1** (council checkpoint, no code) —
that track turns the daily consensus into a real paper trade and its SPT-5 exit message
eventually supersedes S5.5a.

---

### 1 · S5.5c — `morning_signal.py` 09:15 directional message

- [x] **S5.5c** — reformat the `morning_signal.py` entry message to the agreed layout
  (discussion 2026-09-08). A blank line follows the bold header in every variant; a blank
  line separates sections.

  Consensus:
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

  Reference renderer: `format_directional_v3` in
  `scratch/2026-09-08_signal_telegram_messages.py` (messages 1–3, validated on-device
  2026-09-08).
  Entry band = **mean of the agreeing models' `entry_premium_low` / `_high`** (consistent
  with `record_signal_outcome._consensus_entry_premium`), not a single model's band.
  Bold header requires moving the escaping boundary: `_format_signal_notification` escapes its
  own dynamic parts (`escape_markdown` per value) and emits literal `*` for markup; the caller
  in `morning_signal.py` stops wrapping the whole string. Strike via `format_strike`
  (identifier — no thousands separator, `FORMATTING.md`); premium band via `format_money`.
  Register the formatter in `tests/unit/notifications/test_escaping_guard.py`. Extend the
  no-network formatter tests (directional + NO_TRADE render). Key reason / key risk:
  **dropped from the message** per discussion 2026-09-08 (kept in `signal_responses` DB rows
  for the report).
  | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: <pending>

---

### 2 · S5.5a — `record_signal_outcome.py` 16:00 outcome message

- [x] **S5.5a** — **Phase-1 interim outcome message** (revived 2026-09-09; was superseded →
  SPT-5). `scripts/record_signal_outcome.py` posts a Telegram message on its 16:00 run —
  executed / not-taken (would-be P&L) / NO_TRADE — restyled to the S5.5c vertical layout
  (bold header + blank line + one emoji-prefixed line per field). The script currently sends
  nothing. Would-be P&L for the not-taken case is computed **in the formatter** from
  `entry_premium` / `exit_premium` (both populated by `--auto` even when `executed=False`);
  no `SignalOutcome` / `SignalStore` change. Non-fatal send via `build_notifier()` mirroring
  `morning_signal`. `NO_TRADE` and non-`--auto` runs missing a premium fall back to the
  close-only render. Reference renderer: `format_outcome_notification` in
  `scratch/2026-09-08_signal_telegram_messages.py` (messages 6–8, restyled 2026-09-09).
  Tests: no-network render of all three cases + the empty-premium fallback. **SPT-5 still
  supersedes this** when the paper track goes live (real exit replaces the would-be row).
  | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: ce59529

---

### 3 · S5.5d — `signal_report.py` 16:35 digest to Telegram

- [x] **S5.5d** — `scripts/signal_report.py`: push the full 5-section report to Telegram on
  every 16:35 weekday run (currently `print()`-only). Wrap the existing `"\n".join(out)` body
  in a MarkdownV2 fenced code block, escape per the `FORMATTING.md` boundary contract, send
  via `build_notifier()` after the `print()` (non-fatal if no notifier configured, mirroring
  `morning_signal._notify`). Keep the `"No signal outcomes recorded"` early-return
  terminal-only. NSE-holiday guard is S5.5b. Extend the no-network formatter test.
  | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: 51d3e59

---

### 4 · S5.5b — NSE-holiday guard

- [ ] **S5.5b** — NSE-holiday guard: `is_trading_day(market_today())` early-exit (log +
  return 0) at the top of `scripts/morning_signal.py` and `scripts/signal_report.py`,
  mirroring `scripts/pipeline/upstox_chain_snapshot.py`. No new tests (matches existing cron
  pattern).
  | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: <pending>

---

### 5 · S6 — Docs close

- [ ] **S6** — Docs close: `CONTEXT.md` tree, `DECISIONS.md` entry, `TODOS.md` log,
  `docs/plan/README.md` status. Then the `signals/` story is done — move to
  `docs/plan/signals-paper-track/` (SPT-1).

---

## Completed

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
  index F&O positioning to cash-market net flows (`fii_cash_net_cr`/`dii_cash_net_cr`, NSE
  `fiidiiTradeReact`) + test updates. Split out of S5.2a per Animesh (2026-09-07).
  | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: <pending>
- [x] **S5.2a** — `src/signals/market_inputs.py`: `fetch_gift_nifty` / `fetch_usd_inr` /
  `fetch_fii_data` + offline tests (source-discovery spike `c0208c9`..`a60dc29`).
  | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: <pending>
- [x] **S5.2b** — `BrokerClient.get_ohlc(instruments, interval="1d")` across `protocol.py` +
  `upstox_market.py` + `upstox_live.py` + `mock_client.py`, and `SignalStore.get_recent_snapshots(n)`
  + tests. | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: e1b5a0a
- [x] **S5.2c** — `src/signals/snapshot.py`: `assemble_market_snapshot` — the 7 non-S5.2a
  `MarketSnapshot` fields, over the S5.2b prereqs. | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: b33a43d
- [x] **S5.2** — `scripts/morning_signal.py`: 09:15 pipeline cron — wiring over
  `assemble_market_snapshot` + `build_providers` + aggregator + store + Telegram (no unit tests) | SHA: e299a6b
- [x] **S5.3** — `scripts/record_signal_outcome.py`: 16:00 outcome recorder (no unit tests) | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: a387349
- [x] **S5.4** — `scripts/signal_report.py`: on-demand performance report with random baseline (no unit tests) | Owner: Claude | Model: Sonnet 5 | Review: code-reviewer | SHA: <pending>
- [x] **S5.5** — Rollout state recorded + Telegram message-format scope settled (discussion,
  no code). Runbook dropped 2026-09-09 — all three crons already live on the Mac host:
  ```
  30 09 * * 1-5  scripts.morning_signal             >> logs/morning_signal.log
  00 16 * * 1-5  scripts.record_signal_outcome --auto >> logs/record_signal_outcome.log
  35 16 * * 1-5  scripts.signal_report              >> logs/signal_report.log
  ```
  Rollout phase: **Phase 1 `openrouter_only`**. `DECISIONS.md` carries the 2026-09-09 bullet.
  Remaining Telegram work → S5.5c / S5.5a / S5.5d above. `signals-paper-track` SPT-3 owns the
  entry message. | Owner: Claude | Model: Sonnet 5 | Review: docs-only | SHA: 0811b65
