# NiftyShield — Project Instructions (Claude Desktop)

> Paste this into Claude Desktop → Project → Instructions.
> Trim this further as CONTEXT.md/DECISIONS.md/REFERENCES.md absorb more detail.
> Last updated: 2026-04-12

---

## Project Overview

Automated trading system built on the Upstox Developer API for:
- Options selling on NiftyBees ETF (pledged for margin)
- Delta-neutral adjustments based on real-time Greeks
- Backtesting against expired option contract data
- Portfolio monitoring integrated with the FD-OD capital structure

Full architecture state in `CONTEXT.md`. Architecture decisions in `DECISIONS.md`. Instrument keys and AMFI codes in `REFERENCES.md`. Open work in `TODOS.md`.

---

## Pre-Task Protocol

Before writing any code:
1. Read `CONTEXT.md` — authoritative codebase state. State `CONTEXT.md ✓` in first response.
2. If prompt does not name specific files, ask before starting. One clarifying question beats building the wrong thing.
3. State plan in one sentence → which files change → tests required. If >2 files, wait for go-ahead.
4. Tests are mandatory. Every public function needs one happy-path + one error/edge-case test. No network in tests.
5. After implementation, update `CONTEXT.md` (module tree), `DECISIONS.md` (new decisions), `TODOS.md` (session log).

Additional files to read when relevant:
- Architecture changes → `DECISIONS.md`
- Instrument keys / AMFI codes → `REFERENCES.md`
- New feature work → `TODOS.md` + `PLANNER.md`
- Working in a `src/` module → that module's `CLAUDE.md` loads automatically

---

## Python Standards

- Python 3.10+, type hints on all function signatures, Google-style docstrings on all public functions/classes.
- Functions 10–20 lines typical. Split only when it improves clarity, not by rule.
- `dataclasses` or `Pydantic` for all API request/response shapes.
- Vectorized ops (NumPy/Pandas) for historical analysis. Generators for large dataset iteration.

## Async Model

- `asyncio` + `aiohttp` for all I/O-bound operations.
- Never mix asyncio with blocking calls in the hot path.
- CPU-bound work (backtesting, Greeks) → `ProcessPoolExecutor` dispatched from the event loop.
- All coroutines must have explicit timeout handling.

## Data Layer

- Monetary fields: always `Decimal`, stored as TEXT in SQLite. Never float. Read back with `Decimal(row["col"])`.
- Timestamps: stored as UTC, converted to IST at display layer only.
- Historical candles: Parquet, partitioned by instrument + date.
- Config + credentials: TOML/YAML + env vars.

## BrokerClient Protocol

All modules depend on `BrokerClient` protocol (`src/client/protocol.py`), never on concrete implementations. Constructor injection only. `factory.py` is the sole composition root — the only file in `src/` that imports `UpstoxLiveClient` or `MockBrokerClient` directly.

Default test mode is offline (`MockBrokerClient`). Sandbox tests are opt-in (`@pytest.mark.sandbox`). CI runs offline tests only.

## Error Handling

Custom exception hierarchy rooted at `BrokerError` — see `src/client/exceptions.py`. Retryable: `RateLimitError`, `DataFetchError`. Terminal (do not retry): `OrderRejectedError`, `InstrumentNotFoundError`. All blocked API methods raise `NotImplementedError` with explanatory message.

## Logging

Structured JSON in prod. Every API call logs: timestamp, endpoint, request_id, latency_ms, status_code. Every order logs: order_id, instrument, action, qty, price, status. Debug: `UPSTOX_DEBUG=1`.

## Security

Never commit API keys, secrets, or tokens. Credentials in `.env` (local) or secrets manager (prod). `.env` in `.gitignore` always.

---

## Commit Message Format

```
<type>(<scope>): <what changed, imperative mood, ≤60 chars>

Why: <one sentence — reason or problem solved>
What:
- <file path>: <one-line description>
Ref: <constraint from CONTEXT.md, or "none">
```

Types: `feat` / `fix` / `refactor` / `test` / `chore` / `docs`
Scope: folder name under `src/` or `scripts/`

---

## Project Structure (abbreviated)

```
src/
├── auth/              # OAuth (Upstox) + Nuvama session auth
├── client/            # BrokerClient protocol + 3 implementations + factory
├── portfolio/         # Models, store, tracker, strategy definitions
├── mf/                # MF transaction ledger, AMFI NAV fetcher, tracker
├── instruments/       # Offline BOD instrument lookup
├── notifications/     # Telegram notifier (non-fatal, HTML parse_mode)
└── db.py              # Shared SQLite context manager
scripts/               # daily_snapshot.py, seed_*.py, record_trade.py
tests/unit/            # 400 offline tests — run with: python -m pytest tests/unit/
data/portfolio/        # portfolio.sqlite (live DB)
```

Full tree with file-level descriptions in `CONTEXT.md`.

---

## Environment Variables (key ones)

| Variable | Description |
|---|---|
| `UPSTOX_ANALYTICS_TOKEN` | Long-lived Analytics Token for market data |
| `UPSTOX_ACCESS_TOKEN` | Daily OAuth token (not yet wired for portfolio reads) |
| `UPSTOX_SANDBOX_TOKEN` | Sandbox access token |
| `UPSTOX_ENV` | `prod` / `sandbox` / `test` — selects client implementation |
| `UPSTOX_DEBUG` | `1` = verbose request/response logging |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token for cron notifications |
| `TELEGRAM_CHAT_ID` | Telegram chat ID |
| `NUVAMA_SETTINGS_FILE` | Path to Nuvama APIConnect session file |

Full list with examples in `.env.example`.
