# Bug Registry

> One entry per confirmed defect. Do not log speculative issues here — confirm root cause
> first (graph trace / repro), then log. Suspicions belong in `TODOS.md` until confirmed.
> Status values: `🔴 Open` → `🟡 Fix in progress` → `✅ Fixed` (link commit SHA) → `⚪ Won't fix` (with reason).
>
> **Scope:** confirmed defects in live/shipped code (paper trading, cron scripts, live
> gates) — not unimplemented spec items, those are `docs/plan/` story tasks.
>
> **Relationship to root `BUGS.md`:** a bug registry already existed at the repo root
> (`BUGS.md`, single open entry `BUG-001` — `daily_snapshot.py` backfill gap, unrelated,
> low severity). This folder is the canonical home for *new* entries going forward; root
> `BUGS.md` is not migrated, it stays until `BUG-001` is fixed and deleted per its own
> convention. ID numbering is one shared sequence across both files — this registry
> starts at `BUG-002`.
>
> **Priority note:** `BUG-010` is pinned first in reading order (out of ID sequence) because
> it's marked highest priority to pick up next — fixing it makes every other entry in this
> registry faster to triage going forward. IDs are a discovery-order log, not a priority
> queue; this entry's position is the priority signal.

---

## BUG-010 — Six incompatible log output formats coexist in `logs/`, no enforced logging entrypoint

| Field | Value |
|---|---|
| Severity | **HIGH** — not a financial-logic defect, but actively degrades debuggability project-wide; directly slowed down triage of `BUG-009` (had to eyeball-parse mixed formats instead of grepping a single structured shape). Bumped from MEDIUM to HIGH and moved to the front of this registry — pick up first. |
| Status | ✅ Fixed — SHA range 5fa5e33..5d5c8ef (see `docs/bugs/task.md` B010.2–B010.9 for per-item SHAs) |
| Discovered | 2026-07-03, surveying every file in `logs/` after noticing `logs/intraday.log` mixed formats |
| Location | Project-wide — no single file, see breakdown below |

**Symptom:** every log file in `logs/` was sampled (`head`/`tail`, 19 files). At least six distinct line formats are in circulation, often interleaved within the same file:

1. **Structlog pipeline (correct, the intended standard)** — `src/utils/logging.py::setup_logging()` wired correctly. Format: `YYYY-MM-DD HH:MM:SS [LEVEL] [pkg] [sub] [module] event key=value`. Seen in `chain_intraday.log`, `chain_snapshot.log`, `eod_summary.log`, `monitor_daemon.log`, `morning_nav.log`, `pre_market_brief.log`, most of `intraday.log`/`paper_snapshot.log`/`vix_refresh.log`. This is the good case — every other format below is a deviation from it.
2. **Bare stdlib `logging.getLogger(__name__)`, bypassing structlog entirely** — `src/client/upstox_market.py:32`, three call sites (~131/165/205), `%s`-style. Because `setup_logging()` sets the stdlib root handler to `format="%(message)s"`, these render as bare `upstox.api_call endpoint=... status_code=... latency_ms=...` with no timestamp, no level, no module tag. Appears inside `chain_intraday.log`, `chain_snapshot.log`, `intraday.log`, `paper_snapshot.log`, `pre_market_brief.log` — scattered wherever `upstox_market.py` is on the call path.
3. **Raw `print(f"ERROR: ...")` / `print(f"INFO: ...")` with no timestamp** — `scripts/strategies/ic/ic_entry_gates.py`, `paper_ic_entry.py`, `paper_ic_entry_v2.py`. Produces `ERROR: post_expiry_gate: ...`, `INFO: selected expiry = ...` with a hand-typed prefix instead of a real level field. Fills `ic_leaps.log`, `ic_monthly.log`, `ic_v2_monthly.log`, `ic_weekly.log`, `ic_yearly.log` almost entirely.
4. **`structlog.get_logger(...)` called without `setup_logging()` ever being invoked** — all five files under `scripts/strategies/ic/` construct a module-level `logger = structlog.get_logger(...)` but none call `setup_logging()`, so structlog falls back to its own unconfigured default renderer: `2026-07-03 10:54:36 [warning  ]  gate.ivr_violation_logged  gate=0.25 ivr=0.149...` — lowercase padded level, no `[module]` bracket, different timestamp/spacing than format 1. Mixed into `ic_monthly.log`, `ic_v2_monthly.log`, `ic_snapshot.log` alongside format 3.
5. **Hand-built human-readable report strings (emoji, tables, no structure at all)** — `paper_ic_snapshot.py` (`📋 IC EOD Audit — ...`), `paper_ic_monthly_comparison.py` (`📊 IC Monthly Comparison — ...`), and a Rich-style `───` table block at the tail of `paper_snapshot.log`. These are Telegram-notification bodies also being dumped straight into the log file as-is — not a log line, a rendered report.
6. **Bespoke bracket-timestamp format, distinct from format 1** — `scripts/portfolio/daily_snapshot.py` writes `[2026-06-15 15:45:01] Daily snapshot for 2026-06-15` followed by indented plain-text detail lines (`  run_id=...`), which is neither the structlog pipeline nor a `print(f"LEVEL: ...")` — a third, separate hand-rolled convention. Fills `logs/snapshot.log`.

One additional file, `logs/apiconnect.log`, is the Nuvama APIConnect SDK's own internal logger output (`2026-06-15 06:14:48,167 [INFO] APIConnect.APIConnect: ...`, comma-millisecond timestamps) — this is third-party and out of project control; it should be documented as an accepted exception, not "fixed."

**Root cause:** `setup_logging()` exists and is well-built (`src/utils/logging.py`), but nothing in the codebase enforces that every entrypoint script calls it before logging, and nothing prevents `print()` or raw stdlib `logging.getLogger()` from being used instead. Three independent failure modes compound: (a) scripts that never call `setup_logging()` at all, (b) code that reaches for stdlib `logging` directly instead of `structlog.stdlib.get_logger`, and (c) human-facing report/notification text being treated as if it were a log line. `REVIEW.md` G7 mandates `%`-style formatting for "logger calls," which is a stdlib-logging convention — it doesn't address structlog's keyword-argument idiom at all, so the review checklist itself has no rule that would have caught formats 2–6.

