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
| Status | 🔴 **Reopened** (2026-07-26) — original "moot" closure was premature; real repro reappeared on the live host across all 4 `None`-expecting tests, not just one |
| Discovered | 2026-07-03, live-host `pytest` run surfaced by Animesh after BUG-010 B010.4 session. Reopened 2026-07-26 with a fresh full-suite repro. |
| Location | `tests/unit/test_notifications.py::test_build_notifier_returns_none_when_token_missing` + 3 sibling tests; suspected root cause in `src/config.py::_DynamicSettings` or a test elsewhere that mutates `os.environ` outside `monkeypatch` |

**Symptom:** `assert <src.notifications.telegram.TelegramNotifier object at 0x111d06c60> is None` — `build_notifier()` returned a real notifier instead of `None` even though the test calls `monkeypatch.delenv("TELEGRAM_BOT_TOKEN")` / `monkeypatch.delenv("TELEGRAM_CHAT_ID")` immediately beforehand.

**Not yet root-caused** — this entry logs a confirmed repro (real pytest failure, output pasted by Animesh), not a confirmed root cause; investigation is the first checklist step. Not caused by the B010.4 diff — that session touched only `scripts/portfolio/daily_snapshot.py` and a new test file, never `src/notifications/`, `src/config.py`, or `tests/unit/test_notifications.py`.

