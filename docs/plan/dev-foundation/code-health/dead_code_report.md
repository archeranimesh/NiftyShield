# Dead Code Scan Report — CH-2

> Generated: 2026-05-30
> Command: `vulture src/ scripts/ --min-confidence 60`
> Scope: all Python files under `src/` and `scripts/`

**Note:** vulture does not scan `tests/` — functions used only in tests appear as false positives.
This is a known limitation; see the False Positives section.

---

## Summary

| Category | Count |
|---|---|
| Safe to delete | 10 |
| Needs investigation | 13 |
| False positive | 47 |

---

## 1. Safe to Delete

These are clearly unused — assigned variables that are never read, or private helpers with no callers anywhere in the codebase (including `tests/`).

| File | Line | Finding | Confidence | Reason |
|---|---|---|---|---|
| `scripts/gamma_daily_watch.py` | 95 | variable `today_snaps` | 100% | Assigned, never read |
| `scripts/paper_3track_snapshot.py` | 313 | variable `u` | 100% | Unused unpacking variable |
| `scripts/paper_track_snapshot.py` | 74 | variable `u` | 100% | Unused unpacking variable |
| `src/client/protocol.py` | 183 | parameter `callback` in `on_tick` | 100% | Declared in signature, never accessed in body |
| `scripts/paper_3track_overlay_roll.py` | 108 | variable `new_expiry` | 60% | Assigned from return value, never used |
| `scripts/paper_csp_roll.py` | 76 | variable `new_expiry` | 60% | Assigned from return value, never used |
| `src/backtest/bhavcopy_ingest.py` | 39 | variable `settle_price` | 60% | Parsed from row dict, never used downstream |
| `src/mf/tracker.py` | 52 | variable `current_nav` | 60% | Assigned, overshadowed or never read |
| `src/paper/overlay_selector.py` | 38 | variable `fallback_reason` | 60% | Assigned, never used in fallback path |
| `src/paper/track_snapshot.py` | 51 | variable `proxy_delta_state` | 60% | Assigned, never passed anywhere |

**Action:** These can be deleted in a single clean-up commit without behavioural risk.
The unused variables likely originate from refactors where the variable was decoupled from its use site but the assignment was left behind.

---

## 2. Needs Investigation

These have no callers found in `src/` or `scripts/` but are not obviously dead — they may be intentional scaffolding, have been superseded, or require context to confirm.

### 2a — Private helpers with no callers (likely dead)

| File | Line | Finding | Notes |
|---|---|---|---|
| `scripts/daily_snapshot.py` | 62 | `_print_combined_summary` | No callers anywhere. Probably superseded by the composed Dhan+Nuvama summary path. Confirm before deleting. |
| `scripts/paper_3track_snapshot.py` | 185 | `_overlay_roles_for_track` | No callers. May have been extracted and then abandoned mid-refactor. |
| `scripts/paper_3track_snapshot.py` | 268 | `_print_summary_table` | No callers. Likely a formatting helper that was inlined elsewhere. |

### 2b — Public API with no production callers (store/utility methods)

These are public store methods or utility functions with no callers in `src/` or `scripts/`. They all have test coverage, which confirms they *work* but does not confirm they are *needed* at runtime.

| File | Line | Finding | Notes |
|---|---|---|---|
| `src/client/upstox_market.py` | 101 | `get_ohlc_sync` | Sync wrapper around async OHLC fetch. No async caller uses it. May have been written for a script context that was later made async. |
| `src/mf/store.py` | 89 | `insert_transaction` | Superseded by bulk insert? Confirm vs `upsert_nav_snapshots_bulk`. |
| `src/mf/store.py` | 252 | `upsert_nav_snapshots_bulk` | Only in store; not called from tracker or scripts. |
| `src/mf/store.py` | 364 | `get_latest_nav` | No callers in tracker or scripts. |
| `src/paper/store.py` | 426 | `get_latest_nav_snapshot` | No production callers found (tests only). |
| `src/portfolio/store.py` | 441 | `get_strategy_snapshots` | No callers in scripts or src. |
| `src/instruments/lookup.py` | 176 | `search_equity` | No callers in src or scripts. |
| `src/instruments/lookup.py` | 372 | `search_api` | No callers in src or scripts. |
| `src/intraday/market_store.py` | 84 | `get_latest` | No callers in intraday scripts. |