**Impact:** concretely slowed down the `BUG-009` investigation — errors and warnings are not uniformly greppable (`grep ERROR` misses format-4's `[warning  ]` lines and format-1's `[ERROR]` lines have a different bracket shape; format 3's `"ERROR:"` prefix has no real level field to filter on). Any future alerting/monitoring built on top of these logs (e.g. "page me on any ERROR") cannot rely on a single parse rule.

**Suggested fix:** see `LOGGING.md` (project root — new file, added alongside this bug entry) for the standard going forward. Concretely: (1) every entrypoint script (anything with `if __name__ == "__main__"`) must call `setup_logging()` before any other logging happens — add this as a `code-reviewer` checklist item; (2) migrate `src/client/upstox_market.py` to `structlog.stdlib.get_logger(__name__)` (3 call sites); (3) migrate the five `scripts/strategies/ic/*.py` files' raw `print()` calls to `logger.info/warning/error(...)` with keyword args, and add the missing `setup_logging()` call; (4) migrate `scripts/portfolio/daily_snapshot.py` off its bespoke `[timestamp] message` format onto the shared pipeline; (5) keep emoji/table report strings, but log them as a single structured event (e.g. `logger.info("report.sent", channel="telegram", strategy=..., body=report_text)`) rather than a bare `print()` with no level/timestamp; (6) document `apiconnect.log` as an intentional third-party exception rather than attempting to reformat SDK-internal logging.

**Related:** discovered while triaging `BUG-009`; `upstox_market.py`'s stdlib-logging bypass was separately flagged before this survey formalized it as one item in the larger project-wide pattern.

**Closing summary (2026-07-03):** all six format deviations addressed per the suggested-fix list (B010.2–B010.6); `apiconnect.log` documented as an accepted third-party exception (B010.6, verified already satisfied by the original `LOGGING.md` commit); happy-path + degrade-gracefully tests added (B010.7); final review pass (B010.8) against the cumulative diff (`git diff 96c80e7..5d5c8ef`) found no CRITICAL/ERROR — see `docs/bugs/task.md` B010.8 for the checklist covered (G2/G7/G8, unused imports, no information loss on removed `print()` calls). Follow-up recommended, not yet actioned: add "every entrypoint script calls `setup_logging()`" as a permanent `code-reviewer` checklist item (per the original suggested-fix item 1) so this doesn't regress.

---

## BUG-011 — `test_build_notifier_returns_none_when_token_missing` fails on live host (suspected cross-test env leakage)

| Field | Value |
|---|---|
| Severity | **LOW** — test-suite reliability only, no production code path affected; `build_notifier()` itself is not known-broken |
| Status | 🔴 Open |
| Discovered | 2026-07-03, live-host `pytest` run surfaced by Animesh after BUG-010 B010.4 session |
| Location | `tests/unit/test_notifications.py::test_build_notifier_returns_none_when_token_missing`; suspected root cause in `src/config.py::_DynamicSettings` or a test elsewhere that mutates `os.environ` outside `monkeypatch` |

**Symptom:** `assert <src.notifications.telegram.TelegramNotifier object at 0x111d06c60> is None` — `build_notifier()` returned a real notifier instead of `None` even though the test calls `monkeypatch.delenv("TELEGRAM_BOT_TOKEN")` / `monkeypatch.delenv("TELEGRAM_CHAT_ID")` immediately beforehand.

**Not yet root-caused** — this entry logs a confirmed repro (real pytest failure, output pasted by Animesh), not a confirmed root cause; investigation is the first checklist step. Not caused by the B010.4 diff — that session touched only `scripts/portfolio/daily_snapshot.py` and a new test file, never `src/notifications/`, `src/config.py`, or `tests/unit/test_notifications.py`.

**Leading hypothesis:** `build_notifier()` reads through `settings.telegram_bot_token`/`telegram_chat_id`, where `settings` is the `_DynamicSettings` singleton (`src/config.py`) that rebuilds `Settings` only when `hash(frozenset(os.environ.items()))` changes since the last access. If `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are real values already present in the live host's process environment (exported in the shell, not `.env`-sourced) — or some other test in the suite writes directly into `os.environ` rather than through `monkeypatch` (whose reversion `monkeypatch.delenv` in *this* test can't undo if it happened in a different test's un-reverted mutation) — this test only passes when run in isolation, and fails as part of the full suite or a shell session that already exports the tokens. Unconfirmed until reproduced.

**Suggested fix (pending investigation):** (a) confirm via `pytest tests/unit/test_notifications.py::test_build_notifier_returns_none_when_token_missing -q` run alone vs. full-suite run — isolates whether this is cross-test leakage vs. a `_DynamicSettings` caching bug; (b) `echo $TELEGRAM_BOT_TOKEN $TELEGRAM_CHAT_ID` in the host shell running pytest to rule out real OS-level env vars; (c) if cross-test leakage is confirmed, `grep -rn "os.environ\[" tests/` for any raw (non-`monkeypatch`) mutation and convert it to `monkeypatch.setenv`.

---

## BUG-002 — Option delta sign/magnitude corrupted by put-call misclassification

| Field | Value |
|---|---|
| Severity | **CRITICAL** — feeds the portfolio delta entry gate; wrong sign inverts risk reads |
| Status | ✅ Fixed (2026-07-02, SHA 62ed6ef) |
| Discovered | 2026-07-02, triaging `ic_weekly.log` entry rejection |
| Location | `src/risk/delta_tracker.py::_position_delta` (lines 140–175) |

**Fix summary (B002.3 + B002.4, SHA 96398b4 + 62ed6ef):** Sign classification now uses `PaperPosition.option_type` (resolved read-time by `PaperStore` via `InstrumentLookup`, not `instrument_key` substring matching). Magnitude: `aggregate_delta`/`_position_delta` accept an optional `position_deltas: dict[instrument_key, Decimal]` supplying the real chain-derived delta; falls back to the old `±net_qty/lot_size` approximation with a logged WARNING when unavailable — never silent. Module boundary decided by council 2026-07-02 (`docs/council/2026-07-02_paper-delta-source-architecture.md`): `src/risk/` stays pure/zero-I/O; the caller (`ic_entry_gates.py`/`paper_ic_entry.py`) owns chain resolution — **not yet wired** as of SHA 62ed6ef, so `aggregate_delta` callers today still omit `position_deltas` and get the (now correctly-signed) approximation. Wiring the caller-side chain resolution is follow-on work, not tracked under a B002.x line yet — add to `TODOS.md` if picked up.
`aggregate_delta` cross-strategy pooling question (see root cause section below) remains unresolved — flagged for Animesh, not addressed by this fix.

**Symptom:** `ic_weekly.log` — `ERROR: Portfolio delta check failed. Projected=6.901 lots (outside [-0.05, 0.25]). Stop.` A projected delta of 6.9 lots against a ±0.05..0.25 gate is not a marginal miss; something upstream is structurally wrong.

**Root cause:** `_position_delta` classifies a position as put/call by substring-matching `"PE"` / `"CE"` against `pos.instrument_key`:

```python
if "PE" in key:
    return -net_qty / lot_size_d
if "CE" in key or ("NSE_FO|" in key and "PE" not in key):
    return net_qty / lot_size_d
```

Real Upstox `instrument_key` values are pure numeric (`NSE_FO|63916`, confirmed against `REFERENCES.md` — every listed key is `NSE_FO|<digits>`). The literal substrings `"PE"`/`"CE"` never appear in a numeric key, so the put branch is dead code. Every option position — put or call, long or short — falls into the `else` branch and is priced as a naked future: `delta = net_qty / lot_size` (full ±1.0 delta per lot, sign taken straight from `net_qty`).

Concrete case: `paper_csp_nifty_v1` holds a short put, `net_qty=-65` (1 lot short). Correct delta contribution is a small **positive** value (~0.25–0.35 lots — short put is bullish). The code returns **-1.0 lot** — wrong sign, ~3–4x wrong magnitude.

Compounding factor (needs a decision, not just a fix): `aggregate_delta` in `scripts/strategies/ic/paper_ic_entry.py` (line 365) sums across **every** open paper strategy via `store.get_strategy_names()`, not just the calling strategy's own book. `paper_nifty_futures`, `paper_nifty_proxy`, and `paper_nifty_spot` (NiftyBees + FO legs) all feed the same aggregate as the IC's own risk. Whether that cross-strategy pooling is intentional (true portfolio-level delta) or a bug (double-counting parallel proxy/hedge books) is unresolved — flag for Animesh, do not assume during the fix.

**Underlying structural gap:** `PaperPosition` (`src/paper/models.py`) carries no `option_type` / `strike` / `asset_type` field — only `instrument_key`, `net_qty`, `avg_cost`, `avg_sell_price`. There is no reliable signal in the object to reconstruct put/call. The `legs` table (portfolio module, separate from `paper_trades`) *does* carry `asset_type`, `direction`, `strike` — that data exists elsewhere in the schema, `_position_delta` just isn't sourcing it.

**Suggested fix:** Either (a) extend `PaperPosition` with an `option_type: Literal["PE", "CE", "FUT", "EQ"] | None` field populated at trade-record time from the instrument lookup (`InstrumentLookup`), or (b) join against `legs.asset_type` / `legs.direction` when constructing `PaperPosition` in `PaperStore.get_position`. Also replace the crude `net_qty / lot_size` full-delta approximation with the actual option delta from the chain snapshot where available — a short 1-lot put is not equivalent to a short 1-lot future.

**Related:** IDs continue from root `BUGS.md` (`BUG-001` — unrelated, `daily_snapshot.py` backfill gap). See `docs/bugs/prompt.md` for how the two registries relate.

---

## BUG-003 — `_post_expiry_gate` blocks entry for the entire monthly cycle instead of only the settlement day

| Field | Value |
|---|---|
| Severity | **HIGH** — blocks 100% of monthly IC entries except a ~1–3 day window per month |
| Status | ✅ Fixed (2026-07-02, SHA 2c6f771) |
| Discovered | 2026-07-02, triaging `ic_monthly.log` / `ic_v2_monthly.log` entry rejection |
| Location | `scripts/strategies/ic/ic_entry_gates.py::_post_expiry_gate` (lines ~68–95) |

**Fix summary (B003.2–B003.7, SHA 2c6f771):** Added `_most_recently_settled_expiry(today)` — returns the current calendar month's last Tuesday if it has already occurred, otherwise falls back to the previous month's last Tuesday (with Dec→Jan year-rollover handling). `_post_expiry_gate` now blocks only when `today <= that reference date` — i.e. same-day re-entry on the settlement date itself — and allows entry the very next day, instead of blocking the entire new cycle against its own future expiry. B003.4 investigation confirmed there was no separate, already-fixed `paper_ic_entry_v2.py` gate to port from — commit `23e8e93` (2026-06-28) had already moved the (still-buggy) calendar-based gate into the shared `ic_entry_gates.py`, which both V1 and V2 call; that commit fixed a different bug (comparing against a bad future-target expiry) but left the "wrong cycle" reference in place, which is what this fix addresses. `_last_tuesday_of_month` itself is untouched (B003.3 verified no impact on the SEBI Tuesday-expiry logic in `REFERENCES.md`). Tests: 3 new/rewritten cases per file — regression (mid-cycle pass), day-after-settlement pass, same-day-settlement block, Dec→Jan year rollover — in both `tests/unit/strategies/ic/test_ic_entry_gates.py` and `tests/unit/strategies/ic/test_paper_ic_entry_v2.py` (stale always-block assertions from the old bug were rewritten, not just supplemented). 67/67 tests pass in `tests/unit/strategies/ic/`. Reviewed via `general-purpose` agent substituting for `code-reviewer` (not exposed in this Cowork environment, same workaround as BUG-002) against `REVIEW.md` — no CRITICAL/ERROR findings.

**Symptom:** `ic_monthly.log` / `ic_v2_monthly.log` — `ERROR: post_expiry_gate: current month expiry 2026-07-28 has not yet passed (today=2026-07-01). Entry is only valid after settlement.` Today is 2026-07-01 — the June monthly cycle already settled 2026-06-30, a fresh July series just opened. This is exactly when entry should be allowed, not blocked.

**Root cause:**

```python
today = date.today()
expiry = _last_tuesday_of_month(today.year, today.month)
if today <= expiry:
    sys.exit(1)   # blocks entry
```

`_last_tuesday_of_month(today.year, today.month)` computes the expiry of the **current** calendar month — the same cycle the caller is trying to enter — and blocks until that expiry has already passed. That inverts the intended check: you enter a position *before* its own expiry, not after. As written, the monthly IC can only ever enter during the handful of days between this month's expiry and month-end rollover (here: 2026-07-29 to 2026-07-31), then immediately re-blocks for the entirety of the next month.

**Intended behavior** (per module docstring: "block entry before last-Tuesday settlement"): a same-day/next-day guard preventing re-entry on the same date the *previous* cycle is still settling — not a blackout of the entire new cycle.

**Suggested fix:** Reference the *previous* month's `_last_tuesday_of_month` (the cycle that just settled) instead of the current month's, and only block same-day re-entry immediately following that settlement date — not the current cycle's own (future) expiry.

**Related:** shared helper `_last_tuesday_of_month` also backs `REFERENCES.md`'s documented Tuesday-expiry logic (SEBI change, April 2026) — verify the fix doesn't disturb that call site.

---

## BUG-004 — `resolve_ivr` gates on a stale 252-day window with no recency check

| Field | Value |
|---|---|
| Severity | **MEDIUM** — currently benign (VIX mid-range, unlikely to have crossed the 1-year band in the missing days) but silently wrong under a vol spike/crush |
| Status | ✅ Fixed (2026-07-02, SHA 143335e) |
| Discovered | 2026-07-02, verifying IVR=0.24 reading behind `ic_leaps.log` / `ic_yearly.log` rejections |
| Location | `src/backtest/ivr.py::compute_ivr`; `scripts/strategies/ic/ic_entry_gates.py::resolve_ivr` |

**Symptom:** none directly logged — found while independently verifying the IVR=0.24 gate rejection was correct. `resolve_ivr` combines a **live** `vix_today` (from `IntradayMarketStore.get_latest_vix_today()` / `fetch_vix_latest()`) with a **historical** 252-day window loaded from `data/historical/ohlc/india_vix/*.parquet` for the min/max normalization. Pulled the parquet series directly: 2,476 daily rows, 2016-06-27 to **2026-06-25**, zero gaps >5 calendar days anywhere in the decade (history itself is complete and correctly ingested). But the file's `mtime` is 2026-06-26 21:16 and hasn't been touched since — as of today (2026-07-02) the window is missing 5 trading days (Jun 26, 29, 30, Jul 1, Jul 2). `TODOS.md` documents a weekly refresh cron (`refresh_vix.py`, Monday 08:00 IST, 30-day lookback) that should have caught at least through Jun 26 by the Jun 29 run — it visibly didn't.

**Root cause:** `compute_ivr` only validates window *size* (`len(vix_series) < 252 → None`), never window *recency*. A stale-but-full-count series passes silently. The numerator (`vix_today`) is always fresh (live fetch), but the denominator (`window_min`/`window_max`) can be arbitrarily stale as long as the row count clears 252 — there is no check that `window.index.max()` is within N trading days of `today`.

**Why today's 0.24 is very likely still correct despite this:** recomputed the window directly — min **9.15**, max **27.89** over 2025-06-19 to 2026-06-25 (18.74-point range). For the missing 5 days to have changed the percentile, VIX would have had to print a new 1-year high or low, which is a big ask from a level sitting around 13. So this bug did not cause the `ic_leaps`/`ic_yearly` rejections — but it's a latent correctness gap: if VIX had spiked or crushed in the missing days, `resolve_ivr` would gate on a wrong percentile with no error or warning surfaced.

**Suggested fix:** (a) add a recency check in `compute_ivr` or `resolve_ivr` — e.g. `if (today - window.index.max()).days > N: log warning / treat as stale`; (b) separately, verify why the Monday 2026-06-29 `refresh_vix.py` cron run didn't advance the file past 2026-06-25 — check cron logs / whether the cron is actually installed on the live host, not just documented in `TODOS.md`.

**Fix summary (B004.2–B004.5):** B004.2 investigation ruled out a missing/broken cron — `crontab -l` on the live host confirmed the entry is installed exactly as documented (`45 15 * * 1`). Root cause of the staleness was instead: Upstox's `from_date` query param on the historical-candle endpoint appears not to filter the response (`rows=2475`, essentially full decade history, returned on both the original Jun-29 cron run and a manual Jul-2 re-run) combined with an observed ~1-2 trading-day publish lag on VIX EOD candles — the Jun-29 fetch genuinely had 0 new rows available to write at that exact fetch time; the manual Jul-2 re-run picked up 3 rows (Jun 26/29/30) once published. The `from_date`-not-honored behavior is wasteful (full-history refetch weekly) but not itself the cause of staleness and is tracked as a separate follow-on, not part of this fix. B004.3 added `_is_vix_window_stale(series, today)` in `scripts/strategies/ic/ic_entry_gates.py` (kept out of `src/backtest/ivr.py::compute_ivr` deliberately — `compute_ivr`'s existing test suite uses plain RangeIndex series with no dates, and `resolve_ivr` is the only layer holding the date-indexed series). Threshold: 7 calendar days (Animesh-approved — tolerates one missed/late Monday cron run plus observed publish lag without false-positiving on routine gaps). When stale, `resolve_ivr` logs a WARNING and leaves `ivr = None`, reusing the existing `ivr is None` hard-block path rather than adding new blocking logic. B004.5: reviewed via `general-purpose` agent substituting for `code-reviewer` (not exposed in this environment) against `REVIEW.md` — 2 ERROR findings (import ordering, docstring line length) fixed; no CRITICAL logic defects.

**B004.6:** Committed by Animesh on the live host (SHA `143335e`) — this Cowork sandbox had no disk space / `.venv` to run the project's pre-commit hooks itself.

**B004.7 recheck (2026-07-02):** Recomputed the trailing-252-day window as-of each date in the stale period (06-26, 06-29, 06-30, 07-01, 07-02) against the now-caught-up VIX series. Window low/high (9.15 / 27.89) is identical across all five dates — none of the missing days set a new 1-year high or low, so IVR is invariant to the staleness here. Confirms the logged decisions during the stale window were correct: `ic_leaps`/`ic_yearly` rejections (IVR=0.24 < 0.25 gate) and `ic_weekly` pass (IVR=0.24 ≥ 0.15 gate) all stand — no entry was wrongly blocked or wrongly allowed. BUG-004 closed.

**Once fixed, recalculate last week's IVR-gated entries:** any IC entry/rejection decision made between 2026-06-26 and whenever the cron gap is closed was evaluated against this same stale window. After the fix lands (both the recency check and the actual cron/data catch-up), re-run the IVR gate for that period and confirm no entry was wrongly blocked or wrongly allowed — do not assume last week's readings were fine just because this week's happened to be.

**Related:** `BUG-003`'s post-expiry gate and this bug are both in the same "gate evaluated the wrong reference window" family — worth a shared regression-test pattern (assert gate references a *current* or *most-recently-completed* reference point, never a frozen one) once both are fixed.

---

## BUG-005 — B002.2 cross-strategy pooling exclusion was decided but never implemented

| Field | Value |
|---|---|
| Severity | **HIGH** — blocks legitimate IC weekly entries with a fabricated delta figure; portfolio-delta gate is otherwise correctly signed post-BUG-002 |
| Status | 🔴 Open |
| Discovered | 2026-07-02, dry-run of `paper_ic_entry.py --expiry-type weekly` |
| Location | `scripts/strategies/ic/paper_ic_entry.py` (line ~359-365); `scripts/strategies/ic/paper_ic_entry_v2.py` (line ~351-357) |

**Symptom:** Dry-run of V1 weekly entry: `ERROR: Portfolio delta check failed. Projected=-8.098 lots (outside [-0.05, 0.25]). Stop.` Debug trace shows the only IC-relevant position contributing is `paper_csp_nifty_v1`'s short put (`net_qty=-65`, ~+1 lot even under the crude approximation). Every other position dragging the aggregate to -8.098 belongs to `paper_nifty_futures`, `paper_nifty_proxy`, or `paper_nifty_spot` — overlay PP/collar/ditm-call legs from parallel proxy/hedge books, not the IC's own risk.

**Root cause:** BUG-002's root-cause investigation (B002 root cause section) explicitly flagged this pooling as an open scope question, and **B002.2 recorded a decision to resolve it**: *"scope `aggregate_delta` to IC-relevant positions only; exclude `paper_nifty_futures`/`paper_nifty_proxy`/`paper_nifty_spot` from the IC delta-neutral gate. Decided by Animesh 2026-07-02 (no code change this step)."* The "no code change this step" note implied implementation would land in a later B002.x task. It never did — B002.3 added `option_type` resolution, B002.4 added chain-delta sign/magnitude plus the fallback path, B002.5-7 were tests/review/commit for those two. None of them touch `store.get_strategy_names()` / the loop that builds `all_open_pos` in the two entry scripts. The decision was recorded in `bugs.md` and closed out as part of BUG-002 without the corresponding code ever being written — caught only because this dry run happened to exercise the weekly aggregate-delta path, which B002's own test suite (`tests/unit/risk/`) never did (those tests exercise `_position_delta`/`aggregate_delta` directly with hand-built position lists, not the caller-side strategy-name loop in the entry scripts).

```python
strategies_list = store.get_strategy_names()
all_open_pos = []
for strat in strategies_list:
    all_open_pos.extend([p for p in store.get_positions(strat) if p.net_qty != 0])
```

Both `paper_ic_entry.py` (line ~359) and `paper_ic_entry_v2.py` (line ~351) have the identical unfiltered loop.

**Suggested fix:** Exclude `STRATEGY_SPOT`/`STRATEGY_FUTURES`/`STRATEGY_PROXY` (`src/paper/constants.py`) from `strategies_list` before the loop, in both entry scripts. A shared helper in `ic_entry_gates.py` (even though the portfolio-delta gate itself isn't shared between V1/V2 per the module's documented divergence) avoids duplicating the exclusion set inline in two places.

**Related:** `BUG-002` (this is the un-implemented remainder of that bug's B002.2 decision, not a new independent defect).

---

## BUG-006 — Intraday chain snapshot writer only persists the yearly-expiry bucket, not actively-traded expiries

| Field | Value |
|---|---|
| Severity | **MEDIUM** — no functional impact on live gates, but destroys the ability to reconstruct/audit what a strategy actually saw at entry time |
| Status | ✅ Fixed (2026-07-03, SHA 7e0801c) |
| Discovered | 2026-07-03, trying to reconstruct the weekly IC's 10:29 AM strike-selection delta from historical data |
| Location | intraday chain snapshot pipeline (`scripts/pipeline/upstox_chain_intraday.py`) → `data/historical/option_chain/intraday/YYYY/MM/DD/upstox_HHMM.parquet` |

**Fix summary (B006.2–B006.6, SHA 7e0801c):** Root cause was not in the expiry-selection loop (`main()` already iterates all 3 configured expiries via `_PREFERENCE`/`get_expiry_candidates`) — it was in `ChainWriter.write_intraday_snapshot`/`write_eod_snapshot` (`src/backtest/chain_writer.py`): the output filename was keyed only by timestamp (`upstox_{HHMM}.parquet` / `upstox_{date}.parquet`), with no expiry/label component. Since all 3 expiries in a run share the same `snapshot_ts`, each write silently overwrote the previous one on the same path — `yearly` (last in `_PREFERENCE` order) always survived. Fix: added a `label` parameter to both writer methods, appended to the filename (`upstox_{HHMM}_{label}.parquet` / `upstox_{date}_{label}.parquet`); both `upstox_chain_intraday.py` and `upstox_chain_snapshot.py` now pass the per-expiry `label` through from their existing loop. `write_eod_snapshot` had the identical bug (same overwrite-per-date pattern) — fixed in the same change since both share the same root cause. Tests: new regression tests in `test_chain_writer.py` (distinct labels → distinct files, same label → still idempotent, for both writers) plus label-passthrough assertions in both script test files; 29/29 pass. Review: manual `REVIEW.md`-checklist substitute (no `code-reviewer` subagent in this environment) caught and fixed one G2 line-length violation in the new tests and one pre-existing ruff B007 unused-loop-variable finding in the touched file.

**Symptom:** Manually validated a weekly IC entry's live delta post-hoc (short_put 23500 PE showing `delta=0.0243`, well outside the config's `[0.06,0.14]` target band) and tried to check whether it was in-band at the actual 10:29 AM selection time using the persisted 5-min intraday snapshots. Every snapshot file for 2026-07-03 (`upstox_0900.parquet` through `upstox_1040.parquet`, including the 10:25/10:30 files bracketing the dry-run) contains **only** `expiry_date == 2027-06-29` (the yearly bucket) at sparse strikes (16500–31500, ~1500 pt spacing). The weekly 07-Jul-26 expiry — the one actually being traded — was never snapshotted.

**Root cause (not yet traced to exact line — needs graph/code confirmation before fix):** the intraday writer appears hardcoded or configured to snapshot a single expiry (consistent with its use for `gamma_daily_watch.py` / yearly gamma-buy monitoring) rather than the full set of expiries actively traded across strategies (weekly/monthly/leaps/yearly IC all read live chains but only yearly gets an intraday audit trail).

**Impact:** any post-hoc question of the form "was gate X's input actually valid at decision time, or did it decay before/after" cannot be answered for weekly/monthly/leaps IC entries — only for the yearly bucket. This already blocked a debugging session (this one) from confirming whether BUG-candidate delta drift was a selection-time defect or normal DTE-4 convexity after the fact.

**Suggested fix:** parameterize the intraday writer to snapshot every expiry bucket actually referenced by `CONFIGS`/`CONFIGS_V2` (weekly/monthly/leaps/yearly), not just the yearly gamma-watch expiry — or at minimum, snapshot whichever expiry each `paper_ic_entry*.py` cron is about to act on, keyed by run, so every entry decision has a reconstructable input snapshot.

**Related:** none yet — first entry in the "audit trail gap" family.

---

## BUG-007 — Portfolio-delta strike adjustment doesn't re-validate the shifted leg's own delta-target band, IVR, or structure economics

| Field | Value |
|---|---|
| Severity | **HIGH** — can silently accept a structure whose standalone risk/reward was never checked after portfolio-delta correction |
| Status | ⚪ Closed — moot (2026-07-03, SHA 66c4c71) |
| Discovered | 2026-07-03, tracing why weekly IC dry-run selected 24750 CE / 24950 CE for the call wing |
| Location | `scripts/strategies/ic/paper_ic_entry.py` lines ~437–530 (`paper_ic_entry_v2.py` lines ~417–467 has the same pattern) |

**Closed as moot (2026-07-03, no code change):** the `adj_call`/`adj_put` portfolio-delta strike-shift block this bug describes no longer exists in either entry script. It was removed by the same-day "IC entries judged in isolation" decision (`DECISIONS.md` 2026-07-03) — IC entries are now judged only on their own two short legs' delta, never adjusted against other strategies'/variants' open positions. Confirmed via `search_code` for `adj_call`/`adj_put`/"Portfolio delta gate adjusted" across the repo — zero matches. B007.2–B007.5 marked N/A in `task.md` per Animesh; no fix implemented since there is nothing left to fix.

**Symptom:** none directly logged as an error — found while explaining why the portfolio-delta gate printed `INFO: Portfolio delta gate adjusted short_call to 24750.0`. Traced the adjustment code path and confirmed: when `projected_total` (existing book delta + this IC's delta) falls outside `[-0.05, 0.25]`, the script shifts the offending short leg **one strike further OTM** and re-derives its wing hedge at `strike ± wing_width_points`. The only check applied to the shifted leg before accepting it is `_apply_liquidity_gate([adj_call])` (or `adj_put`) — there is no re-check that the new strike still satisfies `config.short_call_delta ± config.delta_range` (or the put equivalent), no re-check of DTE/IVR gates against the now-different structure, and no recomputation of max-profit/max-loss/POP/R:R for the adjusted four-leg structure before accepting it.

**Root cause:**

```python
if adj_call and _apply_liquidity_gate([adj_call]):
    new_ic_delta = Decimal(str(abs(short_put["delta"]))) - Decimal(str(abs(adj_call["delta"])))
    if Decimal("-0.05") <= (current_delta_lots + new_ic_delta) <= Decimal("0.25"):
        # Success — accepted with no further validation of adj_call itself
        short_call = adj_call
        ...
```

The adjustment loop optimizes for exactly one objective (portfolio delta back in band) and treats that as sufficient justification to accept the new strike. It does not re-run the same delta-target/IVR/DTE checks that gated the *original* strike selection — so a portfolio-delta-driven shift can land on a strike with a delta well outside the strategy's own designed band, or on a structure with materially worse R:R/POP than the one that was originally evaluated, and the script has no way to detect or flag that.

**Impact:** the dry-run this surfaced in produced a structure (23500PE/23300PE/24750CE/24950CE, DTE=4) that independent payoff analysis (Stockmock) showed as negative expected value against its own POP estimate (POP 92.2% vs 97.8% breakeven requirement). The delta-adjustment step is not the sole cause of that (DTE=4 and sub-floor IVR both predate it), but it is a second, independent point where the structure's quality could have been re-checked and wasn't.

**Suggested fix:** after any strike shift in this block, re-run the same delta-band check used for original selection against the new leg, and recompute basic structure economics (net credit, max loss, R:R) before accepting — if the shifted leg now fails those, treat it the same as "adjustment failed" (falls through to the existing `if not adjusted:` gate-violation/log-only path) rather than silently accepting a structure that was never fully vetted.

**Related:** `BUG-006` — without a persisted intraday snapshot at decision time, verifying whether this adjustment path fired at a *reasonable* delta vs. an already-degraded one is harder to audit after the fact.

---

## BUG-008 — Dry-run output bakes in point-in-time price/IVR with no re-validation if executed later

| Field | Value |
|---|---|
| Severity | **HIGH** — a paper trade can be recorded against stale price/IVR/delta data if the printed dry-run commands are executed even a short time after generation |
| Status | ✅ Fixed (2026-07-03, SHA d09d316) |
| Discovered | 2026-07-03, checking whether `record_paper_trade.py` re-validates anything when the dry-run's printed commands are pasted and run |
| Location | `scripts/strategies/ic/paper_ic_entry.py` (dry-run command generation) → `scripts/record/record_paper_trade.py` line ~645 |

**Fix summary (B008.2–B008.5):** Decision (Animesh, B008.2): option (a) — `record_paper_trade.py` always re-fetches a live LTP even when `--price` is explicit, and warns/blocks on drift. New pure function `_evaluate_price_drift(claimed_price, live_price, tolerance_pct=Decimal("0.10"))`: silent under 5% drift, WARNING at 5–10%, ERROR (hard block, `sys.exit(1)`) above 10% — `--force-entry` overrides the block (reuses the existing R3-override flag/pattern rather than adding a new one). Gated on `price_was_explicit and not args.close and not args.dry_run`: `--close` already fetches a live LTP itself a few lines earlier; dry-run previews never write to the DB, so BUG-008's actual failure mode (a frozen dry-run price being pasted and executed *later*) only matters at real `--no-dry-run` execution time — gating this way also avoids an unnecessary live network call on every preview. Both the live-fetch call and the `Decimal(str(...))` conversion of the response are wrapped in one `except Exception` — a fetch failure or a malformed/non-numeric LTP value both degrade to "WARNING: live LTP unavailable — proceed unverified" rather than crashing or blocking (this asymmetry — warn-not-block on *unverifiable*, but block on *verified-and-drifted* — was deliberate; a price already exists from the caller, this isn't the `--close` auto-price path where an unresolvable LTP has to hard-block). Tests: `tests/unit/paper/test_record_paper_trade.py` — 4 unit tests on `_evaluate_price_drift` (within-tolerance silent, elevated-warn, past-tolerance-block, zero-price no-op) + 5 `main()` integration tests (blocks on stale price, `--force-entry` overrides, proceeds within tolerance, skipped in dry-run, skipped on `--close`); added an autouse `_no_network_price_drift_check` fixture (default-mocks `UpstoxMarketClient` to return `{}`) so the ~6 pre-existing tests that pass an explicit `--price` with `--no-dry-run` and never cared about this feature don't accidentally attempt a real network call — per-test `@patch` decorators still take precedence within their own test body. 43/43 pass. Reviewed via `general-purpose` agent substituting for `code-reviewer` (not exposed in this Cowork environment) against `REVIEW.md` — no CRITICAL/ERROR findings; one WARNING (exception-catch spans two failure classes under one message, G5-compliant since it's commented and intentional, not blocking) deferred as a documented follow-up, not required before commit. B008.3's IVR/DTE/delta-gate re-run at execution time (beyond price) was explicitly out of scope for this fix per the B008.2 decision — `record_paper_trade.py` already runs its own independent IVR (R3) gate at execution time regardless (pre-existing), and DTE/portfolio-delta re-validation was removed from the entry-gate surface entirely by the unrelated 2026-07-03 "IC entries judged in isolation" decision (DECISIONS.md) — not re-added here.

**Note:** `tests/unit/scripts/test_record_paper_trade_r3.py::test_r3_no_block_on_buy` fails in this Cowork sandbox — confirmed via revert-to-HEAD comparison that it fails identically on the *unmodified* pre-fix code too. Root cause: no real network route to `api.upstox.com` in this sandbox (proxy 403) combined with that test never mocking the pre-existing, unrelated IVR-gate VIX-fallback fetch (`fetch_vix_latest()`) it exercises via `action=BUY`. Pre-existing/environmental, not a regression from this fix — same class of limitation documented at B004.6/B006.6.

**Symptom:** none logged — found by code inspection while assessing how safe it would be to copy-paste the dry-run's `[DRY-RUN] Commands to execute:` block and run it later. `record_paper_trade.py:645` only fetches live LTP **when `--price` is omitted** (`if args.price is None: ... fetch LTP`). The dry-run always emits an explicit `--price <value>` taken from the chain snapshot at the moment `paper_ic_entry.py` ran. If those commands are executed minutes or hours later — the realistic workflow, since a human is meant to review the dry-run before acting — the recorded trade uses the original snapshot's price, not the current market, and none of the entry gates (IVR floor, DTE window, delta band, portfolio delta) are re-evaluated at execution time; those only run inside `paper_ic_entry.py`, not `record_paper_trade.py`.

**Root cause:** the gate-check/strike-selection step and the trade-recording step are two separate scripts connected only by a printed shell command containing frozen values — there is no re-validation boundary at execution time, and no timestamp/staleness check on the embedded price before it's written to `paper_trades`.

**Impact:** directly relevant to this session — DTE and IVR were already found to be outside their target windows at generation time (log-only, so the dry-run still printed commands); if those commands are executed later, the DB will record a paper trade whose entry price no longer reflects the market, with no warning surfaced anywhere in the pipeline.

**Suggested fix:** either (a) have `record_paper_trade.py` re-fetch live LTP and compare against the passed `--price` within some tolerance, warning or blocking on material drift, or (b) have the dry-run commands omit `--price` entirely and let `record_paper_trade.py`'s existing live-fetch path (already there for the no-price case) be the only path — accepting that the reviewed dry-run numbers are illustrative, not literal execution instructions. Either way, re-running the IVR/DTE/delta gates at actual execution time (not just at dry-run generation time) closes the real gap.

**Related:** `BUG-007` (same family — decisions made at one point in the pipeline are not re-checked at the point where they actually take effect).

---

## BUG-009 — `paper_ic_snapshot.py` can never resolve expiry from `instrument_key`, silently killing the daily IC EOD audit

| Field | Value |
|---|---|
| Severity | **HIGH** — daily snapshot report for both monthly IC variants is a permanent no-op; no P&L/audit visibility despite open positions |
| Status | ✅ Fixed |
| Discovered | 2026-07-03, investigating why no snapshot report arrived for `paper_ic_nifty_v2_monthly` after today's entry |
| Location | `scripts/strategies/ic/paper_ic_snapshot.py::process_variant` (lines ~115–134), regex defined line 44 |

**Symptom:** `logs/ic_snapshot.log`, 2026-07-03 15:45:05 — cron ran on schedule (`45 15 * * 1-5`), both variants had open positions, but output was:
```
ic_snapshot.no_expiry_found strategy=paper_ic_nifty_v1_monthly
ic_snapshot.no_expiry_found strategy=paper_ic_nifty_v2_monthly

📋 IC EOD Audit — monthly (paper_ic_nifty_v1_monthly)
Error: Expiry date could not be parsed from positions.

📋 IC EOD Audit — monthly (paper_ic_nifty_v2_monthly)
Error: Expiry date could not be parsed from positions.
```
No real audit ever reaches the user — just this error stub, and it's apparently not escalated anywhere visible (non-fatal notifier contract per `src/notifications/CLAUDE.md`), so the failure goes unnoticed until asked about directly.

**Root cause:**
```python
_EXPIRY_RE_ROBUST = re.compile(r"NIFTY(\d{2}[A-Za-z]{3}\d{4})", re.IGNORECASE)
...
m = _EXPIRY_RE_ROBUST.search(p.instrument_key)
```
This expects a trading-symbol string like `NIFTY28JUL2026...` embedded in `p.instrument_key`. Actual `instrument_key` values recorded in `paper_trades` (confirmed via query) are Upstox's numeric form — `NSE_FO|63930`, `NSE_FO|63987`, etc. — with no date substring anywhere. The regex can never match, `expiry` stays `None` for every leg of every variant, and the function always falls into the `no_expiry_found` branch regardless of whether positions are genuinely open and healthy.

**Impact:** confirmed today for `paper_ic_nifty_v2_monthly` (4 legs entered same day, all `OPEN` in `paper_trades`) and `paper_ic_nifty_v1_monthly` (also has open legs). This is not a one-off — the bug is structural (bad assumption baked into the regex), so it has silently broken the daily EOD audit for both variants since whichever commit last changed `instrument_key` to the numeric format, or since this script was first written against the wrong assumption. `git log --oneline` on this file not yet checked to date the regression precisely.

**Suggested fix:** don't derive expiry from a string pattern that was never present in the stored key. Either (a) reverse-lookup the numeric `instrument_key` against the offline instrument master (`src/instruments/`) to get the real trading symbol/expiry, or (b) store expiry directly on the position/trade row at entry time (`paper_trades` or `PaperPosition`) so downstream snapshot code doesn't need to reconstruct it at all. Option (b) avoids adding an instrument-master lookup dependency to a script whose only job is reporting.

**Fix (2026-07-03, option (a), per Animesh B009.2 decision):** replaced `_EXPIRY_RE_ROBUST` regex block in `process_variant` with `InstrumentLookup.get_by_key(p.instrument_key)` (the `lookup` param was already threaded into the function but unused) → `parse_expiry(inst.get("expiry"))` → `date.fromisoformat(...)`. Same lazy read-time resolution pattern as BUG-002's `PaperPosition.option_type` — no schema change, no migration, fixes historical rows immediately. Unresolvable/legacy `instrument_key` (lookup returns `None`, or `parse_expiry` returns `None`) falls back to the existing `no_expiry_found` branch unchanged — same safe-but-informative behavior as before, just no longer the *only* reachable path. `_EXPIRY_RE_ROBUST` constant and its now-dead code removed; `re` import retained (still used elsewhere in the file for signal-note parsing). 2 new dedicated tests on `process_variant` (numeric-key happy path resolves DTE correctly; unresolvable-key edge case still falls back to `no_expiry_found` without crashing) + existing suite's `mock_lookup` autouse fixture updated so `get_by_key` derives the same expiry the old regex used to, keeping all prior assertions valid without touching every test's fixture data. **Tests not executed this session** — sandbox `.local` disk quota exhausted (`pip install pytest` → `No space left on device`), same limitation class as B004.6/B006.6/B010.4–7; both touched files verified via `py_compile` only. Logic traced manually against `InstrumentLookup.get_by_key`/`parse_expiry` signatures confirmed via the codebase graph.

**Related:** none yet — first bug traced to `paper_ic_snapshot.py` itself; distinct from `BUG-002`'s put/call substring-matching bug in `_position_delta`, though both stem from the same class of mistake (assuming a trading-symbol string is present where only a numeric `instrument_key` actually is).
