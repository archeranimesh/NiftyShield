# NiftyShield

**Options selling automation on NiftyBees ETF, powered by Upstox API.**

NiftyShield is a systematic options trading engine built on a leveraged capital structure —
FD-backed Overdraft facility funding NiftyBees ETF purchases (pledged for margin) and ILTS allocation,
generating two parallel income streams from one pool of borrowed capital.

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
│   ├── auth/              # OAuth flow — Upstox, Nuvama, Dhan
│   ├── client/
│   │   ├── protocol.py        # BrokerClient + sub-protocols (ISP)
│   │   ├── upstox_live.py     # Live Upstox implementation
│   │   ├── upstox_sandbox.py  # Sandbox implementation
│   │   ├── upstox_market.py   # Analytics Token market data (legacy)
│   │   ├── mock_client.py     # Stateful offline mock
│   │   └── factory.py         # Composition root (sole concrete importer)
│   ├── models/            # Shared Pydantic models (option chain, portfolio, mf)
│   ├── portfolio/         # Strategy P&L, daily snapshots, trade ledger
│   ├── paper/             # Paper trading — PaperTrade, PaperStore, PaperTracker
│   ├── strategy/          # Paper-backbone strategies — CSP/CC/PP/Collar/Iron Condor V1+V2, StrategyMonitor, exit-signal engine
│   ├── risk/              # Portfolio delta gating — PortfolioDeltaTracker, entry gate
│   ├── backtest/          # IVR, VIX ingestion, EOD/intraday chain Parquet writer+reader
│   ├── gamma/             # Near-Expiry Gamma Buy — chain snapshot model + store
│   ├── council/           # LLM Council client (RapidCouncil) — stage-1 fan-out + chairman synthesis
│   ├── mf/                # MF transaction ledger, AMFI NAV fetcher
│   ├── dhan/              # Dhan equity/bond holdings + Upstox LTP enrichment
│   ├── nuvama/            # Nuvama bond holdings + options P&L
│   ├── instruments/       # BOD instrument lookup, expiry/strike resolution
│   ├── market_calendar/   # NSE holiday calendar (YAML-backed, fail-open)
│   ├── notifications/     # Telegram notifier (non-fatal, MarkdownV2 parse_mode)
│   ├── intraday/          # Intraday monitoring orchestration (Dhan + Nuvama)
│   ├── utils/             # Structured logging, number formatting, config helpers
│   ├── config.py          # Settings singleton (pydantic-settings) — import, never os.getenv
│   ├── db.py              # Shared SQLite context manager (WAL, FK, Row factory)
│   ├── execution/         # [empty — planned Phase 1–2, see BACKTEST_PLAN.md]
│   └── streaming/         # [empty — planned Phase 1–2, see BACKTEST_PLAN.md]
├── scripts/
│   ├── pipeline/          # EOD/intraday chain snapshot, gamma watch, bhavcopy bootstrap
│   ├── lookup/            # Strike-by-delta finder, instrument BOD lookup
│   ├── record/            # Paper/live trade recording CLIs
│   ├── strategies/        # Per-strategy entry/roll/snapshot scripts (csp/, ic/, three_track/, cc_calibration/)
│   ├── portfolio/         # Live portfolio P&L crons (daily_snapshot, morning_nav, paper_snapshot, roll_leg, backup_db)
│   ├── intraday/          # Intraday tracker crons (Dhan + Nuvama)
│   ├── reporting/         # Paper P&L report builder
│   ├── seed/              # One-time DB seed scripts
│   ├── council/           # ask_council.py CLI + templates
│   ├── dev/               # Diagnostics, one-off migrations, backfills
│   ├── cron/              # Cron line references
│   ├── healthcheck.py           # Dead man's switch for EOD cron validation
│   ├── monitor_daemon.py        # StrategyMonitor daemon main loop
│   ├── position_health_check.py # Roll-overdue / unmapped-asset alert cron
│   ├── pre_market_brief.py      # Pre-market summary cron
│   ├── eod_summary.py           # EOD P&L summary cron
│   └── start_monitor.py / stop_monitor.py  # Daemon launcher / shutdown
├── tests/
│   ├── unit/              # ~2980 offline tests (default — no network, no real tokens)
│   └── fixtures/          # Recorded API responses (JSON)
├── data/
│   └── portfolio/         # portfolio.sqlite (live DB — gitignored)
├── docs/
│   ├── plan/              # Per-story task files + swing/investment research pipelines
│   ├── strategies/        # Strategy spec documents (csp_nifty_v1.md, etc.)
│   ├── council/           # Council decision files + README workflow
│   ├── bugs/              # Open defect tracker (bugs.md / task.md / prompt.md)
│   └── archive/           # Completed plans, archived TODOs, old agents, closed bugs
├── .env.example
├── requirements.txt
├── requirements-dev.txt
├── tools/             # Git submodules (llm-council)
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

