# Data Architecture Domain

You are advising on data storage, pipeline design, or API integration for NiftyShield.

## Stack

- Python 3.10+, asyncio + aiohttp for all I/O. ProcessPoolExecutor for CPU-bound work.
- Never mix asyncio with blocking calls in the hot path.
- All public functions: type hints + Google-style docstrings. Dataclasses or Pydantic for
  all API request/response shapes. Monetary values: always Decimal (never float).

## Storage Layer

- **SQLite** (WAL mode, shared via src/db.py): portfolio state, trade ledger, snapshots.
  Monetary fields stored as TEXT to preserve Decimal precision. Read back via Decimal(row["col"]).
- **Parquet** (pyarrow, partitioned by year/month): historical OHLCV time-series under data/offline/.
  Partition scheme: {year}/{month}/ for EOD, {year}/{month}/{day}/ for intraday — DuckDB-compatible.
- **data/** directory is gitignored (live SQLite DB). Config/YAML is under src/ (version-controlled).

## Live Data Sources

| Source | Token type | What it provides |
|---|---|---|
| Upstox Analytics Token | Long-lived | Option chain + Greeks, OHLC, LTP (zero marginal cost) |
| Upstox OAuth token | Daily refresh | Positions, holdings, margins (not yet wired) |
| Nuvama APIConnect | Session-persistent | Bonds/holdings, options P&L, intraday positions |
| Dhan REST API | 24h manual refresh | Equity ETF holdings (free tier) |
| AMFI flat file | No auth | MF NAV (semicolon-delimited, fetched at 3:45 PM cron) |

## Broker Abstraction (Non-Negotiable)

All modules depend on `BrokerClient` protocol (`src/client/protocol.py`) — never on
concrete implementations. Constructor injection only. `factory.py` is the sole composition
root (the only file that imports `UpstoxLiveClient` or `MockBrokerClient` directly).

## Test Constraints

- No network in unit tests. MockBrokerClient for all broker-dependent code.
- Use `tmp_path` (pytest) for SQLite tests — not `:memory:` (connection opens/closes per call).
- Sandbox tests opt-in via `@pytest.mark.sandbox`. CI runs offline tests only.

## Settled Architectural Decisions — Do Not Re-Litigate

| Decision | Outcome | Date |
|---|---|---|
| Time-series database | Parquet + SQLite (TimescaleDB deferred indefinitely) | 2026-04-27 |
| Monetary precision | Decimal-as-TEXT in SQLite | original |
| Broker abstraction | BrokerClient protocol + DI, factory.py composition root | original |
| MF NAV source | AMFI official flat file (not mfapi.in, not Upstox) | original |
| IV reconstruction model | Black '76 with Nifty Futures forward | 2026-04-30 |
| Slippage model | Absolute INR, VIX-regime-aware, OI multiplier | 2026-04-30 |
| DhanHQ Data API | Rejected (1-min data only 5 days deep) | 2026-04-27 |
| TrueData | Rejected (6-month intraday depth, no historical Greeks) | 2026-04-27 |

## Error Handling

Custom exception hierarchy rooted at `BrokerError` (src/client/exceptions.py).
Retryable: RateLimitError, DataFetchError. Terminal (no retry): OrderRejectedError,
InstrumentNotFoundError. Non-fatal blocks (MF, Dhan, Nuvama fetches) wrapped in
try/except in cron scripts — never abort the main snapshot on a peripheral failure.
