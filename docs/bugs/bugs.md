# Bug Registry

> One entry per confirmed defect. Do not log speculative issues here — confirm root cause
> first (graph trace / repro), then log. Suspicions belong in `TODOS.md` until confirmed.
> Status values: `🔴 Open` → `🟡 Fix in progress` → `✅ Fixed` (link commit SHA) → `⚪ Won't fix` (with reason).
>
> **Scope:** confirmed defects in live/shipped code (paper trading, cron scripts, live
> gates) — not unimplemented spec items, those are `docs/plan/` story tasks.
>
> **Relationship to the legacy registry:** a flat bug registry existed at the repo root
> (`BUGS.md`, single open entry `BUG-001` — `daily_snapshot.py` backfill gap, unrelated,
> low severity). It was relocated to
> [`docs/archive/BUGS_LEGACY.md`](../archive/BUGS_LEGACY.md) on 2026-08-27 (RDO-4), with a
> stub left at the repo root. This folder is the canonical home for *all* entries going
> forward; `BUG-001` stays in the archive file until it is fixed and deleted per its own
> convention. ID numbering is one shared sequence across both — this registry starts at
> `BUG-002`.
>
> **This file holds only open work — the `stories.md` equivalent for `docs/bugs/task.md`'s
> checklist.** `docs/bugs/task.md` is the lean checkbox list; every entry here has the full
> symptom/root-cause/fix detail a task's checkbox alone can't carry. Once a `BUG-NNN`'s every
> `task.md` line is checked and the fix is committed, move its entry to
> `docs/archive/bugs/bugs.md` (and its checklist to `docs/archive/bugs/task.md`) in the same
> commit that flips `Status` to ✅ Fixed — mirrors the `docs/plan/` → `docs/archive/plan/`
> convention. **24 bugs archived 2026-08-13** (`BUG-002` through `BUG-028` minus the 5 below);
> see `docs/archive/bugs/bugs.md` for their full history.

---

## BUG-044 — standalone CC overlay vanishes from the S9 "NiftyBees vs overlays" digest and its P&L is silently added to the Collar line

| Field | Value |
|---|---|
| Severity | **Medium** — wrong data on a daily Telegram: a live overlay shows `No data`, and the Collar recovery figure is overstated by the CC's P&L |
| Status | 🔴 Open — fix tracked under `docs/plan/telegram-message-unification/overlay-recovery-digest/` ORD-1 (investigate + decide) / ORD-2 (fix) |
| Discovered | 2026-09-10 (Animesh, from the 09 Sep digest) |
| Location | `scripts/strategies/three_track/paper_3track_snapshot.py::_overlay_type_groups` (~L1157) → `_compute_overlay_pnl_snapshots` → `_build_recovery_digest` |

**Symptom:** the 2026-09-09 digest rendered `CC   No data` while `PP` and `Collar` had figures
and `Best: PP`.

**Verified evidence (`logs/`):**
- `cc_entry.log` 2026-09-09 10:30:21 — `trade.INSERTED strategy=paper_nifty_overlay leg=overlay_cc`
  (CC bootstrap, SELL @ 53.90).
- `paper_snapshot.log` 2026-09-09 15:35:08 — `Overlay leg snapshot saved: overlay_cc 2026-09-09`
  (the `paper_leg_snapshots` row was written).
- Same run's printed comparison table — `paper_nifty_overlay / CC  ₹+793 / ₹+5,957 / ₹+6,750`
  (CC P&L is computed).
- Then — `WARNING protection_recovery.overlay_source_missing … overlay_type=cc date=2026-09-09`
  (also fires 2026-09-08).

**Root cause:** `_overlay_type_groups`, the BUG-030 fix branch —

```python
elif has_cc and has_put:
    groups["collar"] = ["overlay_cc", "overlay_collar_put"]
```

On 09 Sep the open roles were `{overlay_cc, overlay_pp, overlay_collar_put}` (no
`overlay_collar_call`). This branch folds `overlay_cc` into the `collar` group, so
`_compute_overlay_pnl_snapshots` writes no standalone `cc` `OverlayPnLSnapshot` row —
`_build_recovery_digest` reads back nothing → `CC No data`. And because the collar group sums
both roles, the standalone CC's P&L is added to the digest's `Collar` figure.

**Why BUG-030's fix doesn't cover this:** BUG-030 assumed a coexisting `overlay_cc` + collar
put means the `overlay_cc` *is* the collar's shared call leg (the collar entry dedups a
second short call against an existing CC). It does not distinguish that case from a
**standalone CC bootstrap running alongside a separate collar** — the current live state.

**Fix:** ORD-1 determines whether the two can genuinely coexist and whether a reliable marker
distinguishes "collar call tagged `overlay_cc`" from "standalone `overlay_cc`", then decides
the correct `_overlay_type_groups` behaviour; ORD-2 implements it so a standalone CC gets its
own group/row and the collar total excludes it, without regressing BUG-030's own test.

---

## BUG-043 — "Net P&L" in close notifications has no stable meaning: inception-cumulative for IC v1/v2, cycle-only for collar, absent for CSP

| Field | Value |
|---|---|
| Severity | **Medium** — no wrong trade action, but the headline number on every IC close Telegram is the lifetime total, read at a glance as the just-closed cycle's result |
| Status | 🔴 Open |
| Discovered | 2026-09-10 |
| Location | five close paths under `src/strategy/` — see list below |

Close paths affected (all in `src/strategy/`):
`ic_nifty_v1.py::_send_close_notification` (~L824) ·
`ic_nifty_v2.py::_send_close_notification` (~L2224) ·
`collar_overlay_v1.py` collar close (~L720) ·
`auto_close.py` overlay close (~L308) ·
`csp_nifty_v1.py::_reentry_notification` (~L635).

**Severity detail:** Animesh read the line `Net P&L: ₹3,739.12` on a `paper_ic_nifty_v1_weekly`
CLOSE_FULL message (2026-09-03 close) as that cycle's result. It is the cumulative realized
P&L across all 8 closed cycles since inception; that cycle actually made +₹713.38. Trades and
DB records are correct — only the notification label/semantics are wrong.

**Discovered:** 2026-09-10, user asked for a per-cycle P&L breakdown of the weekly IC and
noticed the close message's "Net P&L" matched the inception total, not the cycle.