# Choose one:
# A. For runtime/production only:
pip install -r requirements.txt

# B. For development (runs tests, linters, pre-commit):
pip install -e ".[dev]"
bash scripts/dev/install_hooks.sh
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

NiftyShield tracks your Nuvama bond and gold bond holdings for margin and portfolio visibility.
Nuvama uses a `request_id` redirect flow — run this once and the session persists indefinitely in a local settings file.

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

Opens your browser to the Nuvama login page.
After authenticating, you'll be redirected to a URL containing a `request_id` token.
Paste the full redirect URL (or just the token) at the prompt.
The session is saved to `NUVAMA_SETTINGS_FILE` — no daily re-auth required.

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

### Nuvama Intraday Options Tracking (Cron)

NiftyShield automatically tracks Nuvama options positional M2M Highs/Lows and captures corresponding Nifty Spot points.

**Cron setup:** Run this silently structured cron hook every 5 minutes during market hours.
```bash
*/5 9-15 * * 1-5 cd /path/to/NiftyShield && .venv/bin/python -m scripts.nuvama_intraday_tracker
```
The tracker efficiently polls Nuvama + Upstox
and permanently persists the 30-day bounding history (M2M max/min + Spot bounds) directly localized inside `portfolio.sqlite`
to be naturally utilized during Daily Snapshots.


### EOD Option Chain Snapshot (Cron)

Fetches Nifty option chains for up to 3 expiries (monthly / quarterly / yearly) and writes each to Parquet for downstream backtesting and slippage analysis.

```bash
# EOD option chain snapshot — 3:30 PM IST, Mon–Fri
30 15 * * 1-5  cd /path/to/NiftyShield && python -m scripts.pipeline.upstox_chain_snapshot >> logs/chain_snapshot.log 2>&1
```

Output path: `data/offline/chain_snapshots/{year}/{month}/upstox_{date}.parquet` (override with `CHAIN_SNAPSHOT_DIR`).


### Intraday Option Chain Snapshot (Cron)

Fetches Nifty option chains for up to 3 expiries every 5 minutes during market hours and writes each to Parquet for downstream backtesting and slippage analysis.

```bash
# Intraday 5-min option chain snapshot — 9:00 AM to 3:55 PM IST, Mon–Fri
*/5 9-15 * * 1-5  cd /path/to/NiftyShield && python -m scripts.pipeline.upstox_chain_intraday >> logs/chain_intraday.log 2>&1
```

Output path: `data/offline/chain_snapshots_5min/{year}/{month}/{day}/upstox_{HHMM}.parquet` (override with `CHAIN_INTRADAY_DIR`).


### Database Backup and Retention (Cron)

Creates an online backup of the live WAL-mode portfolio database
and prunes older backups (retains newest 30 daily and 12 monthly backups).
The backup destination is determined by `BACKUP_DIR` in `.env` (defaults to `/var/backups/niftyshield`),
ensuring backups are physically isolated from the repo mount.

```bash
# Online DB backup — 4:00 PM IST, Mon–Fri
0 16 * * 1-5  cd /path/to/NiftyShield && python -m scripts.portfolio.backup_db >> logs/backup_db.log 2>&1
```



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

Opens your browser to Dhan web portal.
Navigate to Profile → "Access DhanHQ APIs" → "Generate Access Token".
Fill in App Name (e.g. `NiftyShield`), keep Token validity at 24h.
Copy the generated token and paste it at the prompt.

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
* Extract Nuvama Intraday High/Low Bounds
* Aggregate strategy-level P&L
* Store results in SQLite (`daily_snapshots` table)


---

## Trade Ledger

