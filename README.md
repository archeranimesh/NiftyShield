# NiftyShield

**Options selling automation on NiftyBees ETF, powered by Upstox API.**

NiftyShield is a systematic options trading engine built on a leveraged capital structure — FD-backed Overdraft facility funding NiftyBees ETF purchases (pledged for margin) and ILTS allocation, generating two parallel income streams from one pool of borrowed capital.

---

## Strategy Overview

```
┌─────────────────────────────────────────────────────┐
│                  ₹50L FD Ladder                     │
│          (5 × ₹10L, staggered tenures)              │
├──────────────────┬──────────────────────────────────┤
│    OD Facility   │   FD Rate + 2% borrowing cost    │
├──────────┬───────┴───────┬──────────────────────────┤
│  ₹17L    │     ₹17L      │        ₹8.5L             │
│ NiftyBees│     ILTS       │   Margin Call Buffer     │
│  (ETF)   │  (Long-term    │                          │
│          │   Gilt funds)  │                          │
├──────────┴───────────────┴──────────────────────────┤
│          NiftyBees pledged for margin                │
│      → Options selling (premium income)              │
│      → Delta-neutral adjustments                     │
└─────────────────────────────────────────────────────┘
```

**Income streams:** ETF capital appreciation + options premium collection + ILTS coupon returns, all funded by low-cost OD borrowing against FDs.

---

## Architecture

```
┌──────────────────────────────────────┐
│          BrokerClient Protocol       │  ← All modules depend on this
├──────────┬───────────┬───────────────┤
│ Upstox   │  Sandbox  │    Mock       │  ← Swappable implementations
│  Live    │  Client   │   Client      │
├──────────┴───────────┴───────────────┤
│                                      │
│  ┌──────────┐  ┌──────────────────┐  │
│  │ Strategy │  │  Risk Manager    │  │
│  │  Engine  │  │  (margin, delta) │  │
│  └────┬─────┘  └────────┬─────────┘  │
│       │                 │            │
│  ┌────┴─────────────────┴─────────┐  │
│  │      Execution Engine          │  │
│  │  (orders, GTT, adjustments)    │  │
│  └────────────────────────────────┘  │
│                                      │
│  ┌────────────────────────────────┐  │
│  │        Data Layer              │  │
│  │  Historical · Option Chain ·   │  │
│  │  Expired Instruments · Stream  │  │
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
```

**Key design decision:** Every module depends on the `BrokerClient` protocol, never on Upstox directly. This enables fully offline development, testing, and backtesting without any API connection.

---

## Project Structure

```
NiftyShield/
├── src/
│   ├── auth/              # OAuth flow, token management
│   ├── client/
│   │   ├── protocol.py    # BrokerClient & MarketStream protocols
│   │   ├── upstox_live.py # Live Upstox implementation
│   │   ├── upstox_sandbox.py
│   │   ├── mock_client.py # Stateful offline mock
│   │   └── factory.py     # Client injection
│   ├── models/            # Pydantic models for API shapes
│   ├── strategy/          # Signal generation
│   ├── execution/         # Order management
│   ├── data/              # Historical data, expired instruments
│   ├── streaming/         # Websocket feeds + replay
│   ├── backtest/          # Backtesting engine
│   ├── risk/              # Margin, position sizing, delta
│   └── utils/             # Logging, config, helpers
├── tests/
│   ├── unit/              # Offline tests (default)
│   ├── integration/       # Sandbox tests (opt-in)
│   └── fixtures/          # Recorded API responses + tick streams
├── data/
│   ├── offline/           # Bootstrap'd historical data
│   └── bootstrap.py       # One-time data fetch
├── config/                # Environment configs (dev/stage/prod)
├── .env.example
├── requirements.txt
└── README.md
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- An active [Upstox](https://upstox.com) trading account
- API credentials from [Upstox Developer Portal](https://account.upstox.com/developer/apps)

### Setup

```bash
git clone https://github.com/archeranimesh/NiftyShield.git
cd NiftyShield
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

Edit `.env` with your Upstox API Key and Secret.

### Login

```bash
python -m src.auth.login
```

Opens your browser for Upstox OAuth login. Access token is saved to `.env` automatically. Tokens expire daily — re-run each morning.

### Verify

```bash
python -m src.auth.verify
```

Confirms Upstox API connectivity by fetching your account profile.

### Nuvama Login (one-time)

NiftyShield tracks your Nuvama bond and gold bond holdings for margin and portfolio visibility. Nuvama uses a `request_id` redirect flow — run this once and the session persists indefinitely in a local settings file.

**Prerequisites:** Add these to your `.env`:

```
NUVAMA_API_KEY=your_api_key
NUVAMA_API_SECRET=your_api_secret
NUVAMA_SETTINGS_FILE=data/nuvama/settings.json
```

**Login:**

```bash
python -m src.auth.nuvama_login
```