**Leading hypothesis:** `build_notifier()` reads through `settings.telegram_bot_token`/`telegram_chat_id`, where `settings` is the `_DynamicSettings` singleton (`src/config.py`) that rebuilds `Settings` only when `hash(frozenset(os.environ.items()))` changes since the last access. If `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are real values already present in the live host's process environment (exported in the shell, not `.env`-sourced) — or some other test in the suite writes directly into `os.environ` rather than through `monkeypatch` (whose reversion `monkeypatch.delenv` in *this* test can't undo if it happened in a different test's un-reverted mutation) — this test only passes when run in isolation, and fails as part of the full suite or a shell session that already exports the tokens. Unconfirmed until reproduced.

**Suggested fix (pending investigation):** (a) confirm via `pytest tests/unit/test_notifications.py::test_build_notifier_returns_none_when_token_missing -q` run alone vs. full-suite run — isolates whether this is cross-test leakage vs. a `_DynamicSettings` caching bug; (b) `echo $TELEGRAM_BOT_TOKEN $TELEGRAM_CHAT_ID` in the host shell running pytest to rule out real OS-level env vars; (c) if cross-test leakage is confirmed, `grep -rn "os.environ\[" tests/` for any raw (non-`monkeypatch`) mutation and convert it to `monkeypatch.setenv`.

**Original resolution (2026-07-03, investigation-only, no code change):** closed as fixed/moot, citing `fe69612` (2026-05-30) as a pre-existing fix. That closure did not actually reproduce the failure — it reasoned from code inspection only. Per its own reopen clause, logging fresh evidence below.

**2026-07-26 investigation (Animesh's live-host paste — real, not hypothetical):**

- `echo $TELEGRAM_BOT_TOKEN $TELEGRAM_CHAT_ID` on the live host → both empty. Rules out real shell-exported env vars (the original leading hypothesis).
- Running the single failing test in isolation → passes. Running it as part of `tests/unit/` + a handful of related files with `-n auto` → passes. Running the **full** `tests/unit/` suite → fails (all 4 `None`-expecting `build_notifier` tests, never the 2 that set real overriding values).
- Investigated `_DynamicSettings._get_settings()`'s cache-validity check, which compares `hash(frozenset(os.environ.items()))` across accesses. This is unsound on its own terms — hash equality doesn't imply content equality, so two different `os.environ` states can coincidentally collide — and was fixed regardless (`src/config.py`, compares the actual environ dict now, not its hash; see `DECISIONS.md` 2026-07-26). **This fix did not resolve the failure** — reproduced again in a sandbox environment with the fix applied, confirming hash-collision was not the actual root cause of BUG-011's symptom, even though the fix is independently correct and worth keeping.
- Sandbox reproduction is itself flaky under `-n auto` (fails on some runs, passes on others with no code change between runs) — consistent with a genuine cross-test interaction whose visibility depends on pytest-xdist's per-run worker/test assignment, which is not deterministic across runs.
- Ruled out: two candidate leak vectors tested directly (an unguarded `load_dotenv()` call inside `paper_snapshot.py::_run` with no `monkeypatch` cleanup; the same pattern in `src/auth/{dhan,nuvama}_{login,verify}.py`) — both inject real `.env` values into a worker's `os.environ` but `monkeypatch.delenv` still correctly strips them for the duration of any single test that calls it, in both isolated repro attempts.
- **Not yet root-caused.** Since `pytest-xdist` workers are separate processes with independent `os.environ`, the leak (whatever it is) must originate from a *different test in the same worker* via some path that survives past a `monkeypatch.delenv` call within `test_notifications.py`'s own test bodies — which should be structurally impossible given `monkeypatch`'s per-test teardown semantics, unless something re-populates `os.environ` (or bypasses the settings layer entirely) between the `delenv` line and the `build_notifier()` call. Next diagnostic step: temporarically add `print(f"TELEGRAM_BOT_TOKEN={os.environ.get('TELEGRAM_BOT_TOKEN')!r}", file=sys.stderr)` immediately before the `assert build_notifier() is None` line in the failing test, run with `-s` on the live host during an actual failing full-suite run, and capture the printed value — this pins down whether the leak is in `os.environ` itself (real cross-test contamination) or somewhere in the `Settings`/pydantic layer despite a clean `os.environ` (a different, more surprising bug).

**Status: reopened, unresolved.** The `_DynamicSettings` hash-vs-dict fix ships as an independent hardening measure, not a closure of this bug.

---

## BUG-012 — `paper_ic_snapshot.py` instantiated `IronCondorV2` with positional args, silently mis-binding config to the broker object

| Field | Value |
|---|---|
| Severity | **HIGH** — the V2 monthly IC's EOD signal evaluation had been silently no-op'ing (caught exception, degraded report) since `IronCondorV2` was first wired into the snapshot cron; no crash, no alert distinct from a normal chain hiccup |
| Status | ✅ Fixed — see `DECISIONS.md` 2026-07-06 entry for full root-cause writeup and commit |
| Discovered | 2026-07-06, user (Animesh) reported no IC snapshot for the day; traced via `logs/ic_snapshot.log` |
| Location | `scripts/strategies/ic/paper_ic_snapshot.py::process_variant` (constructor call site); root cause is signature-order divergence between `src/strategy/ic_nifty_v1.py::IronCondorV1.__init__` and `src/strategy/ic_nifty_v2.py::IronCondorV2.__init__` |

**Symptom:** `ic_snapshot.log` showed, for `paper_ic_nifty_v2_monthly` only: `ic_snapshot.check_signals_failed strategy=paper_ic_nifty_v2_monthly error='UpstoxLiveClient' object has no attribute 'expiry_type'`, surfaced to Telegram as "Error: Signal evaluation failed" instead of a real snapshot. `paper_ic_nifty_v1_monthly` produced a snapshot but with `LTP=N/A`/`δ=0.00` on every leg — a separate, already-tracked defect (see TODOS.md "Fix BOD resolution in CC / PP / Collar / IC V1 / IC V2 leg finders").

**Root cause:** `process_variant` calls `strategy_cls(broker, store, notifier, config)` positionally to generically instantiate either IC strategy class. `IronCondorV1.__init__(self, broker=None, store=None, notifier=None, config=None)` matches this order. `IronCondorV2.__init__(self, config=None, broker=None, store=None, notifier=None)` does not — so for every V2 invocation, `self._config` was bound to the live `UpstoxLiveClient` broker instance, `self._broker` to `store`, etc. This stayed invisible until `check_signals` accessed `self._config.expiry_type` deep inside `ProfitLockEngine().evaluate(...)`, which raised, was caught by `process_variant`'s own fail-safe `try/except Exception`, and downgraded to a one-line error report — no traceback reached logs at ERROR-with-stack level, no distinct alert from a routine chain-fetch failure.

**Fix:** `scripts/strategies/ic/paper_ic_snapshot.py:172` — call `strategy_cls(broker=broker, store=store, notifier=notifier, config=config)` by keyword, which binds correctly regardless of either class's declared parameter order. Confirmed via `@code-reviewer` that the only other instantiation site (`scripts/daemon/monitor_daemon.py`) already used keyword args for both classes — no other call site carried this risk.

**Test:** `tests/unit/strategies/ic/test_paper_ic_snapshot.py::test_process_variant_binds_constructor_args_by_keyword` — a fake `_ReversedSignatureStrategy` class with V2's real `__init__` order is passed as `strategy_cls`; `check_signals` asserts `self.config.strategy_name` matches the real config, which would fail under the pre-fix positional call (self.config would resolve to the mocked broker instead).

**Related:** the two-class polymorphic-strategy pattern in `process_variant` has no protocol/ABC enforcing a shared `__init__` signature — worth a follow-up to standardize both classes on the same constructor param order (or route construction through a small factory keyed by strategy version) so this class of bug can't recur when a V3 is added.

**Follow-up #2 (same day, 2026-07-06):** the same numeric-key/regex-only expiry-parsing defect existed independently in `scripts/strategies/ic/paper_ic_monthly_comparison.py::build_stats`, but with a worse symptom there — its `_EXPIRY_RE`-only expiry parse also feeds `build_comparison_report`'s "is this variant open?" check (`v1_open = v1.dte is not None`), so a genuinely open position with an unresolvable numeric key got mislabeled **"No open position"** in the V1-vs-V2 comparison Telegram report, hiding real entry credit/P&L/delta/signal data entirely (worse than `paper_ic_snapshot.py`'s symptom, which at least showed `N/A` rather than a false negative on position existence). Fix: `build_stats` gained an optional `lookup: InstrumentLookup | None` param with the same BOD-lookup fallback as `paper_ic_snapshot.py::process_variant`; `_run` now loads it once via a new `--bod-path` CLI arg (fail-safe — falls back to `lookup=None`, degrading to `dte=None` rather than crashing, on a missing/corrupt BOD file). A new `ICMonthlyStats.has_open_position: bool` field, set explicitly and only in `build_stats`'s two construction sites, decouples "position exists" from "DTE could be computed" — `build_comparison_report` now reads `has_open_position` instead of inferring open/closed from `dte`. `@code-reviewer`: no CRITICAL/ERROR findings; confirmed the two states are structurally decoupled (every return path in `build_stats` sets both fields together, so a "stale dte with no position" state is unreachable). 3 new tests: BOD-fallback expiry resolution for a numeric key, no-position still reports `has_open_position=False`, and a report-level test proving a genuinely-open-but-unresolvable-DTE position now renders `N/A` rather than the misleading "No open position".

**Follow-up (same day, 2026-07-06):** fixing the constructor bug above surfaced that the resulting reports were "successful" but hollow — every leg showed `LTP=N/A`/`δ=0.00`, and logs were full of `ic_nifty_v1.strike_parse_failed` / `ic_nifty_v2.strike_parse_failed`. Root cause: `IronCondorV1._find_leg` / `IronCondorV2._find_leg` parse strike+CE/PE from `instrument_key` via `_STRIKE_RE = re.compile(r"NIFTY(\d+)(PE|CE)")`, but real Upstox keys are numeric-only (`NSE_FO|63896`) and never match — the exact defect already fixed for CSP in `CSPNiftyV1._find_put_leg` (BUG-009/SM-1) but never ported to the IC strategies, despite being the item already tracked in TODOS.md ("Fix BOD resolution in CC / PP / Collar / IC V1 / IC V2 leg finders"). Fix: added `_find_leg_via_bod` to both `ic_nifty_v1.py` and `ic_nifty_v2.py`, mirroring `CSPNiftyV1._find_put_leg`'s BOD-lookup fallback (`InstrumentLookup.from_file(DEFAULT_BOD_PATH).get_by_key(instrument_key)` → `strike_price`/`instrument_type`), extended to handle both CE and PE (CSP is PE-only). Also fixed `IronCondorV2._position_strike` (feeds Zone 2 profit-lock strike resolution — a real signal-logic path, not just the report) with the same fallback inline. `@code-reviewer`: no CRITICAL/ERROR findings; confirmed both CE/PE handled, Decimal preserved throughout, `_position_strike`'s callers (Zone 2 profit-lock, roll wing strike lookups) verified as the previously-blind call sites. **Not fixed, flagged as follow-up**: `cc_overlay_v1.py`, `collar_overlay_v1.py`, `pp_overlay_v1.py`, and `nifty_track_comparison_v1.py` share the same `_STRIKE_RE`-only pattern and are still blind to numeric keys — this is the CC/PP/Collar portion of the original TODOS.md item, not yet addressed. Tests: `tests/unit/strategy/test_ic_nifty_v1.py` (4 new tests) and `tests/unit/strategy/test_ic_nifty_v2_signals.py` (4 new tests), all patching `src.instruments.lookup.InstrumentLookup.from_file` — confirmed to fail pre-fix and pass post-fix for the right reason.

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

**Fix (2026-07-03, option (a), per Animesh B009.2 decision):** replaced `_EXPIRY_RE_ROBUST` regex block in `process_variant` with `InstrumentLookup.get_by_key(p.instrument_key)` (the `lookup` param was already threaded into the function but unused) → `parse_expiry(inst.get("expiry"))` → `date.fromisoformat(...)`. Same lazy read-time resolution pattern as BUG-002's `PaperPosition.option_type` — no schema change, no migration, fixes historical rows immediately. Unresolvable/legacy `instrument_key` (lookup returns `None`, or `parse_expiry` returns `None`) falls back to the existing `no_expiry_found` branch unchanged — same safe-but-informative behavior as before, just no longer the *only* reachable path. `_EXPIRY_RE_ROBUST` constant and its now-dead code removed; `re` import retained (still used elsewhere in the file for signal-note parsing). 2 new dedicated tests on `process_variant` (numeric-key happy path resolves DTE correctly; unresolvable-key edge case still falls back to `no_expiry_found` without crashing) + existing suite's `mock_lookup` autouse fixture updated so `get_by_key` derives the same expiry the old regex used to, keeping all prior assertions valid without touching every test's fixture data. **Tests not executed this session** — sandbox `.local` disk quota exhausted (`pip install pytest` → `No space left on device`), same limitation class as B004.6/B006.6/B010.4–7; both touched files verified via `py_compile` only. Logic traced manually against `InstrumentLookup.get_by_key`/`parse_expiry` signatures confirmed via the codebase graph. Live-host test run caught one gap in the happy-path test (broker mock wasn't awaitable and `parse_upstox_option_chain` wasn't patched, so `process_variant` hit the chain-fetch error path before the DTE assertion) — fixed by adding `AsyncMock` on `broker.get_option_chain` and patching `parse_upstox_option_chain`, matching the pattern already used by the rest of the suite. All tests green on live host. Committed SHA `abafeaf`.

**Related:** none yet — first bug traced to `paper_ic_snapshot.py` itself; distinct from `BUG-002`'s put/call substring-matching bug in `_position_delta`, though both stem from the same class of mistake (assuming a trading-symbol string is present where only a numeric `instrument_key` actually is).

---

## BUG-013 — `IronCondorV1` never sends a Telegram close confirmation; `IronCondorV2` only sends one for the rare Zone-2 roll, not its own CLOSE_FULL

| Field | Value |
|---|---|
| Severity | **MEDIUM** — no capital/P&L impact (the close itself executes and persists correctly), but every full IC close is silent on the operator's primary monitoring channel, unlike every other auto-execute strategy |
| Status | ✅ Fixed (2026-07-20) |
| Discovered | 2026-07-20, user asked why a Telegram message was received for a `paper_ic_nifty_v1_monthly` `PROFIT_TARGET` auto-close — traced the actual execution path (`StrategyMonitor._route_event` → `IronCondorV1.apply_action` → `close_ic_legs()`) and found no notifier call anywhere in it |
| Location | `src/strategy/ic_nifty_v1.py::apply_action`; `src/strategy/ic_nifty_v2.py::apply_action` (`CLOSE_FULL`/`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` branch only — `PROFIT_LOCK_ZONE2` was already correct) |

**Symptom:** none logged anywhere — that's the bug. `IronCondorV1.check_signals()` correctly fires `PROFIT_TARGET`/`LOSS_STOP`/`TIME_STOP`/`DELTA_STOP`, `StrategyMonitor` correctly auto-dispatches to `apply_action()`, `close_ic_legs()` correctly persists the closing `PaperTrade` rows — every part of the close executes and is logged (`ic_nifty_v1.apply_action`, `ic_close_executor.legs_closed`, `strategy_monitor.auto_execute_dispatched`), but nothing ever reaches Telegram. Confirmed by checking every strategy's notifier usage: `CSPNiftyV1`, `CCOverlayV1`, `CollarOverlayV1`, and `PPOverlayV1` all call `TelegramGateway.send_notification()` on close via a `_send_notification`/inline `hasattr(self._notifier, "send_notification")` pattern. `IronCondorV1` accepts a `notifier: TelegramGateway | None` constructor argument, stores it as `self._notifier`, and never references it again anywhere in the file — a dead parameter. `IronCondorV2` does call `self._send_profit_lock_notification()`, but only from the `PROFIT_LOCK_ZONE2` branch (a rare partial roll); its `CLOSE_FULL`/`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` branch — the action actually triggered by the common `PROFIT_TARGET`/`FORCED_CLOSE` signals — calls `close_ic_legs()` directly with no notification step, same gap as V1.

The `StrategyMonitor` module docstring (`src/strategy/monitor.py` lines 7-8) documents `"ACTION + strategy.auto_execute + payload["auto_execute"] → apply_action() called directly; send_notification() on completion"` — this describes intended behavior that was never actually implemented for either IC strategy; the docstring itself is stale/aspirational relative to the code, not evidence of a call site that exists.

**Root cause:** `IronCondorV1`/`IronCondorV2` were built with the `close_ic_legs()` persistence path (2026-07-15 fix, TODOS.md) as their primary concern — getting the DB write to happen at all was the priority bug at the time — and Telegram confirmation was never added as a follow-up once persistence was fixed, unlike the overlay/CSP strategies which had notification wired in from their original implementation.

**Impact:** operationally confusing (this is literally how it was discovered — a real close happened with no expected Telegram trail, and a message that *was* received turned out to come from a separate, unrelated cron — `scripts/strategies/ic/paper_ic_snapshot.py`'s EOD audit — not from the close itself), but no capital or data-integrity impact: the close was correctly persisted and would show up in the next EOD/portfolio snapshot regardless of notification. Risk is purely "operator doesn't find out a position closed until the next scheduled report runs," which for TIME_STOP/DTE-driven closes near expiry could be a multi-hour gap.

**Fix (2026-07-20):** added `IronCondorV1._send_close_notification()` (mirrors `CSPNiftyV1._send_notification` pattern) and wired it into `apply_action()`'s `CLOSE_FULL`/`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` auto-execute branch, called with the `PaperTrade` rows actually returned by `close_ic_legs()` (empty list → no-op, since `close_ic_legs()` already logs `ic_close_executor.nothing_to_close` for that case). Added the equivalent `IronCondorV2._send_close_notification()` for the same three action types in its `apply_action()` — the existing `_send_profit_lock_notification()` for `PROFIT_LOCK_ZONE2` is untouched, this is a second, separate notification for the full/spread-close path it never had. Both non-fatal (logged WARNING/ERROR on send failure, never raises) matching the project's notifier contract. `ROLL_WING`'s own close side remains unnotified — same known scope boundary as `IC-CLOSE-2` (TODOS.md), the replacement leg isn't persisted yet either, so a roll-close notification would be misleading before that's built.

**Related:** the 2026-07-15 `close_ic_legs()` persistence fix (TODOS.md) this notification gap sat behind; `DECISIONS.md` 2026-07-20 (same session, the `lookup=` wiring fix and silent-failure-logging pass that led to discovering this).

---

## BUG-014 — `get_positions()` resolves `option_type` unconditionally, generating permanent unactionable warnings for closed legs on delisted contracts

| Field | Value |
|---|---|
| Severity | **MEDIUM** — pure log noise, no capital or data-integrity impact; but the noise is permanent and will recur on every snapshot run forever for affected legs |
| Status | ✅ Fixed (2026-07-20) |
| Discovered | 2026-07-20, investigating repeated `option_type_resolution_failed` warnings in `logs/paper_snapshot.log` (`trace_id=f5985444`) |
| Location | `src/paper/store.py::PaperStore.get_positions` (line ~611, `_resolve_option_type` call site) |

**Symptom:** `option_type_resolution_failed instrument_key=NSE_FO|71474 reason="instrument_key not found in BOD JSON"` and the same for `NSE_FO|44498`, logged on every EOD snapshot run despite both legs having `net_qty == 0` (fully closed, per `paper_trades`: `71474` closed 2026-06-08, `44498` settled ITM 2026-07-17).

**Root cause:** `get_positions()` builds one `PaperPosition` per `leg_role` a strategy has ever traded, grouped only by `leg_role` with no filter on the resulting `net_qty`. It always calls `self._resolve_option_type(cycle_instrument_key)` at construction time (added in `96398b4`, 2026-07-02, B002.3) — before any caller has a chance to apply the `net_qty != 0` filtering convention used everywhere downstream (`paper_3track_snapshot.py:378,567,1200`; the `all_open_pos` loop referenced in BUG-005). `96398b4`'s own 9-test suite covers BOD-load-failure and unresolved-key paths but never a `net_qty == 0` leg. Since Upstox's BOD file drops delisted/expired contracts once settled, any closed leg's `cycle_instrument_key` will *never* resolve again — the warning is not staleness, it's permanent.

**Impact:** no functional impact (`option_type` degrades to `None`, which every downstream caller already treats as a valid, non-fatal state per the field's own docstring). Purely operational: log noise obscures genuine BOD-staleness or resolution issues on legs that are actually still open.

**Suggested fix:** guard the `_resolve_option_type` call in `get_positions()`/`get_position` on `net_qty != 0` — skip resolution (and leave `option_type=None`) for flat legs, consistent with how `_check_base_expiry` already skips flat legs before its own BOD-dependent lookup (`scripts/strategies/three_track/paper_3track_snapshot.py:377-378`). Financial-logic change inside `PaperStore` — requires the real `@code-reviewer` gate per project protocol, not just a patch.

**Related:** BUG-005 (same `net_qty != 0` filtering convention, different call site — that bug is about a missing filter in the IC entry scripts' cross-strategy pooling loop, this one is about the filter being applied too late, after resolution already ran).

**Fix (2026-07-20):** guarded the `_resolve_option_type` call in `get_positions()` on `net_qty != 0` — skips resolution entirely for flat legs, leaving `option_type=None` (already a valid, documented state) without ever touching `InstrumentLookup`. `.py` change in `src/paper/store.py`; per project protocol this required the real `@code-reviewer` gate before commit — Cowork mode cannot spawn this project's local `.claude/agents/code-reviewer` subagent (only generic agent types available in this surface), so the gate was satisfied by applying `code-reviewer.md`'s exact checklist directly rather than skipping it, per the protocol's own "structurally cannot spawn `.claude/agents/*`" allowance. Findings: no CRITICAL/ERROR; traced the one production caller of `PortfolioDeltaTracker.aggregate_delta` (`scripts/record/record_paper_trade.py:833`) to confirm it already filters `net_qty != 0` before calling in, so closed legs never reach `option_type`-branching logic there regardless of this change — no regression. One WARNING-level doc gap (not behavioral): `PaperPosition.option_type`'s docstring didn't yet list "flat leg, resolution skipped" as a reason for `None` — fixed in `src/paper/models.py`. Tests: 2 new in `tests/unit/paper/test_store.py` (open leg still resolves as before; closed leg's resolution call is asserted to never fire, not just degrade to `None`, via a spy that raises if invoked) — 71/71 passing in that file; full regression check across `test_store.py`, `test_track_snapshot.py`, `test_tracker.py`, `tests/unit/risk/` (120 tests) all green.

---

## BUG-015 — `base_futures` leg (`paper_nifty_futures`) recorded wrong quantity (75 instead of correct lot size 65) on the May 2026 settlement-close and roll, corrupting the leg's cycle tracking

| Field | Value |
|---|---|
| Severity | **HIGH** — live base leg's current `net_qty` and `instrument_key` attribution are both wrong; roll/expiry monitoring for this leg is silently mis-targeted |
| Status | ✅ Fixed (2026-07-20) |
| Discovered | 2026-07-20, investigating `base_expiry.expiry_not_found instrument_key=NSE_FO|66071` in `logs/paper_snapshot.log` (`trace_id=f5985444`) |
| Location | `paper_trades` rows for `paper_nifty_futures` / `base_futures`, `NSE_FO|66071` (2026-05-26) and `NSE_FO|62329` (2026-05-29); cycle-tracking logic in `src/paper/store.py::get_positions` (DBI-3, `425e054`) |

**Symptom:** `_check_base_expiry` (`scripts/strategies/three_track/paper_3track_snapshot.py:392`) logs `base_expiry.expiry_not_found` for `NSE_FO|66071` — a NIFTY futures contract that expired 2026-05-26, nearly two months ago — because `get_positions()` still reports the open `base_futures` position as keyed to it.

**Root cause:** Trade history: `BUY 65 NSE_FO|66071` (2026-05-11, correctly 1 lot at the current 65 lot size per `DateAwareLotSizeResolver`'s Jan-1-2026-onward table) → `SELL 75 NSE_FO|66071` (2026-05-26, "Settlement close") → `BUY 75 NSE_FO|62329` (2026-05-29, "Base roll: June futures"). Both the settlement-close and the roll used quantity 75 — the *previous* Nifty lot size (in effect Nov 2024–Dec 2025), not the correct 65 in effect at the time. `DateAwareLotSizeResolver` isn't even wired into the paper-trading path (its only callers are `src/portfolio/strategies/finideas/finrakshak.py` and `ilts.py`) — quantity on these trade-recording scripts is a manually supplied CLI argument, so this is a data-entry error (likely muscle memory from the pre-changeover convention), not a code defect in the resolver or recording scripts. The mismatched 65/75 quantities mean running `net_qty` (`65 − 75 = −10`) never crosses exactly zero, so `get_positions()`'s DBI-3 cycle-reset (`src/paper/store.py`, resets `cycle_instrument_key` only on an exact zero-crossing) never fires — the June roll's `BUY 75` folds into the same still-open cycle (`−10 + 75 = 65`), and `cycle_instrument_key` stays frozen on the expired May contract instead of updating to the June one.

**Impact:** `base_futures`'s reported `net_qty` (65) happens to look numerically plausible by coincidence, masking that the underlying ledger is wrong and that the position is attributed to a delisted instrument_key. Roll/expiry monitoring (`_check_base_expiry`) for this leg is checking the wrong contract's expiry — if a further roll happened after `62329`, its expiry is not being monitored at all currently.

**Suggested fix:** corrective SQL update on the two `paper_trades` rows (75 → 65) to restore an exact zero-crossing, then verify `get_positions()` correctly resets `cycle_instrument_key` to the intended current contract. Check whether the 65-vs-75 error propagated into any roll after `62329` before correcting.

**Related:** BUG-016 (same DBI-3 zero-crossing cycle-reset assumption broken by a different data-entry gap); DECISIONS.md DBI-3 entry (`425e054`); BUG-017 (new — the error's propagation check surfaced that `62329` was never rolled after its own 2026-06-30 expiry, a separate live gap this fix exposed rather than caused).

**Fix (2026-07-20):** confirmed via full trade-history pull that the 75-vs-75 error did not propagate past `NSE_FO|62329` — no roll exists after it, so only the two original rows (`id=29` SELL, `id=30` BUY) needed correction. Updated both quantities 75 → 65 in `paper_trades`, with a `notes` annotation identifying the correction and citing `DateAwareLotSizeResolver`'s date table as the source of truth (65 in effect for both trade dates, 75 was the pre-2026-01-01 value). Data-only correction, no `.py` change. Verified by reimplementing `get_positions()`'s exact cycle-tracking algorithm against the live DB (as with BUG-016 — project `.venv` unusable this session): `paper_nifty_futures`/`base_futures` now correctly reports `net_qty=65`, `instrument_key=NSE_FO|62329`, `entry_date=2026-05-29`. Surfaced BUG-017 as a direct consequence — logged separately rather than folded into this fix, since resolving it requires an actual roll decision (new contract selection), not a ledger correction.

---

## BUG-016 — `overlay_pp` roll on 2026-06-29 never recorded a closing trade for `paper_nifty_spot`/`paper_nifty_futures`, leaving both tracks double-booked at 2x the intended position

| Field | Value |
|---|---|
| Severity | **HIGH** — two of three parallel tracks are currently carrying double the intended protective-put exposure, misattributed to an expired contract; this is a live position-sizing/risk misstatement, not just a stale reference |
| Status | ✅ Fixed (2026-07-20) |
| Discovered | 2026-07-20, investigating `option_type_resolution_failed instrument_key=NSE_FO|58627` in `logs/paper_snapshot.log` (`trace_id=f5985444`) |
| Location | `paper_trades` rows for `paper_nifty_spot` and `paper_nifty_futures` / `overlay_pp`, `NSE_FO|58627` (22000 PE, expiry 2026-06-30); cycle-tracking logic in `src/paper/store.py::get_positions` (DBI-3, `425e054`) |

**Symptom:** `option_type_resolution_failed` fires for `NSE_FO|58627`, a 22000 PE that expired 2026-06-30, three weeks ago — because `get_positions()` still reports it as the current `overlay_pp` position's `cycle_instrument_key` for two of the three parallel tracks.

**Root cause:** Trade history across all three strategies: `BUY 65 NSE_FO|58627` (2026-05-11, all three of `paper_nifty_spot`/`paper_nifty_futures`/`paper_nifty_proxy` open identically) → `SELL 65 NSE_FO|58627 @ 0.05` (2026-05-27, **`paper_nifty_proxy` only**) → `BUY 65 NSE_FO|63848` (21800 PE, exp 2026-07-28) (2026-06-29, all three open the roll). `paper_nifty_proxy` closed the expiring 22000 PE near-worthless before opening the new 21800 PE roll — a clean, zero-crossing cycle. `paper_nifty_spot` and `paper_nifty_futures` never got the matching `SELL 65` close; both went straight from the original May `BUY` into the June 29 roll `BUY` with nothing in between. Their running `net_qty` for this leg is therefore **130** (65 + 65 stacked), not 65 — the earlier per-strategy `SUM` check in this session only surfaced the aggregate and didn't catch the double-booking until the full per-row history was pulled. Because `net_qty` never crossed zero for these two tracks, `get_positions()`'s DBI-3 cycle-reset never fires, so `cycle_instrument_key` stays frozen on the expired `58627` instead of moving to `63848` — same failure mode as BUG-015, different trigger (a missing trade, not a wrong quantity).

**Impact:** `paper_nifty_spot` and `paper_nifty_futures` are each currently carrying a real double-booked protective-put position (old expired 22000 PE + new 21800 PE, both counted as one 130-unit lot misattributed to the expired contract) — this skews any P&L, delta, or notional-exposure calculation reading `overlay_pp`'s `net_qty`/`instrument_key` for these two tracks, not just a cosmetic log warning.

**Suggested fix:** backfill the missing `SELL 65 NSE_FO|58627` close trade for `paper_nifty_spot` and `paper_nifty_futures`, dated to match `paper_nifty_proxy`'s 2026-05-27 close (same price, 0.05, since all three tracks opened the original position identically and the contract's worthless-expiry economics don't differ by track). Verify `get_positions()` then correctly resets to `net_qty=65` on `NSE_FO|63848` for both tracks post-backfill.

**Related:** BUG-015 (same DBI-3 zero-crossing assumption broken by a different data-entry gap — missing trade here vs. wrong quantity there); both point to the same underlying process gap: roll trades recorded per-track manually with no cross-track consistency check.

**Fix (2026-07-20):** backfilled the missing `SELL 65 NSE_FO|58627 @ 0.05` close trade into `paper_trades` for `paper_nifty_spot` and `paper_nifty_futures`, dated `2026-05-27` to match `paper_nifty_proxy`'s existing close row exactly (same price, same `ivr_at_entry=0.3110992529348986`), with a `notes` annotation identifying it as a BUG-016 backfill. Data-only correction — no `.py` change, `UNIQUE(strategy_name, leg_role, instrument_key, trade_date, action)` constraint confirmed non-conflicting before insert (differs by `strategy_name` from the existing proxy row). Verified by reimplementing `PaperStore.get_positions()`'s exact cycle-tracking algorithm against the live DB (project `.venv` unusable in this session's sandbox — broken symlink to a macOS-only interpreter) rather than trusting a paraphrase: all three tracks now report `net_qty=65`, `instrument_key=NSE_FO|63848`, `entry_date=2026-06-29` for `overlay_pp` — matching, no longer double-booked or misattributed to the expired `58627`.

---

## BUG-017 — `paper_nifty_futures`/`base_futures` never rolled past its June contract; `NSE_FO|62329` has sat expired 20 days with no successor

| Field | Value |
|---|---|
| Severity | **HIGH** — the base futures leg (hedge notional for the 3-track comparison) is currently unhedged/stale on an expired contract with no live price feed; needs an operator roll decision, not a code or data fix |
| Status | ✅ Fixed (2026-07-20) |
| Discovered | 2026-07-20, as a direct consequence of fixing BUG-015 — correcting the 66071→62329 quantity error required pulling `base_futures`'s complete trade history, which showed only 3 rows total, ending at the June roll |
| Location | `paper_trades`, `paper_nifty_futures` / `base_futures`, `NSE_FO|62329` (June 2026 NIFTY futures, expiry 2026-06-30) |

**Symptom:** none logged as a distinct warning yet — post-BUG-015 fix, `_check_base_expiry` will now correctly target `NSE_FO|62329` instead of the wrong `66071`, and should start firing `base_expiry.expiry_not_found` (or a large negative-DTE alert, depending on whether `62329` still resolves in the BOD file) on the next snapshot run, since DTE has been negative for 20 days.

**Root cause:** the base futures leg was rolled once, correctly in intent (May → June, `id=30`, 2026-05-29), but no further roll was ever recorded after the June contract's 2026-06-30 expiry. Unlike `overlay_pp` (BUG-016, where the roll happened but the close was missing) or the option base leg (`base_ditm_call`, `44498`, which did settle correctly 2026-07-17), this leg's roll process simply stopped after one cycle — no trade of any kind exists for this leg after 2026-05-29.

**Impact:** the paper book's futures-based hedge/comparison track has had no live, valid instrument backing this leg for three weeks. Any P&L, delta, or notional-exposure read on `paper_nifty_futures`/`base_futures` since 2026-06-30 is against a settled, non-existent contract — not simply "stale data" but "no real position," which is a bigger problem for a leg whose whole purpose is to track live futures-based hedging.

**Suggested fix:** not a data correction — requires deciding and recording an actual roll (settlement-close `NSE_FO|62329` at its 2026-06-30 settlement price, then open the next NIFTY futures contract, likely September quarterly per the contract's monthly-only listing convention). This is a live trading/strategy decision, not a bug patch — flagging for operator action rather than fixing unilaterally.

**Related:** BUG-015 (the quantity-error fix this was discovered while verifying); BUG-016 (same "roll process incomplete" family — a different leg, different failure shape, same underlying gap: rolls recorded manually per-leg with no completeness check or reminder once a leg goes quiet).

**Fix (2026-07-20):** operator decision — roll directly into August (`NSE_FO|58072`, expiry 2026-08-25), skipping July (`NSE_FO|61093`, only 8 DTE remaining at decision time, not worth entering). Prices sourced live rather than approximated (correcting the same shortcut that caused BUG-015): June settlement-close used the official NSE Final Settlement Price from the FUTIDX bhavcopy (`settle_price=23865.75` for the 2026-06-30 expiry row, fetched via `scripts/pipeline/bhavcopy_bootstrap.py --underlying NIFTY --start 2026-06-30 --end 2026-06-30 --include-futures`, written to `data/offline/futures_ohlcv/2026/06/nifty_2026_06.parquet`) — distinct from and more correct than that day's traded close (23861.80). August open used a live LTP fetch via `UpstoxMarketClient.get_ltp_sync` (24364.0, against spot 24238.5 — this session's sandbox has no route to `api.upstox.com`, so the operator ran the fetch locally and supplied the result). Recorded: `SELL 65 NSE_FO|62329 @ 23865.75` (2026-06-30), `BUY 65 NSE_FO|58072 @ 24364.0` (2026-07-20). Verified via the same `get_positions()` reimplementation used for BUG-015/016: `net_qty=65`, `instrument_key=NSE_FO|58072`, `entry_date=2026-07-20` — leg is live and correctly hedged again after 20 days unrolled.

---

## BUG-018 — `IronCondorV2._parse_expiry` never matches real Upstox instrument keys; `check_signals` has silently no-op'd for `paper_ic_nifty_v2_monthly` since entry (2026-07-03)

| Field | Value |
|---|---|
| Severity | **HIGH** — the V2 monthly IC's live profit-target, profit-lock (25/50/75% zones), DTE hard-close, and delta-based forced-close signals have never fired once since entry; the position has been running completely unmanaged by its own strategy logic for three weeks |
| Status | ✅ Fixed and committed (2026-07-23, SHA `3435c5a`); diagnostics added, pending 2026-07-24 live tick verification + removal |
| Discovered | 2026-07-23, investigating a user-reported discrepancy: `paper_snapshot.py`'s EOD `paper_nav_snapshots` row for `paper_ic_nifty_v2_monthly` showed 66.4% of max credit captured on 2026-07-21, but `paper_strategies.profit_lock_zone` had never advanced past 0 (not even the 25% log-only milestone) |
| Location | `src/strategy/ic_nifty_v2.py::IronCondorV2._parse_expiry` (was regex-only; `_EXPIRY_RE` defined near top of file) |

**Symptom:** across the full retained `logs/monitor_daemon.log` window (2026-07-20 through 2026-07-22, 571 ticks across all registered strategies), the string `ic_nifty_v2` appears exactly 3 times — once per day, and every occurrence is the startup `Registered IronCondorV2` line. Zero `mark_unavailable`, zero `pnl_gate_skipped`, zero `profit_lock`, zero delta-signal log lines — nothing from `check_signals` actually running its logic, in contrast to `ic_nifty_v1` which logs on every tick (1,690 `mark_unavailable`/`pnl_gate_skipped` hits over the same window, all attributable to V1).

**Root cause:** `_EXPIRY_RE = re.compile(r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})", re.IGNORECASE)` expects a trading-symbol string (e.g. `NSE_FO|NIFTY28JUL2026...`). Real `instrument_key` values recorded in `paper_trades` for this position are Upstox's numeric form (`NSE_FO|63930`, `NSE_FO|63896`, `NSE_FO|63975`, `NSE_FO|63987`) with no date substring anywhere — the regex can never match, `_parse_expiry` returns `None` for every leg, and `check_signals` hits `if expiry is None: return []` at the very first gate, before the DTE/profit-target/profit-lock code (which begins at the P&L computation step) is ever reached. Identical root cause to **BUG-009** (`paper_ic_snapshot.py`'s EOD audit script, fixed 2026-07-03 via BOD reverse-lookup) and the same class of defect as **BUG-012**'s follow-up, which already fixed `IronCondorV2._find_leg`/`_position_strike` (strike resolution) with a regex-first/BOD-fallback pattern — but that fix was never ported to `_parse_expiry` (DTE/expiry resolution), which is a separate code path.

**Impact:** confirmed for `paper_ic_nifty_v2_monthly` (4 legs entered 2026-07-03, still all `OPEN`). For the entire life of this position, DTE hard-close, the 70% profit-target `CLOSE_FULL`, all three `ProfitLockEngine` zones (25/50/75%), and delta-based `FORCED_CLOSE`/roll evaluation have never executed — the position has been held open purely because nothing ever told it to close or roll, not because none of those conditions were met. `paper_snapshot.py`'s independent `PaperTracker.compute_pnl` (via `get_ltp()`, no expiry dependency) continued computing and persisting real P&L the whole time, which is why the EOD snapshot showed real captured-fraction numbers (66.4% on 07-21, 38.0% on 07-22) while the live strategy remained completely blind to them.

**Contributing factor — test fixture drift:** `tests/unit/strategy/test_ic_nifty_v2_signals.py`'s `_key()` fixture builds keys in the old trading-symbol form (`NSE_FO|NIFTY31JUL2026NIFTY{strike}{type}`), which happens to satisfy the broken regex — so the existing `check_signals` pipeline tests never exercised the real numeric-key path and never caught this. Same test-realism gap noted in BUG-012.

**Fix (2026-07-23):** mirrored `_find_leg`'s established regex-first/BOD-fallback pattern (rather than removing the regex outright, to preserve existing test fixtures and stay consistent with this file's own convention): `_parse_expiry` tries `_EXPIRY_RE` first, and on no match falls back to `InstrumentLookup.from_file(DEFAULT_BOD_PATH).get_by_key(instrument_key)` → `parse_expiry(inst.get("expiry"))` → `date.fromisoformat(...)`, same helper (`src.instruments.lookup.parse_expiry`) BUG-009's fix used. Unresolvable keys / BOD read failures (`OSError`) degrade to `None` and log a WARNING, never raise. Added two temporary diagnostic `log.debug` calls in `check_signals` (tagged `check_signals_entry_diag` / `check_signals_expiry_diag` / `check_signals_pnl_diag`, marked for removal after 2026-07-24 verification) to confirm live ticks now reach the P&L/profit-lock code instead of short-circuiting.

**Tests:** `tests/unit/strategy/test_ic_nifty_v2_signals.py` — `test_parse_expiry_resolves_numeric_key_via_bod`, `test_parse_expiry_resolves_numeric_key_via_bod_epoch_ms`, `test_parse_expiry_numeric_key_not_in_bod_returns_none`, `test_parse_expiry_bod_lookup_raises_returns_none` (mirror BUG-012's `_find_leg`/`_position_strike` test pattern), plus `test_check_signals_end_to_end_resolves_expiry_via_bod` — a full `check_signals` run using real numeric keys (`NSE_FO|63930` etc., not the fixture's old `_key()` form) with a mocked BOD lookup covering all 4 legs, asserting both diagnostic log lines fire with real values and the pipeline reaches its correct hold/`[]` outcome rather than the dead-on-arrival early return. Written in-sandbox (disk quota exhausted here, `pip install pytest` → `ENOSPC`, `.venv` unusable — macOS-only symlink), **run on live host by Animesh 2026-07-23: 26/26 pass in `test_ic_nifty_v2_signals.py`** (initial run caught a real bug in the new end-to-end test itself, not the fix — uniform LTP=50 on all four legs collapsed `combined_mark` to 0, i.e. 100% captured, correctly triggering `CLOSE_FULL` instead of the asserted `[]`; fixed by giving legs distinct LTPs landing at a genuine 10% captured, well under every zone/delta threshold, plus an assertion on `check_signals_pnl_diag`'s `captured_fraction == "0.1000"` so the test can't pass by coincidence again). Full `tests/unit/` suite subsequently run clean: 2451 passed, 2 skipped (pre-existing, unrelated).

**Code review (2026-07-23):** general-purpose agent explicitly loaded `.claude/agents/code-reviewer.md` + `REVIEW.md` and reviewed the scoped diff (this Cowork surface cannot spawn the real `@code-reviewer` subagent). 0 CRITICAL, 0 ERROR, 2 WARNING, 2 INFO. Findings: (1) WARNING — `_parse_expiry`'s BOD fallback now fires on every live tick (real keys are always numeric), adding a third uncached `InstrumentLookup.from_file()` gzip+JSON-parse call per tick alongside the pre-existing `_find_leg_via_bod`/`_position_strike` callers; deferred — pre-existing uncached pattern in this file, not introduced by this fix, but worth hoisting to a memoized/constructor-injected lookup in a follow-up. (2) WARNING — the original two `_parse_expiry` unit tests only fed `expiry` as an ISO string, never exercising the epoch-ms int branch real BOD data actually returns (`src/instruments/lookup.py::parse_expiry`'s int branch) — the same test-realism gap class that hid BUG-018 itself; **fixed immediately**, added `test_parse_expiry_resolves_numeric_key_via_bod_epoch_ms`. (3) INFO — doc said "two" diagnostic log lines, code has three; fixed in CONTEXT.md/TODOS.md. (4) INFO — eager `Decimal.quantize()`/`str()` work in the pnl_diag log call regardless of log level; accepted, line is temporary (removal tagged 2026-07-24). Decimal correctness and exception-scope calibration (`ValueError`/`OSError`) both verified clean, no findings.

**Related:** BUG-009 (identical root cause, different script), BUG-012 (same fix pattern, different method in the same file — `_find_leg`/`_position_strike` vs `_parse_expiry`).

**Committed:** SHA `3435c5a`.

**Open follow-ups (tracked in TODOS.md):**
1. Check `logs/monitor_daemon.log` on 2026-07-24 for `ic_nifty_v2.check_signals_pnl_diag` on `paper_ic_nifty_v2_monthly` — confirms the fix reaches live P&L evaluation in production, not just under test. Once confirmed, remove the 3 temporary diagnostic `log.debug` lines (`check_signals_entry_diag`/`check_signals_expiry_diag`/`check_signals_pnl_diag`) from `check_signals`.
2. Deferred WARNING from code review: `_parse_expiry`'s BOD fallback now fires on every live tick (real keys are always numeric), adding a third uncached `InstrumentLookup.from_file()` read per tick alongside `_find_leg_via_bod`/`_position_strike`. Hoist to a memoized/constructor-injected lookup (pre-existing pattern in this file, not unique to this fix — worth fixing once, for all three call sites).

**Related open investigation:** BUG-019 — Animesh generalised this to "is the live-vs-EOD-snapshot disparity happening for every strategy, not just V2 monthly?" See BUG-019 below.

---

## BUG-019 — Investigation: does every strategy show a live-tick vs. EOD-snapshot P&L disparity, not just `paper_ic_nifty_v2_monthly`?

| Field | Value |
|---|---|
| Severity | **Under investigation** — not yet confirmed as a bug beyond the BUG-018 case; diagnostic instrumentation added to gather evidence across all strategies |
| Status | 🔍 Diagnostics added and committed (2026-07-23, SHA `f7177b6`), awaiting a live trading day's data before any fix is scoped |
| Discovered | 2026-07-23, as a direct generalisation of BUG-018 — Animesh: "can we have some debugs added to check for all the strategy what is the PNL at 15:30 and what does the snapshot measure, i believe there is a disparency" |
| Location | `src/strategy/monitor.py::StrategyMonitor` |

**Hypothesis being tested:** BUG-018 showed `paper_ic_nifty_v2_monthly`'s own internal P&L computation (`_compute_combined_pnl` inside `check_signals`) never ran at all (silently short-circuited before reaching it) — so the "disparity" there was actually "the live side computed nothing," not "the two sides computed different numbers using the same inputs." Now that BUG-018 is fixed, Animesh suspects a *broader* disparity may exist across all strategies between what the live monitor tick sees intraday (specifically near close, ~15:30) and what `paper_snapshot.py`'s EOD cron records a few minutes later (~15:35-15:36). This could be: (a) a genuine last-minute market move between the last tick and the EOD read (not a bug), (b) a real computation/staleness bug independent of BUG-018, or (c) nothing — the two readings may in fact agree once V2 is no longer blind.

**Instrumentation added (2026-07-23):** `StrategyMonitor._log_live_pnl_diag()`, called at the end of every `_tick()`. Restricted to the 15:20-15:30 IST window (not every ~90s tick all day, to avoid adding a `get_ltp` batch call per strategy on every tick). For every registered strategy with at least one open leg (`net_qty != 0`), it calls `PaperTracker.compute_pnl(strategy_name)` — the *exact same function* `paper_snapshot.py`'s EOD cron calls, not an approximation — and logs `strategy_monitor.live_pnl_diag` with `unrealized_pnl`/`realized_pnl`/`total_pnl`/`time`. Because it's the identical function, any gap between this tick's reading (~15:20-15:30) and the EOD snapshot's own log line (`Recorded paper NAV snapshot for '<strategy>' ... total_pnl=X`, ~15:35-15:36) is a genuine timing/staleness disparity, not a methodology difference — the two sides can be diffed directly.

**Tests:** `tests/unit/strategy/test_strategy_monitor.py` — `test_live_pnl_diag_logged_inside_close_window`, `test_live_pnl_diag_skipped_outside_window`, `test_live_pnl_diag_skipped_when_strategy_flat`, `test_live_pnl_diag_swallows_compute_pnl_exception`, `test_live_pnl_diag_skipped_when_compute_pnl_returns_none`, `test_live_pnl_diag_window_boundaries` (parametrized, added after code review — see below). **Not run in-sandbox** (same disk-quota limitation as BUG-018) — verified via `py_compile` only, pending live-host `pytest` run.

**Code review (2026-07-23):** general-purpose agent loaded `.claude/agents/code-reviewer.md` + `REVIEW.md` directly and reviewed the scoped diff. 1 CRITICAL, 2 WARNING, 1 INFO — all resolved before commit:
- **CRITICAL** (REVIEW.md G5): `except Exception:` in `_log_live_pnl_diag` lacked the required inline `# Intentional: ...` comment (the docstring rationale doesn't satisfy the rule as written). Fixed: added inline comment on the `except` line.
- **WARNING**: the diag call was awaited *before* `_write_heartbeat`, so a slow/hanging `get_ltp` inside the comparison window could delay heartbeat freshness — a real (if narrow) production effect for something meant to be a pure side-channel. Fixed: reordered so `_write_heartbeat` runs first, diag call moved after.
- **WARNING**: the original tests covered only one clearly-inside (15:25) and one clearly-outside (11:00) time, leaving the inclusive `_PNL_DIAG_WINDOW_START`/`_MARKET_CLOSE` boundaries (15:20, 15:30) and the just-outside minutes (15:19, 15:31) unasserted — exactly where off-by-one errors hide. Fixed: added `test_live_pnl_diag_window_boundaries` (parametrized, 4 cases).
- **INFO**: mocking `monitor._tracker` post-construction (rather than mocking broker/store) verified as a reasonable unit-test strategy — the real `PaperTracker(store, broker)` wiring still runs in `__init__` via `_make_monitor`, no integration gap hidden. No action needed.
Decimal correctness (`str(unrealized)` etc., no float leakage) and the `PaperTracker(store, broker)`/`BrokerClient`-satisfies-`MarketDataProvider` wiring both verified clean.

**Next step:** after the next trading day, grep `logs/monitor_daemon.log` for `strategy_monitor.live_pnl_diag` (per strategy, 15:20-15:30 entries) and `logs/paper_snapshot.log` for `Recorded paper NAV snapshot` (same day), diff the last live reading against the EOD figure for every strategy. If a real gap shows up beyond what a few minutes of market movement could plausibly explain, escalate to a proper BUG-0XX with root-cause investigation; if not, remove this diagnostic (same 2026-07-24-style cleanup as BUG-018's temp logs, timeline TBD based on how many days of data are needed).

**Committed:** SHA `f7177b6`.

**Related:** BUG-018 (the specific case that prompted this generalisation).

---

## BUG-020 — `IronCondorV2` profit target re-scopes to the surviving legs' credit after any partial close, instead of the original 4-leg basket credit

| Field | Value |
|---|---|
| Severity | **HIGH** — financial-logic defect, directly affects when real capital would be closed under live trading; makes the 70% profit target fire early (against a smaller, post-partial-close credit base) rather than against the condor's actual entry economics. |
| Status | 🔴 Open — Phase 1 (persistence layer) landed 2026-08-04, SHA `285a8fa`; Phase 2 (V2 entry-path wiring) landed 2026-08-04, SHA pending — see task.md B020.7 for the entry-path discovery that changed this phase's plan (`IronCondorV2.enter()` is dead code in production; wired into `paper_ic_entry_v2.py::run()` instead); profit-target branch still reads the old recomputed value until Phase 3 |
| Discovered | 2026-08-04, user question about why `paper_ic_nifty_v2_monthly` closed with a "70% profit target" label alongside a negative lifetime Net P&L |
| Location | `src/strategy/ic_nifty_v2.py::_compute_combined_pnl` (line 2031), consumed by `check_signals`'s Priority 4 profit-target branch (line 1266) |

**Symptom:** `paper_ic_nifty_v2_monthly` closed on 2026-08-04 09:24:11 (`ic_nifty_v2.profit_target_close`, `captured_fraction=0.70`) on what was, by then, only the surviving put spread (`short_put`/`long_put_hedge`) — the call spread had already been force-closed the prior day (2026-08-03 09:15:30, `DELTA_STOP` → `CLOSE_CALL_SPREAD`, after a roll attempt failed the wing-liquidity floor). The reported 70% capture was computed against `entry_credit_pts=98.375`, which is the *put spread's own* entry credit, not the original 4-leg entry credit of 163.850 recorded at basket entry (07-31).

**Root cause:** `_compute_combined_pnl` builds `entry_credit` by summing `avg_sell_price`/`avg_cost` over whatever positions are passed in as `ic_positions` — which is filtered to currently-open legs only. There is no persisted field carrying the original 4-leg entry credit forward; once a partial close (`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD`) removes legs from `ic_positions`, every subsequent `check_signals` tick silently recomputes `entry_credit` from the smaller remaining subset. The 70% profit-target threshold (`_PROFIT_TARGET_RETENTION`) is then applied against that shrunk denominator.

**Contradicts documented design:** `docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md` defines `entry_credit` as the original combined 4-leg credit (line 80: "current combined mark (cost to close all 4 legs)"; line 301-303's state-field table; line 969's `captured_fraction` formula) and names a dedicated field, `original_entry_credit`, meant to persist this across the position's lifecycle. That field does not exist anywhere in `ic_nifty_v2.py`, `src/paper/models.py`, or `src/paper/store.py` — it was specified in the council decision but never implemented.

**Practical effect:** any partial close (delta-stop, failed roll, profit-lock wing contraction) makes the profit target easier to hit than intended, because it's chasing a smaller basket. The strategy's lifetime realized P&L can be negative (as it was here, driven by the earlier call-side delta-stop loss) even while a late-cycle "profit target" fires and reports a superficially healthy 70% capture — the two numbers are not contradictory once you know the scoping, but the current behavior deviates from the council-specified design.

**Suggested fix (not yet implemented):** persist `original_entry_credit` (4-leg, captured atomically at entry alongside the existing `PaperTrade` rows) and reference it in the profit-target branch instead of recomputing from `ic_positions`. Same defect present in `IronCondorV1` — see BUG-021.

**Fix in progress, phased per `docs/bugs/task.md`:** decision made 2026-08-04 (direct-operator override, not a full council session — Option 1: persist at entry, not reconstruct from history). Phase 1 (`PaperStore.set_original_entry_credit`/`get_original_entry_credit`, new `paper_strategies.original_entry_credit` column) committed 2026-08-04, SHA `285a8fa`. Phases 2 (wire `IronCondorV2.enter()` to populate it) and 3 (consume it in the profit-target branch, the actual symptom fix) not yet done.

**Related:** BUG-021 (identical defect in `IronCondorV1`), BUG-018 (same file, prior `_parse_expiry` defect), BUG-012 (same file, config mis-binding).

---

## BUG-021 — `IronCondorV1` has the same partial-close entry-credit re-scoping defect as `IronCondorV2` (BUG-020)

| Field | Value |
|---|---|
| Severity | **HIGH** — same class as BUG-020; not yet observed in a live close (no partial close has fired for `paper_ic_nifty_v1_weekly` in the logs sampled), but the code path is provably present and will trigger under the same conditions. |
| Status | 🔴 Open |
| Discovered | 2026-08-04, audit follow-up after BUG-020, per user request to check V1 |
| Location | `src/strategy/ic_nifty_v1.py::_compute_combined_pnl` (line 907), consumed by `check_signals`'s PROFIT_TARGET/LOSS_STOP branch (line 302) |

**Symptom (not yet reproduced live, confirmed by code inspection):** `ic_nifty_v1.py`'s `check_signals` calls the identical `_compute_combined_pnl` pattern as V2 — `entry_credit` is summed over `ic_positions`, which is filtered to `net_qty != 0` only (line 172-174), with no persisted original-basket credit field. `IronCondorV1` explicitly supports partial closes: `_ALLOWED_ACTIONS` includes `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` (line 72), and a single-leg `DELTA_STOP` can auto-select a spread-specific close (line 739: `action_type = "CLOSE_CALL_SPREAD" if leg_role == "short_call" else "CLOSE_PUT_SPREAD"`). If any such partial close executes, every subsequent tick's `PROFIT_TARGET`/`LOSS_STOP` evaluation (line 315-359) will compute `pct = combined_mark / entry_credit` against the surviving legs' credit only, not the original condor's — same root cause and same practical effect as BUG-020.

**Root cause:** identical to BUG-020 — no `original_entry_credit` field persisted at entry; `_compute_combined_pnl` reconstructs `entry_credit` from whatever's currently open.

**Suggested fix:** same as BUG-020 — persist `original_entry_credit` at entry, reference it in both files' profit-target/loss-stop branches instead of recomputing. Given both strategies share the defect, the fix should probably land as one shared helper/field rather than two parallel patches, to avoid the two files drifting again.

**Not yet fixed** — flagging in this registry per user request.

**Related:** BUG-020 (identical defect in `IronCondorV2`, discovered first).

---

## BUG-022 — Delta-stop wing-roll failure drops straight to a naked single-side partial close (`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD`) instead of searching narrower wing widths first; affects both `IronCondorV1` and `IronCondorV2`

| Field | Value |
|---|---|
| Severity | **HIGH** — financial-logic/risk-management defect. Not a computation error like BUG-020/021; a structural gap where a single failed liquidity check on one candidate strike causes the strategy to give up defined-risk structure entirely on that side, rather than trying other candidates or forcing a full exit. |
| Status | 🔴 Open — design agreed with user (2026-08-04), not yet implemented; scoped for a council checkpoint before coding (see below) |
| Discovered | 2026-08-04, user question "how only CE legs got closed, IC should always have 4 legs" — follow-up to BUG-020 investigation |
| Location | `src/strategy/ic_nifty_v2.py` (`roll_wing_attempt`/`entry_skip_wing_floor_miss`/`roll_guard_failed`/`delta_stop` sequence, ~line 1051-1680; `apply_action`'s `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` branch, line 1790-1793); `src/strategy/ic_nifty_v1.py` (`_select_wing_roll_target`, line 766; `_auto_select_action` Priority 5, line 736-762) |

**Symptom (confirmed live, V2):** 2026-08-03 09:15:30 (trace `01d74268`), `paper_ic_nifty_v2_monthly`'s short call delta breached `roll_trigger_delta` (0.3726). `roll_wing_attempt` tried one replacement long-call candidate; it failed the wing-floor liquidity/premium check (`entry_skip_wing_floor_miss`, `floor_value=0.05`, `actual_value=1.487`). On that single failure, the code went straight to `roll_guard_failed` → `delta_stop` → `CLOSE_CALL_SPREAD`, closing `short_call`+`long_call_hedge` only (`151.95`/`48.20`) and leaving `short_put`+`long_put_hedge` open. No re-hedge or re-entry logic exists anywhere in the file to reopen the call side afterward (confirmed — `DECISIONS.md`'s IC-CLOSE-2 note explicitly defers replacement-leg logic for `ROLL_WING`/`PROFIT_LOCK_ZONE2`, and `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` don't attempt one at all). From that tick until the full close on 08-04, the "iron condor" was structurally a naked-ish 2-leg put credit spread.

**Root cause:** the roll-attempt logic only ever evaluates a single candidate replacement strike per tick. If that one candidate fails the wing-floor guard, the code has exactly two branches: `ROLL_WING` (succeed) or `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` (give up on that side only). There is no intermediate step that tries progressively narrower candidate widths before conceding, and no path that escalates to `CLOSE_FULL` (exit both sides) instead of a single-side partial close.

**Same defect confirmed in `IronCondorV1`:** `_auto_select_action`'s Priority 5 (line 736-762) has the identical two-branch shape — `ROLL_WING` if `_select_wing_roll_target` finds a candidate, else `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` on the breached side only. `_select_wing_roll_target` (line 766) was not fully read for whether it applies the same wing-floor liquidity guard V2 does — needs confirming before implementation, since V1's roll-acceptance criteria may currently be looser (accepting more marginal candidates) rather than stricter.

**Existing reviewed precedent for the correct pattern:** this codebase already has a "search a narrower structure against a floor guarantee, fall back to `CLOSE_FULL` if nothing qualifies" mechanism — `IronCondorV2`'s Zone 2 profit-lock wing contraction (`docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md`, floor inequality `max(W_put, W_call) + D_cum + D_lock + K ≤ 0.75 × C₀`, "if the inequality cannot be satisfied at liquid strikes, CLOSE_FULL executes automatically — no human decision point"). That logic is currently only wired to the *voluntary* profit-lock path, not the *involuntary* delta-stop roll path this bug covers.

**Agreed design (user + Claude discussion, 2026-08-04, not yet council-ratified):** on delta-stop roll failure, before falling back to a single-side close:
1. Search progressively narrower long-strike candidates (walking the hedge leg toward the short strike) down to a configured minimum width floor — not all the way to the short strike itself, which would collapse the hedge to zero width (a naked short with extra transaction cost, not a defined-risk structure).
2. At each candidate width, check both the existing liquidity/premium floor AND the same floor-guarantee inequality already used by Zone 2 profit-lock (reused, not reinvented).
3. Only if no candidate across the full search range clears both checks, escalate to `CLOSE_FULL` (exit both sides) — never fall through to a naked single-side `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` as the final state.
4. Applies to both `IronCondorV1` and `IronCondorV2`; ideally implemented as one shared roll-search helper rather than two parallel implementations, to avoid the drift already seen between the two files' wing-floor logic.

**Open parameters requiring a decision before implementation:** minimum wing-width floor (points or ₹ debit terms), maximum number of candidate strikes to try per tick, whether V1 and V2 share one helper or keep separate (mirroring) implementations, and whether V1's `_select_wing_roll_target` needs its own floor-guarantee check added first (currently unconfirmed).

**Not yet fixed** — per `CLAUDE.md` Step 2b, this is a load-bearing, hard-to-reverse risk-management decision with multiple defensible parameter choices spanning strategy design and execution mechanics; recommend a council checkpoint (or explicit direct-operator override, per the precedent already used elsewhere in `DECISIONS.md`) before implementation, given it changes live risk exposure behavior for both IC strategies.

**Related:** BUG-020, BUG-021 (same investigation thread, same two files, discovered same session — entry-credit scoping vs. this structural roll/close gap are two distinct defects, not duplicates).

---
