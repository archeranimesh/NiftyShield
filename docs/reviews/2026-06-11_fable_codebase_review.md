# Codebase Review — 2026-06-11 (Claude Fable)

Scope: `src/` only. Excludes all issues tracked in `docs/plan/council-refactor/tasks.md`
(BUG-1…7, DBI-1…3, SIG-1, SIG-2, SM-1, SM-2, DAEMON-S1, LOG-1, RPT-*, OPS-*).
Format: `SEVERITY | file:line | description | fix`.

---

## CRITICAL

CRITICAL | src/strategy/overlay_closer.py:427-446 | `OverlayCloser._resolve_mid_price` returns `Decimal("0")` when the strike is absent from the chain, the key regex fails, or any exception fires (silently swallowed by `except Exception: pass` at 441-442). Every overlay close routed through `OverlayCloser` (collar close, put monetize, and the AUTO-1 EOD auto-close path) records a zero-price fill, corrupting realized P&L — exact failure mode of the 2026-06-09 incident. SIG-1 fixes only the *separate* copy in `src/strategy/executor.py`; this one is untracked. | Raise `ValueError` when no price resolves (mirror SIG-1 spec); delete the `except Exception: pass`; extract one shared price resolver used by both executor and closer.

## ERROR

ERROR | src/paper/models.py:223-231 + src/paper/store.py:142-149,1029-1040 | Monetary fields on `PaperExitEvent` (`ltp`, `mid`, `bid`, `ask`, `entry_price`, `threshold_value`) are `float`, persisted as SQLite `REAL` — violates the Decimal-as-TEXT invariant on the table that drives exit decisions and dual-signal audits. Blocks SIG-2's exit_signals Decimal conversion end-to-end (engine will go Decimal, storage stays float). | Change model fields to `Decimal | None`, columns to TEXT via idempotent migration (combine with BUG-4/BUG-6 migration), read back with `Decimal(row[...])`.

ERROR | src/instruments/lookup.py:492-493 | `search_api` creates `aiohttp.ClientSession()` with no `ClientTimeout` and no `asyncio.wait_for` — violates the "all coroutines must have explicit timeout handling" rule; a stalled Upstox search hangs the caller for aiohttp's implicit 300 s default. | `aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))` (pattern already in `src/notifications/telegram.py:107`).

ERROR | src/notifications/telegram_gateway.py:129,216,239 | All three `ClientSession()` instantiations lack an explicit `ClientTimeout`. Worst case is `getUpdates` (239): server-side long-poll `timeout=30` with client default 300 s means a dead Telegram connection stalls the daemon poll loop ~5 min per call. Inconsistent with `telegram.py:107-108` which does this correctly. | Add `ClientTimeout(total=...)` per call site (`getUpdates` needs total > long-poll 30 s, e.g. 40 s; sends 10 s).

ERROR | src/client/upstox_market.py:123-131,148-155,179-185 | The primary market-data client emits zero structured logging on any HTTP call — no endpoint, latency_ms, status_code, or request_id. Direct violation of the project logging standard ("Every API call logs: timestamp, endpoint, request_id, latency_ms, status_code"); the daemon's chain fetches are invisible in logs, which is exactly what made the Jun-09 post-mortem slow. | Wrap the three `_session.get` calls with a `t0 = perf_counter()` + `logger.info("upstox.api_call", endpoint=..., status_code=resp.status_code, latency_ms=...)` helper.

ERROR | src/strategy/overlay_closer.py:459-460 | `_find_option_leg` ends in `except Exception: return None` — unlogged, no intent comment (REVIEW.md G5). A malformed strike or chain shape silently converts to "leg not found", which downstream becomes the zero-price path above. | Catch the specific expected exceptions (`InvalidOperation`, `KeyError`), log at WARNING, add intent comment if broad catch is truly required.

## WARNING

WARNING | src/client/upstox_market.py:212-231 | `_safe_decimal` coerces `None`/non-numeric Greeks to `Decimal("0")`. A strike with missing Greeks gets `delta=0`, which silently suppresses DELTA_BREACH (CSP ≥0.40) and DELTA_STOP (CC ≥0.55) evaluation — a stale-data day disables delta-based exits without an ACTION-visible trace. | Make Greeks `Decimal | None` on `OptionLeg` (or drop the leg) and have evaluators treat `None` as "cannot evaluate" → WARN, never as 0.

WARNING | src/strategy/reentry_mixin.py:93 | `load_vix_series` (pandas/Parquet disk read of 252+ days) runs synchronously inside `async _check_reentry`, blocking the event loop on the daemon's apply_action path. | `await asyncio.to_thread(load_vix_series, self._vix_data_dir)` (pattern already in `upstox_market.py:160-167`).