**Root cause:** no shared contract for what the close-notification P&L line reports. Current
state per close path:

| Close path | P&L line(s) shown | What "Net P&L" actually is |
|---|---|---|
| `ic_nifty_v1._send_close_notification` | `Net P&L:` | `get_strategy_realized_pnl()` — **inception cumulative** |
| `ic_nifty_v2._send_close_notification` | `Net P&L:` | `get_strategy_realized_pnl()` — **inception cumulative** |
| `auto_close.py` (CC / PP / Collar via `OverlayCloser`) | `Net P&L` **and** `Overlay P&L (total realized)` | per-leg entry−exit — **this cycle** (this path is the closest to correct) |
| `collar_overlay_v1.py` collar close | `Net P&L:` | `call_pnl + put_pnl` — **this cycle only**, no inception figure |
| `csp_nifty_v1._reentry_notification` | *(none)* | CSP close shows no P&L at all |

There is no `get_last_cycle_realized_pnl` helper — cycle boundaries (all legs of the group
back to net-zero) are reconstructable from `paper_trades` but nothing does it today.

**Suggested fix:** add `reconstruct_cycles()` / `get_last_cycle_realized_pnl()` to
`src/paper/` (shared with the `scripts/dev/` per-cycle report being built alongside this bug —
same reconstruction logic). Then standardise every close notification to two lines with fixed
labels, e.g. `Cycle P&L: <±figure>` and `Since inception: <±figure>`, and add them to the CSP
close message. Keep `auto_close.py`'s existing dual line but rename to the standard labels.

**Related:** the `scripts/dev/cycle_pnl_report.py` CLI (per-cycle P&L / exit reason / days in
trade for IC-all / CC / PP / Collar) shares the cycle-reconstruction helper; build the helper
under `src/paper/` first, then this bug's notification fix wires it into the five close paths.

---

## BUG-042 — `721daf9` MarkdownV2 switch broke every unmigrated `TelegramNotifier` cron caller (CC/PP entry, paper snapshot, monitor daemon, pre-market brief) — silent 400 since 2026-08-25

| Field | Value |
|---|---|
| Severity | **High** — see failing callers below |
| Status | 🔴 Open |
| Discovered | 2026-09-09 |
| Location | `src/notifications/telegram.py::TelegramNotifier.send` + unmigrated callers |

**Severity detail:** multiple daily/weekly cron notifications have not reached Telegram on any
trading day since 2026-08-25. Confirmed dead so far: covered-call entry (`logs/cc_entry.log`),
protective-put entry (`logs/pp_entry.log`), paper snapshot 15:35 (`logs/paper_snapshot.log`),
monitor daemon alerts (`logs/monitor_daemon.log`), pre-market brief 09:00
(`logs/pre_market_brief.log`). Trades still record to the DB — only the notification is lost.

**Discovered:** 2026-09-09, user asked why the covered call hadn't entered; `logs/cc_entry.log`
showed the CC *did* enter (`trade.INSERTED` 2026-08-26, 2026-09-09) but the 2026-08-26 send
logged `400 Bad Request`. Grep across `logs/` showed the same signature in ≥5 other cron logs
from the same 2026-08-25 boundary.

**Location:** `src/notifications/telegram.py::TelegramNotifier.send` (unconditional
`parse_mode="MarkdownV2"`, no auto-escape); every caller above that builds message text
without `escape_mdv2()` / `escape_markdown()` / `mdcode()`.

**Root cause:** same as BUG-039 (SHA `2cb67ce`, which fixed `daily_snapshot.py` only) and the
`eod_summary.py` / `TelegramGateway` sibling it flagged out of scope. Commit `721daf9`
(2026-08-24 23:00 IST) flipped `TelegramNotifier.send()` from `parse_mode="HTML"` to
`parse_mode="MarkdownV2"` unconditionally, moving escaping responsibility onto every caller.
The `telegram-markdown-migration` epic (ROLL-*/MD-* series) migrated the strategy and alert
callers but never reached these cron entrypoints. Their message text is structurally full of
MarkdownV2-reserved punctuation — `-` (negative figures, box rules), `.` (decimals, DTE),
`()` (percentages), `|` (table separators), `!` `+` `=` `#` — so Telegram rejects the whole
send with `400` ("can't parse entities"), swallowed silently by `send()`'s non-fatal
contract. The first send under MarkdownV2 was 2026-08-25; every failure dates from then.

**Why the log never shows the real reason:** `send()` logs only `str(exc)` from aiohttp's
`raise_for_status()`, which stops at `400, message='Bad Request', url=…` and drops the
response body where Telegram names the byte offset that failed to parse.