Opens your browser to the Nuvama login page. After authenticating, you'll be redirected to a URL containing a `request_id` token. Paste the full redirect URL (or just the token) at the prompt. The session is saved to `NUVAMA_SETTINGS_FILE` — no daily re-auth required.

**Verify:**

```bash
python -m src.auth.nuvama_verify
```

Loads the saved session and fetches live holdings. Expected output:

```
✓ Nuvama session active — 6 holding(s) found.
  Efsl-10%-29-4-34-ncd                      qty=     700  ltp=1014
  Goi  Loan  8.28%  2027                    qty=    2000  ltp=152
  Efsl-9.20%-21-7-26-ncd                    qty=     500  ltp=998.99
  Efsl-9.67%-20-1-28-ncd                    qty=    1200  ltp=997.2
  Efsl-9.67%-29-4-29-ncd                    qty=     700  ltp=998.8
  2.50%goldbonds2031sr-iii                  qty=      50  ltp=14982
```

Unlike Upstox, Nuvama does not require daily re-auth — the session token in `settings.json` survives until explicitly invalidated.

### Dhan Login (daily)

NiftyShield monitors your Dhan portfolio for F&O P&L tracking and after-market holdings review. Dhan uses a manual 24-hour access token generated from their web portal.

**Prerequisites:** Add your Client ID to `.env`:

```
DHAN_CLIENT_ID=<your-client-id>
```

