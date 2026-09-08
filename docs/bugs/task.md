# docs/bugs/ — Task Checklist

> Find the first unchecked `- [ ]` line **that belongs to a `BUG-ID` checklist** (see
> `docs/bugs/prompt.md` for the full session-start protocol). Tick the box and append
> `| SHA <commit_sha>` when done. Add one line to `TODOS.md` session log. Full bug detail for
> each item — symptom, root cause, suggested fix — lives in `docs/bugs/bugs.md`, never here.
>
> **Format contract:** every line in this file is `- [ ]`/`- [x]` **`**Bnnn.x**` — one short
> task sentence.` — optionally followed by `| SHA <sha>` once committed. Do not append
> implementation narrative, test lists, or review findings inline here — that detail belongs in
> the matching `docs/bugs/bugs.md` entry (add an "Implementation progress" note there instead).
> This file is a checklist, not a log.
>
> **Once every `Bnnn.x` line under a `BUG-ID` is checked** and the bug's `bugs.md` Status is
> ✅ Fixed: move the whole section to `docs/archive/bugs/task.md` (and the matching `bugs.md`
> entry to `docs/archive/bugs/bugs.md`) in the closing commit. Do not leave fully-checked
> sections in this file — an unchecked line here should always mean real open work.

---

> BUG-033 closed 2026-08-24 (SHA `ef1c341`) — section moved to `docs/archive/bugs/{bugs,task}.md`.
> BUG-034 closed 2026-08-24 (SHA `88df26e`) — section moved to `docs/archive/bugs/{bugs,task}.md`.
> BUG-032 closed 2026-08-24 (SHA `67d4010`, backfill applied same day) — section moved to `docs/archive/bugs/{bugs,task}.md`.
> BUG-036 closed 2026-08-24 (SHA `d40c3a1`, backfill applied same day) — section moved to `docs/archive/bugs/{bugs,task}.md`.
> BUG-035 closed 2026-08-24 (SHA `0ecd86b`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

## BUG-041 — signals `grok` + `gemini` providers fail on OpenRouter (stale hardcoded model slugs)

- [x] **B041.1** — Confirmed both slugs retired; gemini 400 is slug not `response_format`. Decision: slugs env-configurable, Animesh fills live values. | SHA `f1fad55`
- [x] **B041.2** — `SIGNAL_MODEL_{GROK,GPT4O,GEMINI}` threaded through `factory._construct`; `model` param on grok/gemini providers. | SHA `f1fad55`
- [ ] **B041.3** — Capture the OpenRouter error-response body into the
  `DataFetchError` message (read body before `raise_for_status`) in all three
  providers.
- [ ] **B041.4** — Also wire `SIGNAL_MIN_CONFIDENCE` (+ optionally a consensus
  count) through the same factory pass into `SignalAggregator` — currently
  documented in `.env.example` but hardcoded.
- [ ] **B041.5** — Tests: `test_signals_factory.py` for the slug/env override
  + defaults; provider tests for the error-body capture. `pytest tests/unit/`
  green → real `@code-reviewer` → commit. One manual `morning_signal` run with
  all three providers before closing.
- [ ] **B041.6** — Flip `bugs.md` BUG-041 status ✅ + SHA; move both sections
  to `docs/archive/bugs/{bugs,task}.md`; `TODOS.md` session-log line.

## BUG-040 — signals `_fetch_prev_ohlc` crash: `get_ohlc` shape is fictional + `1d` `prev_ohlc` null intraday

- [x] **B040.1** — Scratch-verify (read-only) the three candidate endpoints and
  survey how other NIFTY strategies source daily OHLC —
  `scratch/2026-09-08_signals_ohlc_probe.py`. Decide the fix's data source. | SHA `5efb464`
- [x] **B040.2** — Implemented `get_historical_candles_sync` + async delegation; v2 day-candle form. | SHA `50a5ce4` + `680778b`
- [x] **B040.3** — Rewrote `_fetch_prev_ohlc` onto `get_historical_candles` (positional-list rows, prev-session guard). | SHA `50a5ce4` + `680778b`
- [x] **B040.4** — Replaced stale `{"ohlc": {...}}` fixtures; added fetcher + guard tests. | SHA `50a5ce4` + `680778b`
- [x] **B040.5** — Flipped `src/client/CLAUDE.md` row; `get_ohlc` marked unused (kept, docstrings corrected). | SHA `50a5ce4`
- [ ] **B040.6** — Suite green (3322) + real `@code-reviewer` clean (0 CRITICAL/ERROR).
  Blocked on live host: one manual `python -m scripts.morning_signal` run (logs + Telegram).
- [ ] **B040.7** — Flip `bugs.md` BUG-040 status to ✅ Fixed + SHA; move both
  sections to `docs/archive/bugs/{bugs,task}.md`; `TODOS.md` session-log line.
  Then S5.5 rollout walkthrough can resume.

## BUG-038 — `OverlayCloser`'s three `self._notifier.send()` calls are unawaited (never sent)

- [ ] **B038.1** — `trace_path` both methods' callers (`close_collar_all`,
  `monetize_collar_put`) to confirm no caller already runs inside an event
  loop before picking sync-vs-async fix.
- [ ] **B038.2** — Fix: make both methods `async def` + `await` the send (or
  a sync-dispatch wrapper if callers require sync). Update callers.
- [ ] **B038.3** — Add a repro test using a `TelegramNotifier`-shaped
  (async-`send`) test double, not the current sync `MockNotifier`/`notifier`
  fixture, so this class of bug is caught in future.
- [ ] **B038.4** — Separately: repro-test `escape_markdown()` against a
  literal backslash in the input (see `bugs.md` BUG-038 note) — scope a
  fix in `src/notifications/markdown.py` if confirmed, coordinate with
  `docs/plan/telegram-markdown-migration/` MD-6's baseline if it touches
  escaped call sites.
- [ ] **B038.5** — Review: real `code-reviewer` (mandatory — financial-logic
  notification paths).
- [ ] **B038.6** — Commit, update `bugs.md` BUG-038 status to ✅ Fixed + SHA,
  update `TODOS.md`.

## BUG-037 — `mark_trade_closed()` also never wired into CSP/IC v1/v2 close paths (54 stale flat legs)

- [x] **B037.1** — Trace `close_csp_leg`/`close_ic_legs`/`roll_ic_legs` (and
  `roll_down_and_out`) call sites for any partial-close/roll scenario that can
  leave `net_qty != 0` on the leg being written — CSP's `ROLL_DOWN_AND_OUT`
  and IC's spread-only closes are partial at the strategy level, unlike
  BUG-035's overlay legs. Confirms whether `mark_trade_closed()` can be called
  unconditionally per closing trade or needs a flatness check first. See
  `docs/bugs/bugs.md` BUG-037. | SHA `b399a3e`
- [x] **B037.2** — Trace `scripts/strategies/three_track/paper_3track_roll.py`'s
  futures/proxy roll-close write path for the same gap — the `base_futures`
  and `base_ditm_call` stale rows found may or may not share this root cause;
  not yet confirmed (unlike CSP/IC, which are confirmed via grep). | SHA `b399a3e`
- [x] **B037.3** — Add `store.mark_trade_closed(...)` (or the appropriate
  partial-close-safe equivalent per B037.1) to `close_csp_leg`,
  `close_ic_legs`, `roll_ic_legs`, and the futures/proxy roll-close path
  (per B037.2, if confirmed in scope). | SHA `5369c0e`
- [x] **B037.4** — Tests: regression coverage per call site mirroring
  BUG-035's B035.4 pattern (mark_trade_closed called on full close, not
  called on partial close/duplicate insert). | SHA `5369c0e`
- [x] **B037.5** — Re-run `scripts/dev/backfill_mark_trade_closed_overlay.py`
  (already generalized, built for BUG-035) against the live DB once B037.3
  lands — it already covers all 54 rows found in this bug's discovery scan.
  Verified 2026-08-24 via `scratch/2026-08-24_check_stale_flat_legs.py`
  (identical read-only query) run both through the device bridge and
  directly by Animesh on the live host — same file, same result: 0 stale
  flat legs, 134 total trade rows. Animesh confirms he ran the backfill
  script with `--dry-run` earlier — note `--dry-run` never writes, so it
  cannot be the mechanism that resolved the 54 rows found at discovery; the
  actual cause is unconfirmed (possibly a prior `--apply` run, or the
  discovery-time count reflected DB state that's since moved on). No open
  action either way — nothing stale remains to backfill.
- [ ] **B037.6** — Review: real `code-reviewer` or `general-purpose` +
  `REVIEW.md` substitute (mandatory — touches live paper-trading state
  transitions across CSP/IC, the two highest-volume strategy families).
- [ ] **B037.7** — Commit, update `bugs.md` BUG-037 status to ✅ Fixed + SHA,
  update `TODOS.md`.

## BUG-019 — Investigation: does every strategy show a live-tick vs. EOD-snapshot P&L disparity?

> Moved to the bottom of this file deliberately (2026-08-24, Animesh) — the 08-14/17/19/20/21
> diff (see `bugs.md` BUG-019) found no systematic staleness bug, just ordinary intraday
> movement, so this is low-priority relative to BUG-030/031. Diagnostics are being left running
> longer rather than removed now. Keep this section last so the session-start protocol picks up
> BUG-030/031 first.

- [ ] **B019.1** — Diagnostics committed (SHA `f7177b6`) and now diffed against 5 live trading
  days (08-14, 08-17, 08-19, 08-20, 08-21) — no systematic bias found, gaps flip sign and scale
  with intraday movement (one exact 0.00 diff on a low-movement day confirms the mechanism
  itself is sound). Leaving diagnostics running per Animesh's call (2026-08-24) rather than
  closing/removing yet. Full context: `docs/bugs/bugs.md` BUG-019.