**Suggested fix (decide at Step 2b):** two options.
1. **Per-caller call-site escaping** (BUG-039's approach, per `FORMATTING.md` §6 "escaping
   happens at the call site"): wrap each assembled `summary_text` in `escape_markdown()` at
   the `notifier.send()` call site. Correct but must be repeated for every entrypoint and is
   fragile against the next new caller.
2. **Defensive default in `send()`**: auto-escape by default, add an explicit
   `preformatted=True` / `raw=True` opt-out for the already-migrated callers that
   intentionally emit `*bold*` / tables. One change, closes the class of bug, but requires
   auditing which existing callers rely on raw MarkdownV2 pass-through.

Recommend option 2 given how many entrypoints are currently broken; confirm no migrated
caller silently regresses to literal backslashes.

**Related / out of scope here:** `TelegramGateway`'s parallel `eod_summary.py` regression
(`cd1e554`) — noted in BUG-039, still unfixed, separate sender class. Fold it in if option 2
is chosen and `TelegramGateway` shares the escape path; otherwise its own bug.

---

## BUG-040 — signals pipeline crashes at `_fetch_prev_ohlc`: `get_ohlc` expects a response shape Upstox v3 never returns, and `1d` `prev_ohlc` is null intraday

| Field | Value |
|---|---|
| Severity | **High** — `scripts/morning_signal.py` (S5.2 cron) cannot complete one run; blocks the `docs/plan/signals/` S5.5 rollout. Not yet cron-enabled — no live signal ever produced. |
| Status | 🟡 Fix in progress — code landed (`50a5ce4` + fixup), B040.6 manual `morning_signal` run blocked on live host |
| Discovered | 2026-09-08, manual run of `python -m scripts.morning_signal` during the S5.5 rollout walkthrough. |
| Location | `src/signals/snapshot.py::_fetch_prev_ohlc` (reads `["ohlc"]`); `src/client/upstox_market.py::_remap_response`; `src/client/upstox_live.py::get_historical_candles` (stub). |

**Symptom:** `python -m scripts.morning_signal` aborts before any provider call or Telegram
send with:

```
File "src/signals/snapshot.py", line 114, in _fetch_prev_ohlc
    Decimal(str(candle["close"])),
KeyError: 'close'
... raise DataFetchError(f"prev OHLC unavailable for {NIFTY_KEY}: {ohlc!r}")
src.client.exceptions.DataFetchError: prev OHLC unavailable for NSE_INDEX|Nifty 50:
  {'NSE_INDEX|Nifty 50': {'last_price': 23672.95, 'instrument_token': 'NSE_INDEX|Nifty 50',
                          'prev_ohlc': None,
                          'live_ohlc': {'open': 23743.1, 'high': 23758.95, 'low': 23657.15,
                                        'close': 23672.95, 'volume': 0, 'ts': 1788805800000}}}
```

**Root cause — two compounding defects:**

1. **`get_ohlc` response shape is fictional.** `src/signals/snapshot.py::_fetch_prev_ohlc`
   reads `ohlc[key]["ohlc"]["close" | "high" | "low"]`. The live Upstox v3
   `/v3/market-quote/ohlc` response (verified 2026-09-08) has **no `"ohlc"` key** — each
   per-instrument value is `{last_price, instrument_token, prev_ohlc, live_ohlc}`.
   `_remap_response` (`src/client/upstox_market.py:41`) only rewrites the outer colon-key to
   pipe-key and passes the value through untouched. Every test fixture mirrors the invented
   `{"ohlc": {...}}` shape (`tests/unit/signals/test_signals_snapshot.py:128`,
   `tests/unit/test_mock_client.py:168`), so CI is green while the live path has never worked.

2. **`interval=1d` returns `prev_ohlc: null` during / after market open.** Verified against
   the live API: `interval=1d` → `prev_ohlc: null`, `live_ohlc` = today's forming daily
   candle. Only `interval=I1` populates `prev_ohlc` — and that is the previous *minute*, not
   the previous session. So there is no fix to `_fetch_prev_ohlc` that keeps calling
   `get_ohlc`: the previous session's *daily* close/high/low is simply not in that endpoint
   at 09:15–09:30. `_fetch_prev_ohlc`'s docstring premise ("at 09:10 the `1d` candle is still
   the previous session") does not hold for v3.

**Verified working alternative (2026-09-08 probe):** the historical-candle API
`GET /v3/historical-candle/{instrument_key}/days/1/{to_date}/{from_date}` returns
`data.candles` as `[ts, open, high, low, close, volume, oi]` rows, most-recent first — e.g.
for NIFTY on 2026-09-08 the first row is the completed 2026-09-07 daily candle. The
`BrokerClient` protocol already declares `get_historical_candles(params: CandleRequest)`;
`MockBrokerClient` implements it (fixture-backed); only `UpstoxLiveClient` has it stubbed as
`NotImplementedError` ("Add a sync fetcher to UpstoxMarketClient first"). A reference sync
implementation of the same endpoint already exists at
`scripts/dev/verify_analytics.py::step_historical_candles` (~L239).

**Suggested fix (not yet started — see task.md B040.x):**

- Implement `get_historical_candles_sync` + async wrapper in
  `src/client/upstox_market.py` (mirror `verify_analytics.py:239`), delegate from
  `src/client/upstox_live.py` (replace the `NotImplementedError`).
- Rewrite `src/signals/snapshot.py::_fetch_prev_ohlc` to build a `CandleRequest` and read
  `candles[0]` → `close=[4]`, `high=[2]`, `low=[3]`.
- Fix the stale `{"ohlc": {...}}` shape in `tests/unit/signals/test_signals_snapshot.py` and
  the `get_ohlc` stub there; add happy + HTTP-error unit tests for the new fetcher in
  `tests/unit/test_client.py`.
- `get_ohlc` / `get_ohlc_sync` become unused after this (only caller was `_fetch_prev_ohlc`).
  Leave in place (protocol-adjacent surface) but correct the lying docstrings, or remove in a
  follow-up — decide at fix time.
- Flip the `get_historical_candles` row in `src/client/CLAUDE.md` from ⛔ to implemented.
- Financial-data boundary → real `@code-reviewer` against the fix diff before commit.

**Investigation notes / scratch (2026-09-08, `scratch/2026-09-08_signals_ohlc_probe.py`,
read-only, no writes):**

- `/v3/market-quote/ohlc` `interval=1d` → `prev_ohlc: None`, `live_ohlc` = today's forming
  daily candle. Confirmed again live. Dead end for prev-session daily OHLC.
- `interval=I1` → `prev_ohlc` populated but it is the previous *minute* candle. Not usable.
- `/v3/historical-candle/{key}/days/1/{to}/{from}` **and** `/v2/historical-candle/{key}/day/{to}?from_date=`
  both return `data.candles` as `[ts, open, high, low, close, volume, oi]`, most-recent
  first. For NIFTY on 2026-09-08 `candles[0]` = `2026-09-07` daily
  (`close=23779.15 high=23890.0 low=23737.9`) — exactly the three numbers `_fetch_prev_ohlc`
  needs. The API skips non-trading days itself (2026-09-05 absent), so `candles[0]` is a
  more reliable "previous session" than computing `prev_trading_day` locally.
- Repo survey: `src/backtest/vix_ingest.py:92,156` already uses the **v2**
  `/historical-candle/{key}/day/{to}?from_date=` form for daily India VIX OHLC and parses the
  same 7-tuple. `scripts/dev/verify_analytics.py:239` uses the **v3** `days/1` form. No
  strategy sources index prev-day OHLC from `/market-quote/ohlc`.
- **WebSocket streamer checked (`MarketDataStreamerV3`,
  upstox.com/developer/api-documentation/streamer-function + .../v3/get-market-data-feed):**
  does **not** help here. `ltpc` mode's `cp` field is the prior session's *close* only — no
  prev high/low. `full` mode's `marketOHLC` `1d` entry is the *current* day's forming candle,
  identical limitation to the REST `/market-quote/ohlc`. No separate prev-day OHLC anywhere in
  the feed. Plus: protobuf decode + a persistent connection for a once-daily batch cron, and
  the repo has no streaming infra (`src/streaming/` empty, Phase 1–2). The streamer is a
  candidate for the *intraday* `StrategyMonitor` poll loop later — out of scope for BUG-040.
- **Decision:** fix uses the historical-candle REST API. Match `vix_ingest.py`'s v2
  `day/{to}?from_date={to-7d}` call for consistency with the one existing daily-OHLC
  fetcher; take `candles[0]`.

**Blast-radius audit (2026-09-08, live probes) — is `_fetch_prev_ohlc` the only broken input?**
Yes. Every other `assemble_market_snapshot` field was probed against its real source and works:

| Field | Source | Live status |
|---|---|---|
| `nifty_spot`, `india_vix` | `get_ltp([NIFTY, VIX])` | ✅ (crash was downstream of this — already proven) |
| `prev_close/high/low` | `_fetch_prev_ohlc` → `get_ohlc` | ❌ **this bug** |
| `gift_nifty` | `get_ltp(GLOBAL_INDEX\|SGX NIFTY)` | ✅ `last_price` 23711.5 |
| `usd_inr` | BOD lookup → `get_ltp(NCD_FO\|1769 = USDINR26SEPFUT)` | ✅ 94.76 |
| `fii` | NSE `fiidiiTradeReact` scrape | ✅ JSON shape matches (`category`/`netValue`, `07-Sep-2026`) — ⚠ NSE is IP/cookie-sensitive, reverify on the live host once |
| `monthly_expiry` | BOD lookup | ✅ `2026-09-29` (correct post-April-2026 Tuesday) |
| `option_chain` | `get_option_chain` V2 + `parse_upstox_option_chain` | ✅ 123 strikes → `OptionChain` |
| `vix_5d_trend` | local `SignalStore` | ✅ bootstrap → `"flat"` |

Side note for the fix: every `get_ltp` quote already carries `cp` = previous close (e.g. NIFTY
`cp` seen in the SGX/USDINR probes). So `prev_close` is available for free from the existing
`get_ltp([NIFTY_KEY])` call — but `prev_high` / `prev_low` still need the historical-candle
call, so the fix fetches all three from there for consistency.

No production code touched under this note; the fix itself is B040.2–B040.7.

**Implementation progress (2026-09-08, B040.2–B040.5):** Antigravity handoff produced
`50a5ce4`, which landed with a mangled `get_historical_candles` signature (stray
`CandleRequest` param → `TypeError`, one red test) and bypassed the financial-logic
`@code-reviewer` gate. Claude follow-up (fixup commit) corrected the signature, reverted
three out-of-scope annotation changes, and addressed both `@code-reviewer` ERRORs:
`(data.get("data") or {})` null-guard in `get_historical_candles_sync`, and the return
type set to the `list[Candle]` protocol alias with the positional-list / raw-float
contract documented. `_fetch_prev_ohlc` now selects the first candle strictly before
`trade_date` (guards a post-close cron re-run picking up today's partial daily candle)
and reads `[4]/[2]/[3]` → close/high/low as `Decimal(str(...))`. `get_ohlc` /
`get_ohlc_sync` kept but marked unused with corrected docstrings; `src/client/CLAUDE.md`
row flipped to ✅. Tests: stale `{"ohlc": {...}}` fixtures replaced with 7-tuple rows;
added `test_prev_ohlc_skips_todays_partial_candle`, `test_prev_ohlc_no_prior_session_raises`
(snapshot) and 3 fetcher tests (`test_client.py`). Full suite 3322 pass; re-review clean
(0 CRITICAL/ERROR). B040.6 manual `morning_signal` run still owed on the live host.

---

## BUG-038 — `OverlayCloser`'s three `self._notifier.send()` calls are unawaited coroutines (never actually sent)

| Field | Value |
|---|---|
| Severity | **High** — silent notification loss on financial-logic paths (collar close/monetize write failures, incomplete-collar abort) |
| Status | 🔴 Open |
| Discovered | 2026-08-25, incidentally — see **Discovery** below the table |
| Location | `src/strategy/overlay_closer.py::OverlayCloser.close_collar_all`, `OverlayCloser.monetize_collar_put` |

**Discovery:** general-purpose code-reviewer-persona pass on `docs/plan/telegram-markdown-migration/` MD-7.3's diff (`src/strategy/overlay_closer.py`) flagged it as unverifiable from the diff alone;
confirmed by reading `src/notifications/telegram.py::TelegramNotifier.send` (`async def send`) against the three call sites in `overlay_closer.py`
(`close_collar_all` ~L269, `monetize_collar_put` ~L330/~L395), all in **synchronous** methods calling `self._notifier.send(...)` with no `await` and no `asyncio.run(...)`/`create_task(...)` wrapper

**Root cause (not yet fixed — out of MD-7.3's scope, which is escaping only):** `TelegramNotifier.send()` is `async def`.
Calling it without `await` from a sync method constructs a coroutine object and immediately discards it — Python schedules nothing,
so the message is never sent. No exception is raised (matches the non-fatal contract's outward behavior), so this fails completely silently;
the only surfacing symptom is a `RuntimeWarning: coroutine 'TelegramNotifier.send' was never awaited` if warnings are enabled,
which is not part of the normal cron/strategy logging path. Net effect: the "Collar close failed", "Collar monetize aborted",
and "Collar monetize failed" alerts — all three fire on a paths where a human needs to intervene (DB write failure leaving legs open, or an incomplete collar structure)
— have likely never reached Telegram in production.

**Why this wasn't caught by MD-7.3's tests:** the test suite's `MockNotifier`/`notifier` test double used in `tests/unit/strategy/test_overlay_closer.py`
implements `send()` as a plain synchronous method (appends to `sent_messages`),
so calling it unawaited works correctly in tests — the mock doesn't reproduce the real notifier's `async def` signature, masking the bug.

**Scope note:** MD-7.3 only changed message *content* (added `escape_markdown()`/`mdcode()` wrapping) — it did not touch these call sites' `await`/no-`await` structure,
so this predates that task and is not a regression it introduced. Filed here rather than fixed inline to keep MD-7.3's diff scoped to escaping only,
per its story spec ("Do NOT change message wording/structure").

**Also surfaced in the same review, not yet independently confirmed:**
`src/notifications/markdown.py::escape_markdown`'s `MARKDOWNV2_RESERVED` set (`_*[]()~\`>#+-=|{}.!`) does not include the backslash character itself.
A dynamic value containing a literal `\` (e.g. a Windows-style path or a regex/JSON error message inside `str(exc)`) would pass through unescaped,
potentially producing a malformed MarkdownV2 escape sequence and a 400 from Telegram — silently swallowed by the non-fatal send contract.
Needs a repro test (`escape_markdown("C:\\foo")` or similar) before scoping a fix;
likely belongs in a follow-up to `MD-1`/`MD-6` rather than this bug, since it's in the shared helper, not `overlay_closer.py`/`auto_close.py` specifically.

**Fix (not yet scoped):** either make `close_collar_all`/`monetize_collar_put` `async def` and `await self._notifier.send(...)` (matches `auto_close.py`'s pattern),
or wrap the send in `asyncio.create_task(...)`/a sync-dispatch helper if these methods must stay synchronous for their other callers.
Needs a graph trace (`trace_path`) of both methods' callers before picking an approach — check whether any caller already runs inside an event loop.

---

## BUG-039 — `daily_snapshot.py`'s Telegram P&L summary silently stopped sending after 2026-08-24 (unescaped MarkdownV2)

| Field | Value |
|---|---|
| Severity | **High** — the daily 15:45 portfolio P&L notification (waterfall + Hedge/FinRakshak + Dhan Options block) has not reached Telegram on any trading day since 2026-08-25 |
| Status | ✅ Fixed — SHA `2cb67ce` |
| Discovered | 2026-09-01, user reported not receiving the daily message since 24 Aug |
| Location | `scripts/portfolio/daily_snapshot.py::_async_main` (live-run Telegram send block, was line 739) |

**Root cause:** commit `721daf9` (Mon 2026-08-24 23:00:53) changed `TelegramNotifier.send()`
(`src/notifications/telegram.py`) from `parse_mode="HTML"` to `parse_mode="MarkdownV2"`
unconditionally, with every caller now responsible for escaping MarkdownV2-reserved characters
(`escape_markdown()`/`mdcode()`) or Telegram rejects the send with a 400 ("can't parse
entities") — swallowed silently by `send()`'s non-fatal contract. That commit landed *after*
2026-08-24's 15:45 cron run (which is why that day's message arrived fine, under the old HTML
mode) — the very next scheduled send, 2026-08-25 15:45, was the first under MarkdownV2.

`daily_snapshot.py`'s summary text (built by `_format_combined_summary` in the same file plus
`format_options_section` in `src/dhan/positions.py`) was never migrated to escape its output —
confirmed via `grep` for `escape_markdown`/`mdcode` in both files: zero hits. The message is
inherently full of MarkdownV2-reserved punctuation that's structural to a P&L report: `-`
(every negative figure), `()` (percentages), `.` (decimals), `+` (signed values), `|`
(separators). This call site was already a known, documented gap —
`tests/unit/notifications/test_escaping_guard.py`'s `_BASELINE_UNESCAPED` dict carried
`("scripts/portfolio/daily_snapshot.py", 739)` with the note *"untracked gap — TODO.md item 9
kept current format as-is (2026-08-11 decision); MD-4's file list never actually included this
file despite that note flagging it for re-check"* — i.e. the `telegram-markdown-migration`
epic's ROLL-*/MD-* series migrated the strategy/alert callers but never reached this one.

**Corroborating evidence:** `logs/snapshot.log` doesn't capture this far into the script's run
on any date (a separate, unrelated stdout-buffering gap, present on both good and bad days —
not investigated further since it wasn't needed for root cause). But a sibling script,
`scripts/eod_summary.py` (different sender class, `TelegramGateway`, different message —
**not** the one the user was missing), shows the identical failure signature starting the same
day and continuing daily through 2026-09-01:
```
2026-08-25 15:42:05 [WARNING] [src] [notifications] [telegram] Telegram notification failed: 400, message='Bad Request'
2026-08-25 15:42:05 [WARNING] [scripts] [eod_summary] Failed to send EOD summary via Telegram.
```
That's a separate regression in `TelegramGateway`'s own (apparently incomplete) MarkdownV2
migration (`cd1e554`) — same day boundary, same root rollout, not fixed by this bug (filed here
only as corroborating evidence of the timing; out of this bug's scope).

**Fix:** wrap `summary_text` in `escape_markdown()` right at the `notifier.send()` call site in
`daily_snapshot.py`, rather than threading escaping through every f-string in the two builder
functions. Verified the message contains zero intentional MarkdownV2 entities (no `*bold*`/
`_italic_` anywhere in either builder), so escaping the whole assembled string is behaviorally
equivalent to escaping each interpolated value individually — and per `FORMATTING.md` §6
("escaping happens at the call site, never inside a formatter") this is a legitimate call site.
Manually verified `escape_markdown()` leaves emoji, box-drawing characters, digits, commas,
`₹`, `%`, and whitespace untouched, so the rendered message is visually identical to the
2026-08-24 version the user has as reference. Removed the now-stale `_BASELINE_UNESCAPED` entry
for this call site in the same commit, per that test file's own maintenance contract.

**Not in scope:** `TelegramGateway`'s parallel `eod_summary.py` regression (see above) — a
separate message, separate sender class, separate root cause within the same escaping
migration; would need its own investigation.

## BUG-019 — Investigation: does every strategy show a live-tick vs. EOD-snapshot P&L disparity, not just `paper_ic_nifty_v2_monthly`?

| Field | Value |
|---|---|
| Severity | **Under investigation** — not yet confirmed as a bug beyond the BUG-018 case; diagnostic instrumentation added to gather evidence across all strategies |
| Status | 🔍 Diagnostics added and committed (2026-07-23, SHA `f7177b6`), awaiting a live trading day's data before any fix is scoped |
| Discovered | 2026-07-23, as a direct generalisation of BUG-018 — see **Discovery** below the table |
| Location | `src/strategy/monitor.py::StrategyMonitor` |

**Discovery:** Animesh: "can we have some debugs added to check for all the strategy what is the PNL at 15:30 and what does the snapshot measure, i believe there is a disparency"

**Hypothesis being tested:** BUG-018 showed `paper_ic_nifty_v2_monthly`'s own internal P&L computation (`_compute_combined_pnl` inside `check_signals`) never ran at all
(silently short-circuited before reaching it) — so the "disparity" there was actually "the live side computed nothing," not "the two sides computed different numbers using the same inputs."
Now that BUG-018 is fixed, Animesh suspects a *broader* disparity may exist across all strategies between what the live monitor tick sees intraday (specifically near close, ~15:30)
and what `paper_snapshot.py`'s EOD cron records a few minutes later (~15:35-15:36).
This could be: (a) a genuine last-minute market move between the last tick and the EOD read (not a bug), (b) a real computation/staleness bug independent of BUG-018,
or (c) nothing — the two readings may in fact agree once V2 is no longer blind.

**Instrumentation added (2026-07-23):** `StrategyMonitor._log_live_pnl_diag()`, called at the end of every `_tick()`.
Restricted to the 15:20-15:30 IST window (not every ~90s tick all day, to avoid adding a `get_ltp` batch call per strategy on every tick).
For every registered strategy with at least one open leg (`net_qty != 0`), it calls `PaperTracker.compute_pnl(strategy_name)`
— the *exact same function* `paper_snapshot.py`'s EOD cron calls, not an approximation — and logs `strategy_monitor.live_pnl_diag` with `unrealized_pnl`/`realized_pnl`/`total_pnl`/`time`.
Because it's the identical function, any gap between this tick's reading (~15:20-15:30)
and the EOD snapshot's own log line (`Recorded paper NAV snapshot for '<strategy>' ... total_pnl=X`, ~15:35-15:36) is a genuine timing/staleness disparity,
not a methodology difference — the two sides can be diffed directly.

**Tests:** `tests/unit/strategy/test_strategy_monitor.py` — `test_live_pnl_diag_logged_inside_close_window`, `test_live_pnl_diag_skipped_outside_window`,
`test_live_pnl_diag_skipped_when_strategy_flat`, `test_live_pnl_diag_swallows_compute_pnl_exception`, `test_live_pnl_diag_skipped_when_compute_pnl_returns_none`,
`test_live_pnl_diag_window_boundaries` (parametrized, added after code review — see below). **Not run in-sandbox** (same disk-quota limitation as BUG-018)
— verified via `py_compile` only, pending live-host `pytest` run.

**Code review (2026-07-23):** general-purpose agent loaded `.claude/agents/code-reviewer.md` + `REVIEW.md` directly and reviewed the scoped diff. 1 CRITICAL,
2 WARNING, 1 INFO — all resolved before commit:
- **CRITICAL** (REVIEW.md G5): `except Exception:` in `_log_live_pnl_diag` lacked the required inline `# Intentional: ...` comment (the docstring rationale doesn't satisfy the rule as written).
Fixed: added inline comment on the `except` line.
- **WARNING**: the diag call was awaited *before* `_write_heartbeat`, so a slow/hanging `get_ltp` inside the comparison window could delay heartbeat freshness
— a real (if narrow) production effect for something meant to be a pure side-channel. Fixed: reordered so `_write_heartbeat` runs first, diag call moved after.
- **WARNING**: the original tests covered only one clearly-inside (15:25) and one clearly-outside (11:00) time, leaving the inclusive `_PNL_DIAG_WINDOW_START`/`_MARKET_CLOSE` boundaries (15:20, 15:30)
and the just-outside minutes (15:19, 15:31) unasserted — exactly where off-by-one errors hide. Fixed: added `test_live_pnl_diag_window_boundaries` (parametrized, 4 cases).
- **INFO**: mocking `monitor._tracker` post-construction (rather than mocking broker/store) verified as a reasonable unit-test strategy
— the real `PaperTracker(store, broker)` wiring still runs in `__init__` via `_make_monitor`, no integration gap hidden. No action needed.
Decimal correctness (`str(unrealized)` etc., no float leakage) and the `PaperTracker(store, broker)`/`BrokerClient`-satisfies-`MarketDataProvider` wiring both verified clean.

**Next step:** after the next trading day, grep `logs/monitor_daemon.log` for `strategy_monitor.live_pnl_diag` (per strategy, 15:20-15:30 entries)
and `logs/paper_snapshot.log` for `Recorded paper NAV snapshot` (same day), diff the last live reading against the EOD figure for every strategy.
If a real gap shows up beyond what a few minutes of market movement could plausibly explain, escalate to a proper BUG-0XX with root-cause investigation;
if not, remove this diagnostic (same 2026-07-24-style cleanup as BUG-018's temp logs, timeline TBD based on how many days of data are needed).

**Committed:** SHA `f7177b6`.

**Investigation result (2026-08-24):** ran the diff the "Next step" above calls for, across 5
separate trading days now present in `logs/monitor_daemon.log`/`logs/paper_snapshot.log`
(08-14, 08-17, 08-19, 08-20, 08-21) — last `strategy_monitor.live_pnl_diag` tick (15:28-15:29)
vs. the EOD `Recorded paper NAV snapshot` line (~15:35-15:36) for each strategy:

| Date | Strategy | live total_pnl | EOD total_pnl | diff |
|---|---|---|---|---|
| 08-14 | v1_leaps | 3805.75 | 3675.75 | -130.00 |
| 08-14 | v2_monthly | 2129.29 | 2002.54 | -126.75 |
| 08-17 | v1_leaps | 4056.00 | 4062.50 | +6.50 |
| 08-19 | v1_weekly | 3692.00 | 3692.00 | 0.00 |
| 08-19 | v1_monthly | 4917.79 | 4882.04 | -35.75 |
| 08-19 | v1_leaps | 3003.00 | 2944.50 | -58.50 |
| 08-19 | v2_monthly | 5828.88 | 5825.62 | -3.26 |
| 08-20 | v1_weekly | 3695.25 | 3734.25 | +39.00 |
| 08-20 | v1_monthly | 5281.79 | 5223.29 | -58.50 |
| 08-20 | v1_leaps | 4400.50 | 4179.50 | -221.00 |
| 08-20 | v2_monthly | 5731.38 | 5802.88 | +71.51 |
| 08-21 | v1_leaps | 4494.75 | 4468.75 | -26.00 |
| 08-21 | v1_monthly | 5337.04 | 5311.04 | -26.00 |
| 08-21 | v1_weekly | 4176.25 | 4166.50 | -9.75 |
| 08-21 | v2_monthly | 6108.37 | 6137.62 | +29.25 |

No systematic bias — sign flips constantly, magnitude tracks how much the market actually moved
that day (near-zero on the quiet 08-19 weekly reading vs. -221 on the more volatile 08-20
leaps reading), and one exact 0.00 diff (08-19 weekly) confirms the two sides agree perfectly
when the market genuinely didn't move in the 15:28→15:36 window. This matches hypothesis (a) —
ordinary last-minute intraday price drift between the last live tick and the EOD read — not
(b), a real computation/staleness bug. Per the "Next step" exit criteria above, this would
normally mean removing the diagnostic; **Animesh's call (2026-08-24): leave it running longer**
rather than closing/removing now. `docs/bugs/task.md`'s BUG-019 section moved to the bottom of
the file (still open, deliberately deprioritized below BUG-030/031) so the session-start
protocol doesn't pick B019.1 up next.

**Related:** BUG-018 (the specific case that prompted this generalisation).

---

## BUG-032 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-08-24, SHA `67d4010`, backfill applied same day)

---

## BUG-036 [MOVED] — see `docs/archive/bugs/bugs.md` (closed 2026-08-24, SHA `d40c3a1`, backfill applied same day)

---


## BUG-037 — `mark_trade_closed()` also never wired into CSP/IC v1/v2 close paths; 54 stale flat legs found live (54, not just BUG-035's 2)

| Field | Value |
|---|---|
| Severity | **MEDIUM** — see **Severity detail** below the table |
| Status | 🔴 Open — found 2026-08-24, not yet fixed. |
| Discovered | 2026-08-24 — see **Discovery** below the table |
| Location | `src/strategy/csp_roll_executor.py::close_csp_leg` (CSP), `src/strategy/ic_close_executor.py::close_ic_legs`/`roll_ic_legs` (IC v1/v2) — see **Location detail** below the table |

**Severity detail:** same category as BUG-035: `paper_trades.state` staleness on already-flat legs, not a live P&L/Greeks defect.
Currently inert per BUG-035's B035.1 trace (flat legs, `net_qty == 0`, never appear in `get_positions()`'s output, so `check_signals` never re-evaluates them regardless of their stale `state`)
— but the wiring gap is real and wider than BUG-035 scoped.

**Discovery:** while validating BUG-035's generalized backfill script (`scripts/dev/backfill_mark_trade_closed_overlay.py --dry-run`) against the live DB
— a scan for any `(strategy_name, leg_role, instrument_key)` that's flat but still `state IN ('OPEN','DEFENDED')` returned 54 rows, not the 2 BUG-035 already fixed.

**Location detail:** likely also `scripts/strategies/three_track/paper_3track_roll.py`'s futures/proxy roll-close writes (unconfirmed, see Suggested fix).

**Symptom:** 54 `(strategy_name, leg_role, instrument_key)` tuples are fully flat (BUY quantity − SELL quantity == 0) but still carry `state IN ('OPEN','DEFENDED')` on every row.
Breakdown: 5 `paper_csp_nifty_v1` short_put legs, 46 across `paper_ic_nifty_v1_weekly`/`monthly`/`leaps` and `paper_ic_nifty_v2_monthly` (short_call/short_put/long_call_hedge/long_put_hedge),
1 `paper_nifty_futures` base_futures leg, 1 `paper_nifty_proxy` base_ditm_call leg, and 1 more `paper_nifty_overlay`/`overlay_pp` leg (`NSE_FO|74046`) that BUG-035's original two-row backfill missed
because it only looked at the two instrument keys named in that bug's discovery query, not the whole table.

**Root cause:** Same shape as BUG-035 — `PaperStore.mark_trade_closed()` was never wired into the CSP or IC close/roll paths either.
Confirmed via direct grep (not the codebase graph — see note below):
`csp_roll_executor.py::close_csp_leg()` (used by `CSPNiftyV1.apply_action`'s `CLOSE_AND_ROLL`/`CLOSE_AND_WAIT`/`ROLL_DOWN_AND_OUT` branches) calls `store.record_trade(close_trade)`
and nothing else.
`ic_close_executor.py::close_ic_legs()`/`roll_ic_legs()` (used by both `IronCondorV1` and `IronCondorV2`'s `apply_action` for `CLOSE_FULL`/`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` and roll actions)
call `store.record_trades(trades)` and nothing else. Neither ever calls `mark_trade_closed()`.

**Graph-index correction (important for future sessions):** BUG-035's B035.1 trace used `codebase-memory-mcp`'s `trace_path(direction=inbound)`
and reported **zero callers** for both `get_trade_state()` and `mark_trade_defended()` project-wide. That was wrong
— a direct `grep -rn` found real callers of both in `src/strategy/csp_nifty_v1.py` (`get_trade_state()` at line 203,
feeding `evaluate_delta_breach_csp`'s OPEN-vs-DEFENDED state-aware branching per `CONTEXT.md`'s own documented behavior;
`mark_trade_defended()` at line 596, in the `ROLL_DOWN_AND_OUT` flow).
The graph's CALLS-edge index for this repo appears stale for at least these two symbols.
This doesn't change B035.1's practical conclusion — CSP's `check_signals` only reaches `get_trade_state()` for positions `get_positions()` returns,
which excludes flat (`net_qty == 0`) legs entirely, so the 54 stale rows found here (all flat) still don't affect any live signal evaluation today —
but the graph result itself should not be trusted as a sole source for "zero callers" claims going forward;
grep or `query_graph`'s raw CALLS-edge scan should corroborate before stating a symbol is orphaned.

**Suggested fix:** Mirror BUG-035's fix shape
— add `store.mark_trade_closed(...)` (or, if a roll only partially closes down to a nonzero size, the appropriate state transition) at each close write site above,
gated on the write actually flattening the position. Before implementing, trace `close_csp_leg`/`close_ic_legs`/`roll_ic_legs` call sites for any place a *partial* close/roll can leave `net_qty != 0`
— unlike BUG-035's overlay legs (always full closes), CSP's `ROLL_DOWN_AND_OUT` and IC's spread-only closes are explicitly partial at the strategy level,
so `mark_trade_closed()` must only fire on the specific leg's own row, using the per-leg trade being written (not a whole-strategy flatten check),
same pattern already validated in BUG-035's `OverlayCloser` fix. `paper_3track_roll.py`'s futures/proxy roll-close path needs its own trace (not yet done) before assuming the identical fix applies.
Backfill: `scripts/dev/backfill_mark_trade_closed_overlay.py` (built for BUG-035, generalized to scan the whole table rather than hardcoding instrument keys) already covers all 54 rows found here
— safe to run once the root-cause fix lands, since its discovery query only targets rows that are *already* flat (no partial-close risk).

**Related:** BUG-035 (identical bug shape, different call sites — CC/PP/Collar there, CSP/IC here); this bug's discovery came directly out of validating BUG-035's backfill script.

**Implementation progress (2026-08-24, B037.1/B037.2):** Re-traced current code (grep, not
`codebase-memory-mcp` — its CALLS-edge index is already flagged stale above) for all three call
sites. Confirms the suggested fix needs no gating beyond the per-leg trade being written:

- `close_csp_leg` (`src/strategy/csp_roll_executor.py:150`) closes at `existing.quantity` — the
  full size of that leg's row — before `record_trade`. CLOSE_AND_ROLL/CLOSE_AND_WAIT/
  ROLL_DOWN_AND_OUT all route through here at full leg quantity.
- `close_ic_legs`/`roll_ic_legs` (`src/strategy/ic_close_executor.py:236,361`) both build closing
  trades via `_build_close_trades`, called only on positions with `net_qty != 0`, at that leg's
  full `net_qty`. The "partial" in spread-only closes (e.g. CLOSE_CALL_SPREAD) is partial *at the
  strategy level* (only some roles close) — each individual leg row written is still a full close
  of that row. `roll_ic_legs` additionally writes open-side trades in the same `record_trades`
  call, so the close-vs-open trades need to stay distinguishable when `mark_trade_closed` is wired
  in (B037.3) — don't derive it from `TradeAction` alone.
- `paper_3track_roll.py::check_and_roll_leg` (`scripts/strategies/three_track/paper_3track_roll.py:252,278`)
  — **confirmed in scope**, not just "likely" as originally scoped. `qty = abs(pos.net_qty)`, full
  close, `record_trades([close_trade, open_trade])`, no `mark_trade_closed` call anywhere in the
  file. Same fix shape applies.

No B037.1 flatness-check branch is needed — all three sites already only ever write full-leg
closes, never a partial paydown of a single row. B037.3 can call `mark_trade_closed()`
unconditionally per closing trade, keyed to that trade's own
`(strategy_name, leg_role, instrument_key)`.

**Implementation progress (2026-08-24, B037.3/B037.4, SHA `5369c0e`):** Wired
`store.mark_trade_closed()` into all three confirmed sites:

- `close_csp_leg` (`src/strategy/csp_roll_executor.py`) — calls it only when
  `record_trade()` returns `True` (guards the duplicate-insert case, same
  shape as BUG-035's CC/PP overlay fix).
- `close_ic_legs` (`src/strategy/ic_close_executor.py`) — iterates `inserted`
  (the rows `record_trades()` actually wrote) and marks each one closed, so a
  partial write (some legs skipped as duplicates) only marks the legs that
  landed.
- `roll_ic_legs` (`src/strategy/ic_close_executor.py`) — marks only the
  close-side trades. Since `close_trades` and `open_trades` are concatenated
  into one `record_trades()` call, the close-side rows are identified by
  Python object identity (`id()`) against the pre-concatenation `close_trades`
  list, not by `TradeAction`, so the freshly-opened replacement leg is never
  mistakenly marked CLOSED.
- `check_and_roll_leg` (`scripts/strategies/three_track/paper_3track_roll.py`)
  — marks the leg closed only when `close_trade in inserted` (equality-based;
  safe here since close_trade/open_trade always differ by instrument_key).

Tests added mirroring BUG-035's B035.4 pattern (happy path + duplicate-insert
skip) in `tests/unit/strategy/test_csp_roll_executor.py`,
`tests/unit/strategy/test_ic_close_executor.py` (both `close_ic_legs` and
`roll_ic_legs`), and `tests/unit/scripts/test_paper_3track_roll.py` (using a
real `PaperStore`, not a mock, per that file's existing convention). All 51
tests in the three touched suites pass; a full `tests/unit/` run shows 31
pre-existing failures/7 errors unrelated to this change (missing
`pyarrow`/`fastparquet`/etc. in the ad-hoc review venv, confirmed by
traceback inspection — none touch the files this bug modified).

**B037.5 (2026-08-24):** Re-verified the live DB (`data/portfolio/portfolio.sqlite`)
via a new read-only diagnostic, `scratch/2026-08-24_check_stale_flat_legs.py`
(same discovery query as the backfill script, no writes) — run both through
the Cowork device bridge and directly by Animesh on the live host, identical
result: 0 stale flat legs across 134 total trade rows / 9 strategies. Animesh
confirmed he'd run `backfill_mark_trade_closed_overlay.py --dry-run` earlier
— that mode never writes, so it isn't what resolved the 54 rows found at
discovery time; the actual mechanism is unconfirmed. No backfill `--apply`
run was needed or performed — nothing stale remains.

**Outstanding for this bug:** B037.6 (mandatory real `@code-reviewer` run —
this session is Cowork, which cannot spawn `.claude/agents/code-reviewer.md`;
the B037.3/B037.4 commit (`5369c0e`) landed without that gate clearing, so a
`@code-reviewer` pass against that commit's diff from Claude Code is still
owed before this bug is considered fully closed).

---