Find it: login to [web.dhan.co](https://web.dhan.co) → Profile icon (top-right) → Client ID is displayed.

**Login:**

```bash
python -m src.auth.dhan_login
```

Opens your browser to Dhan web portal. Navigate to Profile → "Access DhanHQ APIs" → "Generate Access Token". Fill in App Name (e.g. `NiftyShield`), keep Token validity at 24h. Copy the generated token and paste it at the prompt.

**Verify:**

```bash
python -m src.auth.dhan_verify
```

Confirms Dhan connectivity by fetching your profile and holdings. Expected output:

```
✓ Dhan session active — profile: JOHN DOE (1000000001)
✓ 5 holding(s) found.
  HDFC                                     qty=    1000  avg=2655.00
  TCS                                      qty=     500  avg=3345.00
```

> **Note:** Dhan tokens expire every 24 hours. Re-run `dhan_login` daily, or generate a new token from web.dhan.co.

### ✅ Step 3: Run Daily Snapshot

```
python -m scripts.daily_snapshot 
```

This will:

* Fetch latest market prices (LTP)
* Compute P&L for each leg
* Aggregate strategy-level P&L
* Store results in SQLite (`daily_snapshots` table)


---

## Trade Ledger

NiftyShield tracks every physical trade execution in a `trades` table — separate from the strategy leg definitions in `ilts.py` / `finrakshak.py`. This enables accurate weighted-average cost basis across multiple entries, a full audit trail for option rolls, and position queries without touching strategy files.

The two systems run in parallel: `Leg.entry_price` continues to drive `daily_snapshot.py` P&L until an explicit switch is made. The trade ledger grows independently.

### Backfill existing positions

```bash
# Dry run first — inspect what will be inserted
python scripts/seed_trades.py --dry-run

# Seed the live DB (idempotent — safe to re-run)
python scripts/seed_trades.py
```

### Record a new trade

```bash
python scripts/record_trade.py \
  --strategy ILTS \
  --leg EBBETF0431 \
  --key "NSE_EQ|INF754K01LE1" \
  --date 2026-04-08 \
  --action BUY \
  --qty 27 \
  --price 1386.20 \
  --notes "addition to ILTS position"
```

Prints the updated net position immediately after insert:

```
ILTS / EBBETF0431: 465 units @ avg ₹1388.01
```

Use `--dry-run` to validate fields without touching the DB:

```bash
python scripts/record_trade.py --strategy ILTS --leg EBBETF0431 \
  --key "NSE_EQ|INF754K01LE1" --date 2026-04-08 \
  --action BUY --qty 27 --price 1386.20 --dry-run
```

### Roll an option leg (expiry roll)

Use `roll_leg.py` to atomically close an expiring position and open the replacement in a single DB transaction. If either insert fails, neither is committed.

```bash
python scripts/roll_leg.py \
  --strategy finideas_ilts \
  --date 2026-06-20 \
  --old-leg NIFTY_MAY_PE_ATM \
  --old-key "NSE_FO|<expiring-token>" \
  --old-action BUY \
  --old-qty 50 \
  --old-price 45.00 \
  --new-leg NIFTY_JUN_PE_ATM \
  --new-key "NSE_FO|<new-token>" \
  --new-action SELL \
  --new-qty 50 \
  --new-price 85.00 \
  --notes "JUN expiry roll"
```

Prints updated net positions immediately after both inserts:

```
Roll complete — finideas_ilts  [2026-06-20]
  CLOSED  NIFTY_MAY_PE_ATM : 0 units @ avg ₹0.00
  OPENED  NIFTY_JUN_PE_ATM : -50 units @ avg ₹0.00
```

Use `--dry-run` to validate both trades without touching the DB:

```bash
python scripts/roll_leg.py --strategy finideas_ilts --date 2026-06-20 \
  --old-leg NIFTY_MAY_PE_ATM --old-key "NSE_FO|12345" \
  --old-action BUY --old-qty 50 --old-price 45.00 \
  --new-leg NIFTY_JUN_PE_ATM --new-key "NSE_FO|67890" \
  --new-action SELL --new-qty 50 --new-price 85.00 --dry-run
```

**`--old-action` convention:** BUY to cover a short (most option legs are short); SELL to exit a long.

### Query position directly

```python
from src.portfolio.store import PortfolioStore
from pathlib import Path

store = PortfolioStore(Path("data/portfolio/portfolio.sqlite"))
net_qty, avg_price = store.get_position("ILTS", "EBBETF0431")
# (465, Decimal('1388.0077...'))
```

### Short legs

SELL trades are recorded with `--action SELL`. Net quantity will be negative, avg price will be `0.00` (premium received, not a cost basis):

```bash
python scripts/record_trade.py \
  --strategy ILTS \
  --leg NIFTY_JUN_PE \
  --key "NSE_FO|37805" \
  --date 2026-01-15 \
  --action SELL \
  --qty 65 \
  --price 840.00 \
  --notes "short PE leg, ILTS hedge"
```

```
ILTS / NIFTY_JUN_PE: -65 units @ avg ₹0.00
```

---

## Testing Philosophy

Three-stage promotion pipeline — code must clear each stage before moving forward:

| Stage | Environment | Network | Purpose |
|-------|-------------|---------|---------|
| **1. Offline** | `MockBrokerClient` + recorded fixtures | None | Unit tests, strategy logic, backtesting |
| **2. Sandbox** | Upstox Sandbox API | Sandbox only | Order flow validation |
| **3. Production** | Upstox Live API | Live | Smoke tests, real trading |

```bash
# Stage 1: Run all offline tests (default, no network)
pytest

# Stage 2: Run sandbox tests (requires valid sandbox token)
pytest --sandbox
```

**Default is offline.** Running `pytest` with no flags never touches the network.

---

## Data Strategy

| Data Type | Storage | Purpose |
|-----------|---------|---------|
| Historical candles | Parquet | Backtesting, signal generation |
| Expired option contracts | SQLite | Reconstruct past chains |
| Live option chain | In-memory | Real-time strike selection |
| Order journal | SQLite | Audit trail, P&L tracking |
| Recorded API responses | JSON fixtures | Offline unit tests |
| Recorded tick streams | Parquet | Strategy replay tests |

All backtesting runs **fully offline** against local Parquet/SQLite stores. No API call should ever be made during a backtest.

---

## Key Upstox API Endpoints

| Capability | API | Usage |
|------------|-----|-------|
| Place/Modify/Cancel Orders | Orders API | Core execution |
| GTT Orders | GTT API | Stop-loss management |
| Option Chain | Option Chain API | Greeks, IV, OI for strike selection |
| Historical Candles | Historical Data V3 | Active instrument signals |
| Expired Instruments | Expired Instruments API | Backtesting past expiries |
| Portfolio & Positions | Portfolio API | Live monitoring |
| Margin Check | Margins API | Pre-order validation |
| Market Quotes | Market Quote API | LTP, OHLC |
| Live Streaming | Websocket API | Real-time tick data |

---

## Roadmap

- [x] Upstox OAuth login + token management
- [x] API connectivity verification
- [x] BrokerClient protocol + MockBrokerClient
- [x] NiftyBees market data fetcher (LTP, option chain via Analytics Token)
- [x] Daily snapshot pipeline (P&L, Telegram notification, historical replay)
- [x] MF portfolio tracking (transactions, NAV snapshots, holdings P&L)
- [x] Trade ledger (execution history, weighted avg cost basis, position queries)
- [x] Atomic leg roll CLI (expiry rolls with single-transaction close + open)
- [ ] Option chain fetcher with Greeks
- [ ] Historical data pipeline (active + expired)
- [ ] Offline data bootstrap script
- [ ] Backtesting engine
- [ ] Strategy engine (short strangle / iron condor)
- [ ] Delta-neutral adjustment logic
- [ ] Risk manager (margin monitoring)
- [ ] Order execution engine
- [ ] Websocket streaming + replay

---

## Security

- Credentials stored in `.env` (never committed)
- OAuth tokens expire daily
- Production order placement requires static IP whitelisting
- `.env`, `data/`, `.venv/` are gitignored

---

## Disclaimer

This project is for personal use and educational purposes. Options trading involves significant risk of loss. Past performance of any strategy does not guarantee future results. Always do your own analysis before placing trades.

---

## License

Private repository. Not for redistribution.