NiftyShield tracks every physical trade execution in a `trades` table — separate from the strategy leg definitions in `ilts.py` / `finrakshak.py`.
This enables accurate weighted-average cost basis across multiple entries,
a full audit trail for option rolls,
and position queries without touching strategy files.

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

## Paper Trade Entry Workflow

The typical paper trade entry is a two-step process: scan the live chain for a strike that matches your delta target, then record the trade.

### Step 1 — Find a strike by delta

```bash
# Scan both CE and PE sides for 20–30 delta, default expiry
python scripts/find_strike_by_delta.py \
    --expiry 2026-05-29 \
    --delta-min 0.20 --delta-max 0.30
```

Output:

```
Fetching option chain: NSE_INDEX|Nifty 50  expiry=2026-05-29 …

  Nifty 50  expiry: 2026-05-29  |  spot: ₹24,250.00
  SIDE    STRIKE    DELTA    IV%      LTP      MID      BID      ASK        OI  KEY
  ──────────────────────────────────────────────────────────────────────────────────
  CE      25000    +0.2851   12.43    85.50    85.25    85.00    85.50    124500  NSE_FO|41200
  CE      25100    +0.2310   11.87    65.25    65.38    65.25    65.50     98200  NSE_FO|41210
  PE      23500   -0.2976   12.18    80.50    80.25    80.00    80.50    156800  NSE_FO|41300
  PE      23400   -0.2512   11.55    65.75    65.63    65.50    65.75    132400  NSE_FO|41310
```

Filter to one side and add `--dry-run` to get a ready-to-paste `record_paper_trade.py` command per match:

```bash
python scripts/find_strike_by_delta.py \
    --expiry 2026-05-29 \
    --delta-min 0.20 --delta-max 0.30 \
    --option-type PE \
    --strategy paper_csp_nifty_v1 \
    --leg short_put \
    --qty 75 \
    --action SELL \
    --dry-run
```

Output adds:

```
─── Dry-run (SELL · paper_csp_nifty_v1) ────────────────────────────────────────

# PE 23500 | delta=-0.2976 | iv=12.18%
python scripts/record_paper_trade.py \
    --strategy paper_csp_nifty_v1 \
    --leg short_put \
    --key "NSE_FO|41300" \
    --date 2026-05-03 \
    --action SELL \
    --qty 75 \
    --price 80.25

# PE 23400 | delta=-0.2512 | iv=11.55%
python scripts/record_paper_trade.py \
    --strategy paper_csp_nifty_v1 \
    --leg short_put \
    --key "NSE_FO|41310" \
    --date 2026-05-03 \
    --action SELL \
    --qty 75 \
    --price 65.63
```

Price defaults to `(bid + ask) / 2`; falls back to LTP when the spread is zero.
`--leg` is auto-inferred from `--option-type` + `--action` when omitted (`PE + SELL → short_put`, `CE + SELL → short_call`, etc.).

All flags:

| Flag | Default | Notes |
|---|---|---|
| `--expiry` | *(required)* | YYYY-MM-DD |
| `--delta-min` | `0.20` | Lower bound for \|delta\| |
| `--delta-max` | `0.35` | Upper bound for \|delta\| |
| `--option-type` | `BOTH` | `CE` / `PE` / `BOTH` |
| `--underlying` | `NSE_INDEX\|Nifty 50` | Override for other underlyings |
| `--strategy` | `paper_csp_nifty_v1` | Must start with `paper_` |
| `--leg` | *(auto-inferred)* | e.g. `short_put`, `short_call` |
| `--qty` | `75` | 1 Nifty lot |
| `--action` | `SELL` | `BUY` / `SELL` |
| `--date` | today | Trade execution date |
| `--dry-run` | off | Emit record_paper_trade commands |

Requires `UPSTOX_ANALYTICS_TOKEN` in `.env`.

### Step 2 — Record the paper trade

