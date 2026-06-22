# IC-E4 — `scripts/strategies/ic/paper_ic_snapshot.py`: EOD cron

> **Assigned to: Antigravity** — new script, well-defined spec; TDD loop appropriate.

**Prerequisite:** IC-E1 and IC-E2 must be committed.

**Files to create/change:**
- `scripts/strategies/ic/paper_ic_snapshot.py` — new EOD snapshot + signal detection script
- `tests/unit/strategies/ic/test_paper_ic_snapshot.py` — new test file

---

## Purpose

Provides the IC with the same daily monitoring coverage that `paper_3track_snapshot.py`
gives to the 3-Track strategy. Runs as an EOD cron, queries open IC positions, evaluates
exit signals via `IronCondorV1.check_signals`, deduplicates against existing OPEN events
in `PaperStore`, and sends a Telegram summary.

---

## CLI

```
python scripts/strategies/ic/paper_ic_snapshot.py [--date YYYY-MM-DD] [--dry-run] [--no-dry-run]
```

| Flag | Default | Description |
|---|---|---|
| `--date YYYY-MM-DD` | today (IST) | Snapshot date |
| `--dry-run` / `--no-dry-run` | `--dry-run` | Print report only; no DB writes or Telegram sends |

---

## Implementation steps (in order)

### Step 1 — Trading day guard

Call `is_trading_day(snapshot_date)`. If `False`: log INFO "not a trading day" and exit 0.

### Step 2 — Load open IC positions

`positions = store.get_open_positions(strategy_name=STRATEGY_IC)`
If empty: log INFO "no open IC positions" and send Telegram `"[IC] No open position"`. Exit 0.

### Step 3 — Fetch option chain

Resolve expiry from the first position's `instrument_key` (parse the expiry suffix).
Use `UpstoxMarketClient(settings.upstox_analytics_token).get_option_chain("NSE_INDEX|Nifty 50", expiry_str)`.
Parse with `parse_upstox_option_chain(raw)` → `OptionChain`.

### Step 4 — Run exit signal detection

```python
strategy = IronCondorV1(broker=broker, store=store, notifier=gateway)
signals = await strategy.check_signals(market=chain, positions=positions)
```

### Step 5 — Deduplicate against existing open events

For each ACTION signal, call `store.get_open_exit_events(strategy_name=STRATEGY_IC, leg_name=..., exit_signal=signal.event_type)`.
If an OPEN event already exists for the same signal type + leg, skip recording (do not double-fire Telegram).

### Step 6 — Record new ACTION events

For each new (non-duplicate) ACTION signal: call `store.create_exit_event(...)`.
In dry-run mode: print the event details instead, no DB write.

### Step 7 — Build terminal report

```
=== IC Snapshot — 2026-07-15 ===
Strategy : paper_ic_nifty_v1
Nifty    : 24,850.00
DTE      : 22

Legs:
  short_put  NIFTY24500PE  δ=-0.189  LTP=₹72.00  Entry=₹85.50
  long_put   NIFTY24000PE  LTP=₹18.50
  short_call NIFTY25200CE  δ=0.101   LTP=₹38.00  Entry=₹42.25
  long_call  NIFTY25700CE  LTP=₹11.00

Combined mark   : ₹139.50  (entry credit: ₹127.75)
% of credit     : 109.2%  ← above 100% = currently at a loss
Combined P&L    : −₹763  (−11.7 points × 65 units)

Signals detected:
  [INFO] DTE_WARN — DTE 22 ≤ 25
  (no ACTION signals)
```

### Step 8 — Send Telegram

Condense the report to a shorter Telegram message (3–5 lines):
```
[IC] 2026-07-15 | DTE 22 | Nifty 24,850
Mark ₹139.50 vs credit ₹127.75 (109%)
P&L: −₹763
Signals: DTE_WARN (INFO)
```
In dry-run mode: print message to stdout only.

### Step 9 — DTE expiry alert

If `dte <= 5`: append to Telegram message:
`"⚠️ DTE ≤ 5 — TIME_STOP should fire at DTE 14; verify exit has been executed."`

---

## Tests (`tests/unit/strategies/ic/test_paper_ic_snapshot.py`)

All offline. Mock `UpstoxMarketClient`, `PaperStore`, `IronCondorV1.check_signals`,
`is_trading_day`, `TelegramNotifier`.

**Happy-path tests:**
1. Open IC position + chain returns clean data → report generated, no ACTION signals →
   Telegram INFO message sent, no exit events recorded.
2. Open IC position + `check_signals` returns DELTA_STOP ACTION → new exit event recorded,
   Telegram ACTION message sent.
3. `--dry-run` → no `store.create_exit_event` call, no Telegram send, report printed.
4. Existing OPEN exit event for same signal → deduplicated, no second event recorded.

**Edge/error tests:**
5. No open IC positions → exits 0 with `"[IC] No open position"` Telegram.
6. Non-trading day → exits 0, no chain fetch attempted.
7. DELTA_STOP fires for both short_put and short_call in same tick → two separate exit events
   recorded (one per leg).

---

## Cron configuration

Add to `scripts/daemon/` or document in `TODOS.md`:
```
# EOD IC snapshot — 15:40 IST (after 3-Track snapshot at 15:35)
40 10 * * 1-5  cd /path/to/NiftyShield && python scripts/strategies/ic/paper_ic_snapshot.py --no-dry-run
```

---

## Commit

```
feat(scripts/ic): add paper_ic_snapshot.py — EOD IC signal detection cron

Why: IC positions had no daily exit-signal report; operators had to manually
inspect positions; signal deduplication was absent.
What:
- scripts/strategies/ic/paper_ic_snapshot.py: EOD snapshot + signal detection
- tests/unit/strategies/ic/test_paper_ic_snapshot.py: 7 offline tests
Ref: ic-e2e IC-E4
```

---

## Pre-baked Context

**`PaperStore.get_open_positions`** — `src/paper/store.py`.
Signature: `get_open_positions(strategy_name: str | None = None) -> list[PaperPosition]`.

**`PaperStore.get_open_exit_events`** — `src/paper/store.py`.
Signature: `get_open_exit_events(strategy_name: str, leg_name: str, exit_signal: str) -> list[PaperExitEvent]`.

**`PaperStore.create_exit_event`** — `src/paper/store.py`.
Upserts by `(trade_id, exit_signal)`.

**`ExitSignal`** enum — `src/paper/models.py`.
Members include: `DELTA_STOP`, `TIME_STOP`, `PROFIT_TARGET`, `LOSS_STOP`, `DTE_WARN`, `ROLL_WING`.

**`is_trading_day`** — `src/market_calendar/holidays.py`.
Signature: `is_trading_day(d: date) -> bool`. Returns False on NSE holidays and weekends.

**`parse_upstox_option_chain`** — `src/client/upstox_market.py`.
Signature: `parse_upstox_option_chain(raw: dict) -> OptionChain`.

**`STRATEGY_IC`** — `src/paper/constants.py` (added in IC-E1). Value: `"paper_ic_nifty_v1"`.

**`IronCondorV1.check_signals`** — `src/strategy/ic_nifty_v1.py`.
Async. Accepts `market: OptionChain`, `positions: list[PaperPosition]`. Returns `list[SignalEvent]`.

**`TelegramNotifier`** — `src/notifications/telegram.py`.
Non-fatal: all methods log errors and return, never raise. Use `send_plain_message(text)` for
both INFO and ACTION summaries in this script (ACTION events are already routed to the approval
flow by the live daemon; the snapshot is read-only reporting).