### 2c — Intentional scaffolding (do not delete yet)

These are flagged but are known planned work per `CONTEXT.md`:

| File | Lines | Finding | Notes |
|---|---|---|---|
| `src/gamma/store.py` | 232–538 | `GammaStore` + all methods | Scaffolding for `gamma_daily_watch.py` script not yet implemented. Keep — Phase A next. |
| `src/backtest/chain_reader.py` | 10–161 | `ChainReader` + all methods | Phase 1 scaffolding. Not wired until backtest engine is built. Keep. |

---

## 3. False Positives

Vulture does not understand the following patterns, producing false positives for all of them.

### 3a — Used only in `tests/` (vulture does not scan test directory)

| Symbol | File | Used in |
|---|---|---|
| `select_overlay_expiry` | `src/paper/overlay_selector.py` | `tests/unit/paper/test_overlay_selector.py` |
| `compute_annualised_overlay_cost` | `src/paper/metrics.py` | `tests/unit/paper/test_metrics.py` |
| `escape_mdv2` | `src/notifications/telegram.py` | `tests/unit/test_notifications.py` |
| `ingest_vix_from_csv` | `src/backtest/vix_ingest.py` | `tests/unit/backtest/test_vix_ingest.py` |
| `ingest_vix_from_api` | `src/backtest/vix_ingest.py` | `tests/unit/backtest/test_vix_ingest.py` |
| `load_options_ohlcv` | `src/backtest/bhavcopy_loader.py` | `tests/unit/backtest/test_bhavcopy_loader.py` |
| `parse_option_symbol` | `src/backtest/bhavcopy_ingest.py` | `tests/unit/backtest/test_bhavcopy_ingest.py` |
| `get_latest_heartbeat` | `src/portfolio/store.py` | `tests/unit/test_portfolio.py` |
| `get_latest_snapshot_date` | `src/portfolio/store.py` | `tests/unit/test_portfolio.py` |
| `get_prev_total_value` | `src/nuvama/store.py` | `tests/unit/nuvama/test_store.py` |
| `get_leg_snapshot` | `src/paper/store.py` | `tests/unit/paper/` |
| `MockNuvamaClient` | `src/nuvama/mock_client.py` | `tests/unit/nuvama/` |
| Mock helpers: `set_price`, `set_margin`, `simulate_error`, `reset` | `src/client/mock_client.py` | `tests/unit/test_client.py` |

### 3b — Pydantic validators and config (called by framework, not directly)

Pydantic `model_config`, `@validator`, `@field_validator`, and `@model_validator` decorated methods are invoked by the Pydantic metaclass, not by explicit call sites. Vulture cannot see this dispatch.

| File | Symbols |
|---|---|
| `src/models/mf.py` | `model_config`, `nav_is_finite` |
| `src/models/portfolio.py` | `model_config`, `price_must_be_positive`, `avg_price_must_be_non_negative`, `validate_leg_invariants` |
| `src/paper/models.py` | `model_config`, `strategy_name_must_have_paper_prefix`, `price_must_be_positive` |

### 3c — Protocol/ABC implementations (structural subtyping)

`BrokerClient` and related protocols use structural subtyping. Implementations satisfy the protocol without inheritance, so call sites type-check against the protocol, not the concrete class. Vulture sees the methods as unbound.

| File | Symbols |
|---|---|
| `src/client/protocol.py` | `OrderExecutor`, `PortfolioReader`, `MarketStream`, all their methods |
| `src/client/mock_client.py` | `get_margins`, `get_historical_candles`, `get_expired_option_contracts` |
| `src/client/upstox_live.py` | `get_historical_candles`, `get_expired_option_contracts`, `get_margins` |

### 3d — stdlib override methods (called by framework)

| File | Symbols | Caller |
|---|---|---|
| `src/auth/login.py` | `do_GET`, `log_message` | `http.server.BaseHTTPRequestHandler` |