WARNING | src/strategy/reentry_mixin.py:107,123,156,172 | structlog event names are dynamic f-strings (`f"{self.strategy_name}.reentry_ivr_load_failed"`) — eager evaluation (G7) and, worse, per-strategy event names break log aggregation: you cannot grep one stable event across strategies. | Use constant event names (`"reentry.ivr_load_failed"`) with `strategy=self.strategy_name` as a bound field.

WARNING | src/strategy/csp_nifty_v1.py:143,236 + cc_overlay_v1.py:72,161,247 + pp_overlay_v1.py:87,167,250 + collar_overlay_v1.py:52,222 + ic_nifty_v1.py:111,238 + nifty_track_comparison_v1.py:94,190 + overlay_closer.py:99,164,267 | All DTE, days_held, and trade_date computations use `date.today()` — server-locale-dependent. On any UTC host (CI, future VPS) the trading date is wrong between 00:00 UTC and 05:30 IST, shifting DTE by one exactly when DTE ≤ 5/7 roll gates are evaluated. Works today only because the host is IST. | Add one `market_today() -> date` helper (IST-aware, `src/market_calendar/`) and replace all call sites.

WARNING | src/nuvama/store.py:532 | Purge cutoff computed as naive local `datetime.now() - timedelta(days=days)` compared against UTC-stored timestamps — retention window off by +5:30 on IST hosts and wrong by an arbitrary offset elsewhere. | Use `datetime.now(timezone.utc)` for the cutoff.

WARNING | src/strategy/monitor.py:168,203 | `self._notifier` is mistyped (gateway methods accessed via `# type: ignore[attr-defined]` ×2). This is the identical masking pattern that hid the DAEMON-S1 crash at line 204 — the ignores neutralize mypy on the daemon's most failure-prone seams. | Type the dependency as `TelegramGateway | None` (or a Protocol with `send_plain_message`/`send_approval_request`) and delete the ignores.

WARNING | src/instruments/strike_selector.py:12-25,87-89 | `_safe_float` silently defaults unparseable `ltp`/`bid`/`ask` to `0.0` — monetary floats in the strike-selection path, and zero-coercion is the same defect family as the Jun-09 flood. A bad chain row becomes a strike with ltp=0 rather than an excluded-with-WARN strike. | Return `None` on coercion failure, skip the entry with a WARN log; keep prices Decimal until ranking.

WARNING | src/client/mock_client.py:92,244 | Mock monetary surfaces are float (`set_margin(amount: float)`, `"entry_price": float(price)`), so tests written against the mock encode float-money expectations that diverge from the Decimal protocol contract. | Accept/emit `Decimal` in the mock; tests construct `Decimal` fixtures.

## INFO

INFO | src/config.py:209 | `assert self._cached_settings is not None` in src/ (G6 — stripped under `-O`). Type-narrowing only, unreachable-false, but the rule is absolute outside `tests/`. | Replace with `if self._cached_settings is None: raise RuntimeError(...)` or restructure to return the local directly.

INFO | src/strategy/reentry_mixin.py:141 | `datetime.utcnow()` — deprecated since 3.12 and returns a *naive* datetime into `event_time`, mixing naive/aware UTC in `paper_exit_events`. | `datetime.now(timezone.utc)`.

INFO | src/client/exceptions.py:23-48 | `RateLimitError`/`DataFetchError` are documented as retryable, but no retry mechanism exists anywhere in `src/` — the retryable/terminal taxonomy is currently aspirational; a 429 during a daemon tick just fails the tick. | Either add a small bounded-backoff retry at the `BrokerClient` boundary honoring the taxonomy, or note in `DECISIONS.md` that retry is deliberately deferred.

---

## Counts

| Severity | New findings |
|---|---|
| CRITICAL | 1 |
| ERROR | 5 |
| WARNING | 8 |
| INFO | 3 |
| **Total** | **17** |

Known issues encountered during the sweep and skipped (already in tasks.md): 6 —
exit_signals float comparisons (SIG-2), executor `_resolve_mid_price` stub + `_write_audit`
(SIG-1/RPT-0), `add_pending_approval` (DAEMON-S1), `delete_trade` predicate (DBI-1c),
`get_positions` cycle/entry_date/instrument_key defects (BUG-1/DBI-3), missing trace
correlation (LOG-1).

Clean areas verified: no `UpstoxLiveClient`/`MockBrokerClient` imports outside
`factory.py`; no mutable default arguments; no bare `except:`; no f-strings in stdlib
`logger.*` calls; no `get_logger(__name__)` in `scripts/`; `upstox_market` async wrappers
correctly use `asyncio.to_thread`; NAV/trade monetary persistence correctly uses
Decimal-as-TEXT; `Leg.pnl()` converts float input via `Decimal(str(...))`.