Copy the command from `--dry-run` output and run it directly. See [Paper Trade CLI](#paper-trade-cli) for the full `record_paper_trade.py` reference.

### Paper Trade CLI

```bash
# Auto-resolve instrument key from underlying + strike + expiry
python scripts/record_paper_trade.py \
    --strategy paper_csp_nifty_v1 \
    --leg short_put \
    --underlying NIFTY \
    --strike 23500 \
    --option-type PE \
    --expiry 2026-05-29 \
    --date 2026-05-03 \
    --action SELL \
    --qty 75 \
    --price 80.25

# Or use --key directly (faster — no BOD lookup)
python scripts/record_paper_trade.py \
    --strategy paper_csp_nifty_v1 \
    --leg short_put \
    --key "NSE_FO|41300" \
    --date 2026-05-03 \
    --action SELL \
    --qty 75 \
    --price 80.25

# Dry run — validate without inserting
python scripts/record_paper_trade.py \
    --strategy paper_csp_nifty_v1 --leg short_put \
    --key "NSE_FO|41300" --date 2026-05-03 \
    --action SELL --qty 75 --price 80.25 --dry-run
```

`--strategy` must start with `paper_`. Strategy name is enforced at both the CLI and model layer to prevent cross-contamination with the live trade ledger.

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
- [x] Nuvama portfolio monitoring (bonds/gold bonds)
- [x] Nuvama options P&L fetch and reporting
- [x] Nuvama intraday tracker (5-minute M2M/Spot bounds snapshotting)
- [x] Dhan portfolio monitoring (equity + bond holdings, Upstox LTP enrichment)
- [x] NSE market holiday calendar (fail-open, version-controlled YAML)
- [x] Morning NAV backfill script (pre-market AMFI fetch, T-1 gap fix)
- [x] Greeks capture — `OptionChain` Pydantic model + `_extract_greeks_from_chain` (2026-04-25)
- [x] Paper trading module (`src/paper/`) — `PaperTrade`, `PaperStore`, `PaperTracker`, `record_paper_trade.py` (2026-04-25)
- [x] Strategy spec validator — `scripts/validate_strategy_spec.py`, 28 tests (2026-04-25)
- [x] CSP v1 strategy spec — `docs/strategies/csp_nifty_v1.md` (Nifty 50 index options, R1–R7)
- [x] NiftyShield integrated strategy spec — `docs/strategies/niftyshield_integrated_v1.md`
- [x] `find_strike_by_delta.py` — live chain → |delta| filter → strike/IV/key table + `--dry-run` record_paper_trade commands (2026-05-03)
- [x] Historical data pipeline — VIX ingestion (`src/backtest/vix_ingest.py`) + EOD/intraday option chain
  Parquet writer/reader (`src/backtest/chain_writer.py`/`chain_reader.py`)
- [x] Backtest analytics module (`src/backtest/`) — IVR computation, chain data pipeline
  (the full multi-phase backtest engine — portfolio construction, live promotion — remains in progress, see `BACKTEST_PLAN_PHASE1.md`, **P0**)
- [x] Strategy engine (`src/strategy/`) — CSP/CC/PP/Collar overlays, Iron Condor V1+V2, `StrategyMonitor`, exit-signal engine; paper-trading backbone live since 2026-07
- [x] Portfolio delta risk manager (`src/risk/`) — `PortfolioDeltaTracker`, entry gate, warning/cap thresholds
- [ ] Order execution engine (`src/execution/`) — blocked (static IP)
- [ ] Websocket streaming + replay (`src/streaming/`) — Phase 1–2, see `BACKTEST_PLAN.md`

---

## Security

- Credentials stored in `.env` (never committed)
- OAuth tokens expire daily
- Production order placement requires static IP whitelisting
- `.env`, `data/`, `.venv/` are gitignored

---

## Disclaimer

This project is for personal use and educational purposes.
Options trading involves significant risk of loss.
Past performance of any strategy does not guarantee future results.
Always do your own analysis before placing trades.

---

## Reference Documents (for AI assistants and contributors)

The project root contains a set of markdown files that serve as structured context for both AI coding assistants and human contributors.
`CLAUDE.md` defines exactly when each file should be loaded.

### Always load at the start of every session

| File | Purpose |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Mandatory 6-step AI pre-task workflow: read context → confirm scope → plan → test → update docs → commit. Auto-loaded at session start. |
| [`CONTEXT.md`](CONTEXT.md) | **Single source of truth** for codebase state — module tree, what exists vs. what doesn't, live DB state, test counts, active constraints. Read before writing code. |

### Load when relevant

| File | When to load | Purpose |
|---|---|---|
| [`DECISIONS.md`](DECISIONS.md) | Adding or changing module architecture | Architecture decisions with rationale and tradeoffs — why choices were made, what alternatives were rejected. |
| [`REFERENCES.md`](REFERENCES.md) | Touching instrument keys, AMFI codes, or market data | Instrument keys, AMFI scheme codes, API quirks, token lifetimes, exact DB column names. |
| [`TODOS.md`](TODOS.md) | Starting a new feature | Two-in-one: priority-tiered (P0→P5) open action items + chronological session log. Mark items done and add a log entry each session. |
| [`PLANNER.md`](PLANNER.md) | Starting a new feature | Multi-sprint feature roadmap — where the next task fits in the overall sequence. |
| [`BACKTEST_PLAN.md`](BACKTEST_PLAN.md) | Any backtest, paper trading, or strategy research task | Phased backtesting → paper trading → live execution pipeline plan. Read before any Phase 0–4 work. |
| [`LITERATURE.md`](LITERATURE.md) | Implementing a metric or ML technique | Concept reference — Kelly, Sharpe, meta-labeling, Greeks; each carries a `LIT-N` code cited in comments and TODOs. |
| [`REVIEW.md`](REVIEW.md) | Before every commit (`code-reviewer` agent) | Python review checklist — bug patterns (Part I), Pythonic idioms (Part II), Google Style rules G1–G8 (Part III). |

`BACKTEST_PLAN.md` renders as an interactive card-format widget — say "show me the plan" to get the visual view.

### Quick reference — when to read what

```
Every session          →  CLAUDE.md  +  CONTEXT.md
New feature            →  + TODOS.md + PLANNER.md
Architecture change    →  + DECISIONS.md
Market data / keys     →  + REFERENCES.md
Backtest / strategy    →  + BACKTEST_PLAN.md + LITERATURE.md
Before each commit     →  REVIEW.md  (via code-reviewer agent)
```

---

## Skills & Agents — Phrase Triggers

NiftyShield has pre-configured skills and agents you invoke by saying a phrase to Claude. No setup needed — just use the trigger phrase and the right tool fires automatically.

### Skills (reusable workflows)

| Skill | Say this | What happens |
|---|---|---|
| **plan view** | "show me the plan" · "plan status" | Renders `BACKTEST_PLAN.md` as an interactive card widget — task cards, `[x]` state, badges, gate rows. Auto-renders on file read. |
| **md-organize** | "organize the markdown" · "archive TODOs" | Archives done stories + old log entries, syncs docs, reflows prose, reconciles the `CLAUDE.md` / `AGENTS.md` mirrors, commits. |
| **commit** | "generate a commit message" | Produces a commit in the project format (`type(scope): subject` + `Why:` + `What:` + `Ref:`). Full spec in `.claude/skills/commit/SKILL.md`. |

### Agents (specialist sub-tasks)

| Agent | Model | Say this | What it does |
|---|---|---|---|
| **code-reviewer** | Opus | "Run code-reviewer on `src/portfolio/`" | Checks Decimal invariants, BrokerClient protocol, type hints, async, REVIEW.md hygiene; flags CRITICAL / ERROR / WARNING. |
| **test-runner** | Haiku | "Run the test-runner agent" | Runs `python -m pytest tests/unit/`, reports pass/fail count + any failures. Use after every code change before committing. |
| **greeks-analyst** | Sonnet | "Design/extend the OptionChain model" | Inspects the `nifty_chain_2026-04-07.json` fixture, proposes changes to `OptionChain` and `_extract_greeks_from_chain()`. |
| **roll-validator** | Opus | "Validate before I roll [leg]" | Validates pre-roll net position, Trade model integrity, txn atomicity, instrument keys; returns SAFE TO ROLL / DO NOT ROLL. |
| **options-strategist** | Opus | "Size a short strangle for [expiry]" | Designs IC / strangle legs by delta; delta-neutral analysis, rebalance signals. Advisory until execution is live. |

### When to reach for which

```
After writing code           →  test-runner (quick) → code-reviewer (before merge)
About to commit              →  commit skill
Expiry is approaching        →  roll-validator before touching the DB
Greeks / OptionChain work    →  greeks-analyst
Strategy design question     →  options-strategist
TODOS getting messy          →  md-organize skill
Check plan / what's next     →  "show me the plan"  (card-format widget)
```

---

## License

Private repository. Not for redistribution.
