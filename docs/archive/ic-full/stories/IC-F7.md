# IC-F7 — `paper_ic_snapshot.py` EOD audit cron

> **Assigned to: Antigravity** — new script; TDD loop.

**Prerequisites:**
- IC-F3 — parameterised `IronCondorV1` (strategy names stable; `auto_execute=True`)

**Important context shift from earlier design:** With `auto_execute=True`, the daemon
handles exits during market hours. The EOD snapshot is now an **audit log**, not an
action-prompting tool. Its job: confirm what happened today, report current position
state, flag anything the intraday daemon may have missed (e.g. if daemon was down),
emit DTE reminders. Do NOT duplicate daemon action signals into Telegram as approvals.

**Files to create:**
- `scripts/strategies/ic/paper_ic_snapshot.py`
- `tests/unit/strategies/ic/test_paper_ic_snapshot.py`
  (`scripts/strategies/ic/__init__.py` created in IC-F6)

---

## Implementation

### `_SCRIPT_NAME`
```python
_SCRIPT_NAME = "scripts.strategies.ic.paper_ic_snapshot"
logger = structlog.get_logger(_SCRIPT_NAME)
```

### Per-variant loop

For each `expiry_type, config` in `CONFIGS.items()`:

1. `positions = store.get_positions(config.strategy_name)` — skip if empty (no message).
2. Parse expiry from any position's `instrument_key` (use `_EXPIRY_RE` pattern).
3. Fetch live chain (wrap in try/except — one failure must not abort remaining variants).
4. `ic = IronCondorV1(broker, store, notifier, config)`
5. `events = await ic.check_signals(chain, positions)`
6. Check for any OPEN exit events already in DB (`store.get_open_exit_events(config.strategy_name)`).
   These were created by intraday auto-execute — include their status in the audit report.
7. Build and send one Telegram message per active variant (format below).

### Telegram format (audit, not action-prompting)

```
📋 IC EOD Audit — monthly (paper_ic_nifty_v1_monthly)
DTE: 18  |  Nifty: 24,750  |  IVR: 0.42

Position:
  Short Put  24500PE  δ=-0.18  LTP=₹62.50  (entry ₹85.50)
  Long Put   24000PE  LTP=₹18.00
  Short Call 25200CE  δ=0.11   LTP=₹38.00  (entry ₹42.25)
  Long Call  25700CE  LTP=₹12.00

P&L: combined mark ₹112.00 vs entry credit ₹127.75 → 12% captured so far

Today's signals: DTE_WARN ℹ️
Intraday actions: none
```

If intraday auto-execute fired today (ACTED exit events in DB):
```
Intraday actions: PROFIT_TARGET → CLOSE_FULL executed at 11:42
```

If ACTION signals still present at EOD (daemon may have been down):
```
⚠️  Unresolved ACTION signals:
  TIME_STOP 🔴  DTE 14 — position should have been closed today
```

### No open positions across all variants
Single Telegram: `"IC EOD: no open positions across all expiry types."`

---

## Tests (8 tests, all offline)

Mock: chain fetch, `PaperStore`, `TelegramGateway`, `IronCondorV1.check_signals`.

1. One variant active → one Telegram message with position + signal summary.
2. All four active → four messages sent.
3. Intraday ACTED exit event → message includes "Intraday actions" line.
4. Unresolved ACTION signal at EOD → "Unresolved ACTION signals" block in message.
5. DTE ≤ `config.dte_warn` → DTE_WARN noted even when no other signals.
6. No active variants → single "no open positions" message.
7. Chain fetch fails for one variant → error logged; other variants processed; error note in Telegram for failed variant.
8. `check_signals` raises for one variant → caught; remaining variants processed.

---

## Commit

```
feat(scripts/ic): paper_ic_snapshot.py — EOD audit cron for all IC variants

Why: auto_execute daemon handles exits; EOD snapshot provides audit trail
and catches daemon-down scenarios.
What:
- scripts/strategies/ic/paper_ic_snapshot.py: EOD cron over all CONFIGS
- tests/unit/strategies/ic/test_paper_ic_snapshot.py: 8 offline tests
Ref: ic-full IC-F7
```

---

## Pre-baked Context

**`store.get_open_exit_events(strategy_name)`** — returns `list[PaperExitEvent]` where
`status == "OPEN"`. ACTED events have `status == "ACTED"` — fetch all and filter locally
if the store method only returns OPEN. Check `PaperStore` API before assuming.

**`_EXPIRY_RE`** from `ic_nifty_v1.py`:
```python
_EXPIRY_RE = re.compile(r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE|CE)", re.IGNORECASE)
```
Reuse this pattern — do not duplicate; import from `ic_nifty_v1` or replicate inline
with a comment pointing to the source.

**`CONFIGS`** — `src.strategy.ic_expiry_config`. Iterate `CONFIGS.items()`.

**`paper_3track_snapshot.py`** at `scripts/strategies/three_track/paper_3track_snapshot.py` —
reference for structlog setup, `_SCRIPT_NAME`, Telegram send, and asyncio entry point.

**Cron target:** `45 15 * * 1-5` — wire in IC-F8 scheduled task, not in this script.
This script has no built-in scheduler; it runs to completion and exits.