### 3e — Exception hierarchy (raised in code, `except`-caught by type)

`AuthenticationError`, `RateLimitError`, `InstrumentNotFoundError` are all raised in `src/client/` and caught by callers. Vulture misses `raise ExceptionClass(...)` as a "use".

### 3f — SQLite `row_factory` attribute assignments

`connection.row_factory = sqlite3.Row` is a Python attribute assignment on the connection object. Vulture flags the attribute name as unused because it sees no read of `row_factory` on a Python object it tracks.

| File | Line |
|---|---|
| `src/db.py` | 39 |
| `scripts/migrate_strike_to_text.py` | 64 |

### 3g — Enum members and dataclass fields (accessed via instance, not by name)

| File | Symbols | Reason |
|---|---|---|
| `src/models/mf.py` | `REDEMPTION` | Enum member; accessed as `TransactionType.REDEMPTION` in conditionals |
| `src/models/portfolio.py` | `MIS` | Enum member; used in order type filtering |
| `src/models/portfolio.py` | `total_lots` | Property; used in summary formatting |
| `src/models/portfolio.py` | `leg_pnl` | Method; called in reporting paths |
| `src/risk/models.py` | `niftybees_delta_lots`, `as_of` | Frozen dataclass fields; accessed via dot notation |
| `src/nuvama/models.py` | `company_name`, `hair_cut` | Model fields; populated from API JSON |
| `src/dhan/models.py` | `position_type` | Model field; parsed from Dhan API |

### 3h — `__main__` block caller

| File | Symbol | Notes |
|---|---|---|
| `src/dhan/reader.py` | `fetch_dhan_portfolio` | Called inside `if __name__ == "__main__":` block in the same file |

### 3i — `validate_strategy_spec.py` property

| File | Symbol | Notes |
|---|---|---|
| `scripts/validate_strategy_spec.py` | `passed` (property) | Accessed as `.passed` on the result object at the call site — vulture misses property reads |

---

## Whitelist Candidates

If a `vulture_whitelist.py` is created at repo root, the following should be added to silence
confirmed false positives on future runs:

```python
# vulture_whitelist.py
# Protocol/ABC methods — structural subtyping, not explicitly called
from src.client.protocol import OrderExecutor, PortfolioReader, MarketStream
OrderExecutor.place_order
PortfolioReader.get_margins
PortfolioReader.get_historical_candles
PortfolioReader.get_expired_option_contracts
MarketStream.subscribe
MarketStream.unsubscribe
MarketStream.on_tick
MarketStream.disconnect

# HTTP server overrides
from src.auth.login import _OAuthCallbackHandler
_OAuthCallbackHandler.do_GET
_OAuthCallbackHandler.log_message

# Exception hierarchy
from src.client.exceptions import AuthenticationError, RateLimitError, InstrumentNotFoundError
AuthenticationError
RateLimitError
InstrumentNotFoundError

# Pydantic framework calls (validators, config)
# Add model validator method names if needed per-module

# Mock client test helpers
from src.client.mock_client import MockBrokerClient
MockBrokerClient.set_price
MockBrokerClient.set_margin
MockBrokerClient.simulate_error
MockBrokerClient.reset
```

**Do not create this file in CH-2.** Whitelist creation is a follow-up action after confirming
the "Needs Investigation" items.

---

## Recommended Follow-up Actions

1. **Immediate (low risk):** Delete the 10 "Safe to Delete" items in a single commit.
2. **Verify then delete:** Audit the 3 private helpers in §2a — confirm not called via `getattr` or dynamic dispatch. Then delete.
3. **Store API audit (§2b):** Cross-check store methods against the script that owns them (`mf/tracker.py` owns `mf/store.py`, etc.). Methods with test coverage but no production caller are candidates for deletion if the script logic is genuinely complete.
4. **Scaffolding (§2c):** Leave `GammaStore` and `ChainReader` intact — they are Phase 1 targets.
5. **Whitelist:** Create `vulture_whitelist.py` after §2 audit is done, then add `vulture` to the `Makefile` `dead-code` target.
