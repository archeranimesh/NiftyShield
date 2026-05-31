# PB1.7 — Daemon + cron scripts + requirements.txt
> **Assigned to: Antigravity** — 6 files, fully spec'd, mechanical script wiring; no design decisions.

**Files to change:**
- `scripts/monitor_daemon.py` — persistent daemon process
- `scripts/start_monitor.py` — launches daemon if not running
- `scripts/stop_monitor.py` — sends SIGTERM to daemon
- `scripts/pre_market_brief.py` — 09:00 stateless cron
- `scripts/eod_summary.py` — 15:35 stateless cron
- `requirements.txt` — add `python-telegram-bot>=21.0`

**What to implement:**

**`scripts/monitor_daemon.py`** — Two concurrent asyncio tasks:
`StrategyMonitor.run()` and `TelegramGateway.start_polling()`.
Writes heartbeat on every tick. Handles `SIGTERM` cleanly:
  1. Cancel both tasks.
  2. Set all `PENDING` approvals to `EXPIRED`.
  3. Write final heartbeat with `last_event="SHUTDOWN"`.
  4. `sys.exit(0)`.

Registered strategies at startup: `CSPNiftyV1`, `IronCondorV1`, `NiftyTrackComparisonV1`
(instantiate each; if a strategy raises on init, log ERROR and skip — do not crash daemon).

**`scripts/start_monitor.py`** — Checks `daemon_heartbeat.last_beat`. If absent or stale
(> 5 minutes old): launch `python -m scripts.monitor_daemon` via `subprocess.Popen`.
Exits immediately after launch (does not block).

**`scripts/stop_monitor.py`** — Reads PID from `daemon_heartbeat`. Sends `SIGTERM`.
Polls for up to 30 seconds. If process still alive: sends `SIGKILL`. Logs outcome.

**`scripts/pre_market_brief.py`** — Stateless. Cron: `00 09 * * 1-5`.
Fetches open `PaperPosition`s from all 4 strategy names.
Formats a Telegram message: strategy name, leg count, total unrealized P&L, IVR.
Sends via `TelegramGateway.send_plain_message`. Non-fatal.

**`scripts/eod_summary.py`** — Stateless. Cron: `35 15 * * 1-5`.
Fetches today's `paper_nav_snapshots`. Formats daily P&L summary per strategy.
Fetches today's council activity count from `pending_approvals`.
Sends via `TelegramGateway.send_plain_message`. Non-fatal.

**Cron additions (document in script header comments):**
```
00 09 * * 1-5  python -m scripts.pre_market_brief
15 09 * * 1-5  python -m scripts.start_monitor
30 15 * * 1-5  python -m scripts.stop_monitor
35 15 * * 1-5  python -m scripts.eod_summary
```

No unit tests required for daemon/cron scripts.

**Commit:** `feat(scripts): add monitor_daemon + start/stop + pre_market_brief + eod_summary + python-telegram-bot dep`

---

## Pre-baked Context

> Graph queries pre-run 2026-05-31. Skip "Before any code" graph calls — use these directly.

**`StrategyMonitor`** — `src/strategy/monitor.py` (PB1.2).
Constructor: `StrategyMonitor(broker, store, notifier, strategies, poll_interval_s=90)`.
Key methods: `async def run()`, `register(strategy)`.

**`TelegramGateway`** — `src/notifications/telegram_gateway.py` (PB1.5).
Constructor: `TelegramGateway(bot_token, chat_id, db_path)`.
Key methods: `send_plain_message(text) -> bool`, `async start_polling(on_approved, on_rejected)`.

**`PaperStore.write_heartbeat`** — added in PB1.6. Signature:
`write_heartbeat(pid: int, strategies: list[str], last_event: str | None = None) -> None`.
`get_heartbeat() -> dict | None` — returns the single `daemon_heartbeat` row.

**`build_notifier`** — `src/notifications/telegram.py:121`. Returns `TelegramNotifier | None`.
For the daemon, build `TelegramGateway` directly using `settings.telegram_bot_token` and
`settings.telegram_chat_id` — `build_notifier` is for the simpler `TelegramNotifier` only.

**`UPSTOX_ENV` / factory pattern** — in existing scripts, client is constructed via
`from src.client.factory import create_client; broker = create_client()`.
Confirm the exact factory function name with `grep -n "def create" src/client/factory.py`
before writing the daemon.

**`CSPNiftyV1` / `IronCondorV1` / `NiftyTrackComparisonV1`** — all in `src/strategy/`
(PB2.1, PB3.1, PB4.1). Import all three at the top of `monitor_daemon.py`; guard each
instantiation in `try/except Exception` so a broken strategy doesn't crash the daemon.
