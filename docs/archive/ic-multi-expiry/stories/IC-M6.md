# IC-M6 — `paper_ic_snapshot.py` EOD cron (supersedes ic-e2e IC-E4)

> **Assigned to: Antigravity** — new script; TDD loop; fully specified below.

**This story supersedes ic-e2e IC-E4.** Do not implement IC-E4 from the ic-e2e plan.

**Prerequisites:**
- ic-multi-expiry IC-M2 — parameterised `IronCondorV1` (strategy names must be stable)
- ic-multi-expiry IC-M5 — entry script committed (ensures at least one IC variant can produce positions to snapshot)

**Files to create:**
- `scripts/strategies/ic/paper_ic_snapshot.py` — new EOD cron script
- `tests/unit/strategies/ic/test_paper_ic_snapshot.py` — new test file
  (`scripts/strategies/ic/__init__.py` already exists after IC-M5)

---

## Purpose

EOD cron that iterates all four IC strategy names, fetches open positions for each,
runs `IronCondorV1.check_signals()`, and sends a consolidated Telegram report.
Analogous to `scripts/strategies/three_track/paper_3track_snapshot.py` but for ICs.

Cron target: `45 15 * * 1-5` (same slot as other EOD snapshots).

---

## Implementation

### Script structure

```python
"""EOD IC snapshot — exit signal detection for all four IC expiry variants.

Iterates paper_ic_nifty_v1_weekly / _monthly / _leaps / _yearly in sequence.
For each variant with open positions: fetches live chain, runs IronCondorV1
signal engine, deduplicates against existing OPEN exit events, sends Telegram
report. Variants with no open positions are skipped silently.

Cron: 45 15 * * 1-5
"""
```

### Per-variant loop (for each `expiry_type, config` in `CONFIGS.items()`)

1. `positions = store.get_positions(config.strategy_name)` — skip if empty.
2. Fetch live chain: `UpstoxMarketClient(...).get_option_chain(...)` using the expiry
   parsed from any position's `instrument_key` (use `IronCondorV1._parse_expiry` pattern —
   instantiate the IC object and call the helper, or replicate the regex inline).
3. `events = await ic.check_signals(chain, positions)` — where `ic = IronCondorV1(broker, store, notifier, config)`.
4. Deduplicate: filter `events` against `store.get_open_exit_events(config.strategy_name)`.
   Skip any event whose `(strategy_name, leg_role, exit_signal)` triple already has an OPEN event.
5. For new ACTION events: `store.create_exit_event(...)`.
6. DTE alert: if DTE ≤ `config.dte_warn` emit a DTE INFO message in the report regardless of
   other signals.
7. Build and send Telegram message for this variant (see format below).

### Telegram report format (per variant, only sent when positions exist)

```
📊 IC Snapshot — monthly (paper_ic_nifty_v1_monthly)
DTE: 18  |  Nifty: 24,750  |  IVR: 0.42

Signals:
• DTE_WARN ℹ️  DTE 18 ≤ 21 — approaching expiry
• DELTA_WARN ⚠️  short_call |delta| 0.27 ≥ 0.25

No ACTION signals.
```

If ACTION signals exist:
```
🚨 IC Snapshot — weekly (paper_ic_nifty_v1_weekly)
DTE: 2  |  Nifty: 24,750

ACTION required:
• TIME_STOP 🔴  DTE 2 ≤ 2 — time stop triggered
  → Valid actions: CLOSE_FULL | CLOSE_CALL_SPREAD | CLOSE_PUT_SPREAD
```

If no open positions for this variant → skip entirely (no Telegram message).

### No open positions across all variants

If all four variants have zero positions → send one consolidated Telegram message:
`"IC Snapshot: no open IC positions across all expiry types."`

---

## Tests (`tests/unit/strategies/ic/test_paper_ic_snapshot.py`)

All offline. Mock chain fetch, `PaperStore`, `TelegramGateway`, `IronCondorV1.check_signals`.

**Happy-path tests:**
1. One variant has open positions → `check_signals` called once; Telegram message sent for that variant only.
2. All four variants have open positions → `check_signals` called four times; four Telegram messages sent.
3. ACTION signal for one variant → `store.create_exit_event` called; Telegram message includes "ACTION required" block.
4. Signal already OPEN in exit events → deduplicated; `create_exit_event` not called again.
5. DTE ≤ `config.dte_warn` → DTE INFO block included even when no other signals fire.

**Edge/error tests:**
6. No open positions across all variants → single "no open positions" Telegram message; `check_signals` never called.
7. Chain fetch fails for one variant → error logged; script continues to next variant; Telegram error note sent.
8. `check_signals` raises for one variant → caught; error logged; remaining variants processed.

---

## Commit

```
feat(scripts/ic): paper_ic_snapshot.py — EOD multi-expiry IC signal cron

Why: Four independent IC variants need daily exit signal monitoring;
ic-e2e IC-E4 spec superseded by multi-expiry design.
What:
- scripts/strategies/ic/paper_ic_snapshot.py: EOD cron iterating all CONFIGS
- tests/unit/strategies/ic/test_paper_ic_snapshot.py: 8 offline tests
Ref: ic-multi-expiry IC-M6
```

---

## Pre-baked Context

**`CONFIGS`** — `src.strategy.ic_expiry_config`. Keys in insertion order:
`"weekly"`, `"monthly"`, `"leaps"`, `"yearly"`.

**`store.get_positions(strategy_name)`** — returns `list[PaperPosition]`; empty list when
no open positions for that strategy_name.

**`store.get_open_exit_events(strategy_name)`** — returns `list[PaperExitEvent]` with
`status == "OPEN"`. Use to deduplicate before calling `create_exit_event`.

**`store.create_exit_event(...)`** — upsert by `(trade_id, exit_signal)`. See
`PaperStore` API in `CONTEXT.md` for full signature.

**`paper_3track_snapshot.py`** at `scripts/strategies/three_track/paper_3track_snapshot.py` —
reference for: structlog setup, `_SCRIPT_NAME` naming convention, exit signal deduplication
pattern, `_check_base_expiry()` DTE alert pattern, and Telegram send structure.
Use as structural reference only — the IC script does not need the overlay/base-expiry logic.

**Telegram HTML parse_mode** — `TelegramGateway` sends HTML; use `<b>`, `<i>`, `<code>` tags.
Emoji in message text is fine. Do not use markdown syntax.

**`_SCRIPT_NAME`** convention (per `CLAUDE.md` logging standard):
```python
_SCRIPT_NAME = "scripts.strategies.ic.paper_ic_snapshot"
logger = structlog.get_logger(_SCRIPT_NAME)
```
