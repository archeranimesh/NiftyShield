"""SQLite persistence for paper trading.

Two tables in the shared portfolio.sqlite DB:
  - paper_trades          — one row per simulated execution.
  - paper_nav_snapshots   — one row per (strategy, date) mark-to-market.

Both tables are isolated from live tables by a ``paper_`` prefix on
strategy_name (enforced at model layer) and by separate table names.
No foreign-key cross-references to the live tables are introduced here.

All monetary values stored as TEXT (Decimal invariant).  Timestamps stored
as UTC; IST conversion at display layer only.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

import structlog

from src.db import connect as _connect
from src.instruments.lookup import InstrumentLookup
from src.models.portfolio import TradeAction
from src.paper.constants import DEFAULT_BOD_PATH, NIFTYBEES_KEY
from src.paper.models import (
    ExitSignal,
    GateViolation,
    MarginSnapshot,
    OverlayPnLSnapshot,
    PaperLegSnapshot,
    PaperNavSnapshot,
    PaperPosition,
    PaperTrade,
    ProtectionRecoverySnapshot,
    TrackComparisonSnapshot,
    TradeState,
)
from src.strategy.profit_lock_engine import ProfitLockState

logger = structlog.get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_trades (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name  TEXT NOT NULL,
    leg_role       TEXT NOT NULL,
    instrument_key TEXT NOT NULL,
    trade_date     TEXT NOT NULL,
    action         TEXT NOT NULL,
    quantity       INTEGER NOT NULL,
    price          TEXT NOT NULL,
    notes          TEXT NOT NULL DEFAULT '',
    ivr_at_entry   REAL DEFAULT NULL,
    state          TEXT NOT NULL DEFAULT 'OPEN'
                       CHECK(state IN ('OPEN','DEFENDED','RE_ENTRY_PENDING','CLOSED')),
    UNIQUE(strategy_name, leg_role, instrument_key, trade_date, action)
);

CREATE INDEX IF NOT EXISTS idx_paper_trades_strategy_leg
    ON paper_trades(strategy_name, leg_role, trade_date);

CREATE TABLE IF NOT EXISTS paper_nav_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name     TEXT NOT NULL,
    snapshot_date     TEXT NOT NULL,
    unrealized_pnl    TEXT NOT NULL,
    realized_pnl      TEXT NOT NULL,
    total_pnl         TEXT NOT NULL,
    underlying_price  TEXT,
    UNIQUE(strategy_name, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_paper_nav_strategy_date
    ON paper_nav_snapshots(strategy_name, snapshot_date);

CREATE TABLE IF NOT EXISTS paper_proxy_delta_log (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name      TEXT NOT NULL,
    log_date           TEXT NOT NULL,
    delta              TEXT NOT NULL,
    is_below_threshold BOOLEAN NOT NULL,
    UNIQUE(strategy_name, log_date)
);

CREATE INDEX IF NOT EXISTS idx_paper_proxy_delta_log_strategy_date
    ON paper_proxy_delta_log(strategy_name, log_date);

CREATE TABLE IF NOT EXISTS paper_leg_snapshots (
    strategy_name  TEXT    NOT NULL,
    leg_role       TEXT    NOT NULL,
    snapshot_date  TEXT    NOT NULL,
    unrealized_pnl TEXT    NOT NULL,
    realized_pnl   TEXT    NOT NULL,
    total_pnl      TEXT    NOT NULL,
    ltp            TEXT,
    PRIMARY KEY (strategy_name, leg_role, snapshot_date)
) STRICT;

CREATE TABLE IF NOT EXISTS pending_approvals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name   TEXT    NOT NULL,
    event_type      TEXT    NOT NULL,
    council_output  TEXT    NOT NULL,   -- JSON blob (CouncilOutput serialised)
    status          TEXT    NOT NULL,   -- PENDING | APPROVED | REJECTED | EXPIRED
    approved_rank   INTEGER,            -- rank of the action the user approved (NULL until resolved)
    expires_at      TEXT    NOT NULL,   -- ISO UTC; set to +30 min at creation
    telegram_msg_id INTEGER,            -- message_id returned by Telegram API
    created_at      TEXT    NOT NULL,   -- ISO UTC
    resolved_at     TEXT                -- ISO UTC; NULL until APPROVED/REJECTED/EXPIRED
) STRICT;

CREATE TABLE IF NOT EXISTS council_outputs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    approval_id     INTEGER NOT NULL REFERENCES pending_approvals(id),
    persona         TEXT    NOT NULL,   -- "QuantAnalyst" | "SpecGuardian" | "RiskManager" | "OptionsStrategist" | "Chairman"
    model           TEXT    NOT NULL,   -- e.g. "deepseek/deepseek-r1-0528"
    prompt_tokens   INTEGER,
    output_tokens   INTEGER,
    latency_ms      INTEGER,
    response        TEXT    NOT NULL,   -- raw model response text
    created_at      TEXT    NOT NULL    -- ISO UTC
) STRICT;

CREATE TABLE IF NOT EXISTS daemon_heartbeat (
    id          INTEGER PRIMARY KEY CHECK (id = 1),   -- single-row table
    pid         INTEGER NOT NULL,
    last_beat   TEXT    NOT NULL,   -- ISO UTC; updated every monitor tick
    strategies  TEXT    NOT NULL,   -- JSON array of registered strategy_name strings
    last_event  TEXT                -- last SignalEvent.event_type seen; NULL if none yet
) STRICT;

CREATE INDEX IF NOT EXISTS idx_pending_approvals_status
    ON pending_approvals (status, strategy_name);

CREATE INDEX IF NOT EXISTS idx_council_outputs_approval
    ON council_outputs (approval_id);

CREATE TABLE IF NOT EXISTS paper_exit_events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name           TEXT    NOT NULL,
    leg_name                TEXT    NOT NULL,
    trade_id                TEXT    NOT NULL,
    snapshot_id             INTEGER,
    event_time              TEXT    NOT NULL,
    detected_by             TEXT    NOT NULL,
    exit_signal             TEXT    NOT NULL,
    severity                TEXT    NOT NULL,
    ltp                     TEXT,
    mid                     TEXT,
    bid                     TEXT,
    ask                     TEXT,
    delta                   REAL,
    dte                     INTEGER,
    entry_price             TEXT    NOT NULL,
    threshold_value         TEXT,
    delta_stop_would_fire   INTEGER,
    premium_stop_would_fire INTEGER,
    actual_rule_used        TEXT,
    counterfactual_dte_marks TEXT,
    status                  TEXT    NOT NULL DEFAULT 'OPEN',
    notes                   TEXT,
    created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_exit_events_strategy_leg
    ON paper_exit_events (strategy_name, leg_name, status);

CREATE INDEX IF NOT EXISTS idx_exit_events_trade
    ON paper_exit_events (trade_id, exit_signal);

CREATE INDEX IF NOT EXISTS idx_exit_events_open
    ON paper_exit_events (status, event_time)
    WHERE status = 'OPEN';

CREATE TABLE IF NOT EXISTS paper_action_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name   TEXT    NOT NULL,
    action_type     TEXT    NOT NULL,
    leg_role        TEXT    NOT NULL,
    price           TEXT    NOT NULL,   -- Decimal stored as TEXT
    qty             INTEGER NOT NULL,
    rationale       TEXT,
    executed_at     TEXT    NOT NULL    -- ISO UTC
) STRICT;

CREATE TABLE IF NOT EXISTS gate_violations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    gate_name       TEXT    NOT NULL,
    threshold       TEXT    NOT NULL,
    actual          TEXT    NOT NULL,
    strategy_name   TEXT    NOT NULL,
    logged_at       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gate_violations_strategy_gate
    ON gate_violations (strategy_name, gate_name);

CREATE TABLE IF NOT EXISTS paper_strategies (
    strategy_name            TEXT PRIMARY KEY,
    proxy_delta_breach_count INTEGER NOT NULL DEFAULT 0,
    profit_lock_zone         INTEGER NOT NULL DEFAULT 0,
    zone2_lock_executed      INTEGER NOT NULL DEFAULT 0,
    zone3_lock_executed      INTEGER NOT NULL DEFAULT 0,
    cumulative_lock_debit    TEXT    NOT NULL DEFAULT '0',
    active_put_width_pts     INTEGER NOT NULL DEFAULT 0,
    active_call_width_pts    INTEGER NOT NULL DEFAULT 0,
    cycle_id                 TEXT    NOT NULL DEFAULT ''
) STRICT;

CREATE TABLE IF NOT EXISTS paper_margin_snapshots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name    TEXT NOT NULL,
    entry_date       TEXT NOT NULL,
    required_margin  TEXT NOT NULL,
    final_margin     TEXT NOT NULL,
    captured_at      TEXT NOT NULL,
    UNIQUE(strategy_name, entry_date)
);

CREATE INDEX IF NOT EXISTS idx_paper_margin_snapshots_strategy_entry
    ON paper_margin_snapshots(strategy_name, entry_date);

CREATE TABLE IF NOT EXISTS paper_track_comparison_snapshots (
    strategy_name       TEXT NOT NULL,
    snapshot_date       TEXT NOT NULL,
    pnl_1d_abs          TEXT NOT NULL,
    pnl_1d_pct          TEXT NOT NULL,
    pnl_inception_abs   TEXT NOT NULL,
    pnl_inception_pct   TEXT NOT NULL,
    tracking_error_pct  TEXT,
    PRIMARY KEY (strategy_name, snapshot_date)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_paper_track_comparison_strategy_date
    ON paper_track_comparison_snapshots(strategy_name, snapshot_date);

CREATE TABLE IF NOT EXISTS paper_overlay_pnl_snapshots (
    strategy_name       TEXT NOT NULL,
    overlay_type        TEXT NOT NULL,
    snapshot_date       TEXT NOT NULL,
    pnl_1d_abs          TEXT NOT NULL,
    pnl_1d_pct          TEXT NOT NULL,
    pnl_inception_abs   TEXT NOT NULL,
    pnl_inception_pct   TEXT NOT NULL,
    PRIMARY KEY (strategy_name, overlay_type, snapshot_date)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_paper_overlay_pnl_strategy_type_date
    ON paper_overlay_pnl_snapshots(strategy_name, overlay_type, snapshot_date);

CREATE TABLE IF NOT EXISTS paper_protection_recovery_snapshots (
    snapshot_date                 TEXT NOT NULL,
    niftybees_pnl_1d              TEXT NOT NULL,
    cc_pnl_1d                     TEXT NOT NULL,
    pp_pnl_1d                     TEXT NOT NULL,
    collar_pnl_1d                 TEXT NOT NULL,
    niftybees_pnl_inception       TEXT NOT NULL,
    cc_pnl_inception              TEXT NOT NULL,
    pp_pnl_inception              TEXT NOT NULL,
    collar_pnl_inception          TEXT NOT NULL,
    best_overlay                  TEXT,
    best_recovery_pct             TEXT,
    best_overlay_inception        TEXT,
    best_recovery_pct_inception   TEXT,
    PRIMARY KEY (snapshot_date)
) STRICT;

CREATE TABLE IF NOT EXISTS warn_signal_state (
    strategy_name   TEXT    NOT NULL,
    event_type      TEXT    NOT NULL,
    leg_role        TEXT    NOT NULL,
    expiry          TEXT    NOT NULL DEFAULT '',
    active          INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT    NOT NULL,
    PRIMARY KEY (strategy_name, event_type, leg_role, expiry)
) STRICT;
"""


def _row_to_trade(row: sqlite3.Row) -> PaperTrade:
    return PaperTrade(
        strategy_name=row["strategy_name"],
        leg_role=row["leg_role"],
        instrument_key=row["instrument_key"],
        trade_date=date.fromisoformat(row["trade_date"]),
        action=TradeAction(row["action"]),
        quantity=row["quantity"],
        price=Decimal(row["price"]),
        notes=row["notes"],
        ivr_at_entry=row["ivr_at_entry"],
        state=TradeState(row["state"]) if row["state"] else TradeState.OPEN,
    )


def _row_to_leg_snapshot(row: sqlite3.Row) -> PaperLegSnapshot:
    return PaperLegSnapshot(
        strategy_name=row["strategy_name"],
        leg_role=row["leg_role"],
        snapshot_date=date.fromisoformat(row["snapshot_date"]),
        unrealized_pnl=Decimal(row["unrealized_pnl"]),
        realized_pnl=Decimal(row["realized_pnl"]),
        total_pnl=Decimal(row["total_pnl"]),
        ltp=Decimal(row["ltp"]) if row["ltp"] is not None else None,
    )


def _row_to_track_comparison_snapshot(row: sqlite3.Row) -> TrackComparisonSnapshot:
    return TrackComparisonSnapshot(
        strategy_name=row["strategy_name"],
        snapshot_date=date.fromisoformat(row["snapshot_date"]),
        pnl_1d_abs=Decimal(row["pnl_1d_abs"]),
        pnl_1d_pct=Decimal(row["pnl_1d_pct"]),
        pnl_inception_abs=Decimal(row["pnl_inception_abs"]),
        pnl_inception_pct=Decimal(row["pnl_inception_pct"]),
        tracking_error_pct=(
            Decimal(row["tracking_error_pct"]) if row["tracking_error_pct"] is not None else None
        ),
    )


def _row_to_overlay_pnl_snapshot(row: sqlite3.Row) -> OverlayPnLSnapshot:
    return OverlayPnLSnapshot(
        strategy_name=row["strategy_name"],
        overlay_type=row["overlay_type"],
        snapshot_date=date.fromisoformat(row["snapshot_date"]),
        pnl_1d_abs=Decimal(row["pnl_1d_abs"]),
        pnl_1d_pct=Decimal(row["pnl_1d_pct"]),
        pnl_inception_abs=Decimal(row["pnl_inception_abs"]),
        pnl_inception_pct=Decimal(row["pnl_inception_pct"]),
    )


def _row_to_protection_recovery_snapshot(row: sqlite3.Row) -> ProtectionRecoverySnapshot:
    return ProtectionRecoverySnapshot(
        snapshot_date=date.fromisoformat(row["snapshot_date"]),
        niftybees_pnl_1d=Decimal(row["niftybees_pnl_1d"]),
        cc_pnl_1d=Decimal(row["cc_pnl_1d"]),
        pp_pnl_1d=Decimal(row["pp_pnl_1d"]),
        collar_pnl_1d=Decimal(row["collar_pnl_1d"]),
        niftybees_pnl_inception=Decimal(row["niftybees_pnl_inception"]),
        cc_pnl_inception=Decimal(row["cc_pnl_inception"]),
        pp_pnl_inception=Decimal(row["pp_pnl_inception"]),
        collar_pnl_inception=Decimal(row["collar_pnl_inception"]),
        best_overlay=row["best_overlay"],
        best_recovery_pct=(
            Decimal(row["best_recovery_pct"]) if row["best_recovery_pct"] is not None else None
        ),
        best_overlay_inception=row["best_overlay_inception"],
        best_recovery_pct_inception=(
            Decimal(row["best_recovery_pct_inception"])
            if row["best_recovery_pct_inception"] is not None
            else None
        ),
    )


class PaperStore:
    """SQLite-backed store for paper trading records.

    Creates the paper_trades and paper_nav_snapshots tables on first
    instantiation if they do not exist.  Uses the shared portfolio.sqlite
    database via the src.db connection manager.

    Args:
        db_path: Path to the shared portfolio SQLite database.
    """

    def __init__(
        self,
        db_path: Path | str,
        instrument_lookup: InstrumentLookup | None = None,
    ) -> None:
        """Initialize store, creating tables if needed.

        Args:
            db_path: Path to SQLite database file (str or Path).
            instrument_lookup: Optional pre-built InstrumentLookup, used to
                resolve ``PaperPosition.option_type`` at read time. If not
                supplied, one is lazily constructed from ``DEFAULT_BOD_PATH``
                on first call to `get_position`/`get_positions` (mirrors the
                ``lookup: InstrumentLookup | None = None`` pattern used
                elsewhere, e.g. `src/strategy/csp_nifty_v1.py`).
        """
        self._instrument_lookup = instrument_lookup
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with _connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)
            # Migration: add ivr_at_entry to paper_trades if missing
            try:
                conn.execute("ALTER TABLE paper_trades ADD COLUMN ivr_at_entry REAL DEFAULT NULL")
            except sqlite3.OperationalError:
                pass  # Column already exists
            # Migration: add state to paper_trades if missing
            try:
                conn.execute(
                    "ALTER TABLE paper_trades ADD COLUMN state TEXT NOT NULL DEFAULT 'OPEN'"
                    " CHECK(state IN ('OPEN','DEFENDED','RE_ENTRY_PENDING'))"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            # Migration: add profit_lock fields to paper_strategies (each column independent)
            for _ddl in (
                "ALTER TABLE paper_strategies ADD COLUMN profit_lock_zone INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE paper_strategies ADD COLUMN zone2_lock_executed INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE paper_strategies ADD COLUMN zone3_lock_executed INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE paper_strategies ADD COLUMN cumulative_lock_debit TEXT NOT NULL DEFAULT '0'",
                "ALTER TABLE paper_strategies ADD COLUMN active_put_width_pts INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE paper_strategies ADD COLUMN active_call_width_pts INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE paper_strategies ADD COLUMN cycle_id TEXT NOT NULL DEFAULT ''",
                # BUG-020 Phase 1: original 4-leg entry credit, captured atomically at
                # entry, so profit-target/loss-stop branches don't re-scope to whatever
                # legs happen to still be open after a partial close. NULL until an
                # entry populates it (Phase 2) — read side must treat NULL as "unknown,
                # fall back to today's recompute" (Phase 3), not as zero.
                "ALTER TABLE paper_strategies ADD COLUMN original_entry_credit TEXT DEFAULT NULL",
            ):
                try:
                    conn.execute(_ddl)
                except sqlite3.OperationalError:
                    pass  # Column already exists
            # Migration: add instrument_key to UNIQUE constraint (BUG-4)
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='paper_trades'"
            ).fetchone()
            if row and "instrument_key, trade_date" not in row[0]:
                conn.executescript(
                    """
                    PRAGMA foreign_keys = OFF;
                    BEGIN;
                    CREATE TABLE paper_trades_new (
                        id             INTEGER PRIMARY KEY AUTOINCREMENT,
                        strategy_name  TEXT NOT NULL,
                        leg_role       TEXT NOT NULL,
                        instrument_key TEXT NOT NULL,
                        trade_date     TEXT NOT NULL,
                        action         TEXT NOT NULL,
                        quantity       INTEGER NOT NULL,
                        price          TEXT NOT NULL,
                        notes          TEXT NOT NULL DEFAULT '',
                        ivr_at_entry   REAL DEFAULT NULL,
                        state          TEXT NOT NULL DEFAULT 'OPEN'
                                           CHECK(state IN ('OPEN','DEFENDED','RE_ENTRY_PENDING','CLOSED')),
                        UNIQUE(strategy_name, leg_role, instrument_key, trade_date, action)
                    );
                    INSERT OR IGNORE INTO paper_trades_new
                        SELECT id, strategy_name, leg_role, instrument_key, trade_date,
                               action, quantity, price, notes, ivr_at_entry, state
                        FROM paper_trades;
                    DROP TABLE paper_trades;
                    ALTER TABLE paper_trades_new RENAME TO paper_trades;
                    CREATE INDEX IF NOT EXISTS idx_paper_trades_strategy_leg
                        ON paper_trades(strategy_name, leg_role, trade_date);
                    COMMIT;
                    PRAGMA foreign_keys = ON;
                    """
                )

    # ── Trades ledger ─────────────────────────────────────────────────────────

    def record_trade(self, trade: PaperTrade) -> bool:
        """Insert a paper trade into the ledger. Silently skips exact duplicates.

        Uniqueness is on (strategy_name, leg_role, instrument_key, trade_date, action).
        Re-running record_paper_trade.py with the same args is always safe.

        Args:
            trade: The paper trade to persist.

        Returns:
            True if the row was inserted; False if skipped as a duplicate.
        """
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO paper_trades
                   (strategy_name, leg_role, instrument_key, trade_date,
                    action, quantity, price, notes, ivr_at_entry, state)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(strategy_name, leg_role, instrument_key, trade_date, action)
                   DO NOTHING""",
                (
                    trade.strategy_name,
                    trade.leg_role,
                    trade.instrument_key,
                    trade.trade_date.isoformat(),
                    trade.action.value,
                    trade.quantity,
                    str(trade.price),
                    trade.notes,
                    trade.ivr_at_entry,
                    trade.state.value,
                ),
            )
            return cur.rowcount == 1

    def record_trades(self, trades: list[PaperTrade]) -> tuple[list[PaperTrade], list[PaperTrade]]:
        """Insert multiple paper trades in a single atomic transaction.

        Silently skips exact duplicates (based on the unique constraint).
        If any trade insertion raises an error, the entire batch is rolled back.

        Args:
            trades: List of PaperTrade objects to persist.

        Returns:
            A tuple of (inserted_trades, skipped_trades).
        """
        inserted_trades: list[PaperTrade] = []
        skipped_trades: list[PaperTrade] = []
        with _connect(self.db_path) as conn:
            for trade in trades:
                cur = conn.execute(
                    """INSERT INTO paper_trades
                       (strategy_name, leg_role, instrument_key, trade_date,
                        action, quantity, price, notes, ivr_at_entry, state)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(strategy_name, leg_role, instrument_key, trade_date, action)
                       DO NOTHING""",
                    (
                        trade.strategy_name,
                        trade.leg_role,
                        trade.instrument_key,
                        trade.trade_date.isoformat(),
                        trade.action.value,
                        trade.quantity,
                        str(trade.price),
                        trade.notes,
                        trade.ivr_at_entry,
                        trade.state.value,
                    ),
                )
                if cur.rowcount == 1:
                    inserted_trades.append(trade)
                else:
                    skipped_trades.append(trade)
        return inserted_trades, skipped_trades

    def update_trade_state(self, trade_id: int, state: TradeState) -> None:
        """Update the lifecycle state of an existing paper trade.

        Args:
            trade_id: Primary key of the paper_trades row to update.
            state: New TradeState value to persist.

        Raises:
            ValueError: If no trade with the given trade_id exists.
        """
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE paper_trades SET state = ? WHERE id = ?",
                (state.value, trade_id),
            )
            if cur.rowcount == 0:
                raise ValueError(f"No paper trade found with id={trade_id}")

    def mark_trade_closed(
        self,
        strategy_name: str,
        leg_role: str,
        instrument_key: str,
    ) -> None:
        """Transition the opening trade for a leg to CLOSED state.

        Called after a close trade has been successfully recorded to prevent
        the position from re-appearing in signal evaluation on the next tick.
        Only transitions rows currently in OPEN or DEFENDED state — does not
        touch RE_ENTRY_PENDING or already-CLOSED rows.

        Args:
            strategy_name: Strategy that owns the trade.
            leg_role: Leg role identifier (e.g. ``overlay_cc``).
            instrument_key: Instrument key of the position being closed.
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                """UPDATE paper_trades SET state = 'CLOSED'
                   WHERE strategy_name = ? AND leg_role = ? AND instrument_key = ?
                   AND state IN ('OPEN', 'DEFENDED')""",
                (strategy_name, leg_role, instrument_key),
            )

    def mark_trade_defended(
        self,
        strategy_name: str,
        leg_role: str,
        instrument_key: str,
    ) -> None:
        """Transition an OPEN trade to DEFENDED state after a defensive roll.

        Called by ``CSPNiftyV1._roll_down`` after a successful roll_down_and_out
        so that the next delta breach escalates to DELTA_BREACH_FINAL instead
        of firing another ROLL_DOWN_AND_OUT.  No-op if the row is not OPEN.

        Args:
            strategy_name: Strategy that owns the trade.
            leg_role: Leg role identifier.
            instrument_key: Instrument key of the newly-opened rolled position.
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                """UPDATE paper_trades SET state = 'DEFENDED'
                   WHERE strategy_name = ? AND leg_role = ? AND instrument_key = ?
                   AND state = 'OPEN'""",
                (strategy_name, leg_role, instrument_key),
            )

    def get_trade_state(
        self,
        strategy_name: str,
        leg_role: str,
    ) -> TradeState:
        """Return the lifecycle state of the currently open trade for a leg.

        Queries the most recent non-CLOSED SELL trade for the given
        (strategy_name, leg_role) pair.  Defaults to ``TradeState.OPEN``
        when no active trade exists (safe fallback — never blocks an evaluation).

        Args:
            strategy_name: Strategy that owns the trade.
            leg_role: Leg role identifier (e.g. ``short_put``).

        Returns:
            Current TradeState for the active trade; ``TradeState.OPEN``
            when no non-CLOSED trade is found.
        """
        with _connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT state FROM paper_trades
                   WHERE strategy_name = ? AND leg_role = ?
                   AND action = 'SELL'
                   AND state NOT IN ('CLOSED')
                   ORDER BY trade_date DESC, id DESC LIMIT 1""",
                (strategy_name, leg_role),
            ).fetchone()
        if row is None:
            return TradeState.OPEN
        return TradeState(row["state"])

    def get_trades(
        self,
        strategy_name: str,
        leg_role: str | None = None,
    ) -> list[PaperTrade]:
        """Return paper trades for a strategy, optionally filtered by leg_role.

        Args:
            strategy_name: Strategy to fetch trades for.
            leg_role: If provided, filter to this leg only.

        Returns:
            List of PaperTrade ordered by trade_date ASC.
        """
        with _connect(self.db_path) as conn:
            if leg_role is not None:
                rows = conn.execute(
                    "SELECT strategy_name, leg_role, instrument_key, trade_date,"
                    " action, quantity, price, notes, ivr_at_entry, state"
                    " FROM paper_trades"
                    " WHERE strategy_name = ? AND leg_role = ?"
                    " ORDER BY trade_date ASC, id ASC",
                    (strategy_name, leg_role),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT strategy_name, leg_role, instrument_key, trade_date,"
                    " action, quantity, price, notes, ivr_at_entry, state"
                    " FROM paper_trades"
                    " WHERE strategy_name = ?"
                    " ORDER BY trade_date ASC, id ASC",
                    (strategy_name,),
                ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def get_positions(self, strategy_name: str) -> list[PaperPosition]:
        """Compute net open positions for all (leg, instrument) pairs of a strategy.

        Grouped by ``(leg_role, instrument_key)`` — not ``leg_role`` alone — so a
        SELL that closes an expiring contract during a roll never nets against
        the BUY that opened the replacement contract (PG-1; see
        docs/plan/paper-store-position-granularity/). ``delete_trade()`` already
        scopes its WHERE clause to ``instrument_key``; this keeps the same
        granularity. Callers that assumed one position per ``leg_role`` must be
        updated to iterate all returned positions (PG-2).

        Args:
            strategy_name: Paper strategy name.

        Returns:
            One PaperPosition per (leg_role, instrument_key) pair with a
            non-zero net quantity. Flat pairs are excluded.
        """
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT leg_role, action, quantity, price, instrument_key, trade_date"
                " FROM paper_trades"
                " WHERE strategy_name = ?"
                " ORDER BY trade_date ASC, id ASC",
                (strategy_name,),
            ).fetchall()

        if not rows:
            return []

        instrument_rows = defaultdict(list)
        for row in rows:
            instrument_rows[(row["leg_role"], row["instrument_key"])].append(row)

        positions = []
        for (leg_role, group_instrument_key), rows_for_instrument in instrument_rows.items():
            net_qty = 0
            buy_total_qty = 0
            buy_total_cost = Decimal("0")
            sell_total_qty = 0
            sell_total_cost = Decimal("0")
            # DBI-3: track the opening trade of the current cycle (after net_qty last hit 0).
            # cycle_start_date: entry date regardless of BUY/SELL action (fixes long-first legs).
            # cycle_instrument_key: always group_instrument_key now — each group is already
            # scoped to a single instrument (PG-1), so no roll can occur within a group.
            cycle_start_date: date | None = None
            cycle_instrument_key: str = group_instrument_key

            for row in rows_for_instrument:
                qty = row["quantity"]
                price = Decimal(row["price"])
                raw_date = row["trade_date"]
                trade_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date

                # New cycle: net_qty was flat going into this trade — record the opener.
                if net_qty == 0:
                    cycle_start_date = trade_date
                    cycle_instrument_key = row["instrument_key"]
                    buy_total_qty = 0
                    buy_total_cost = Decimal("0")
                    sell_total_qty = 0
                    sell_total_cost = Decimal("0")

                if TradeAction(row["action"]) == TradeAction.BUY:
                    net_qty += qty
                    buy_total_qty += qty
                    buy_total_cost += price * qty
                else:
                    net_qty -= qty
                    sell_total_qty += qty
                    sell_total_cost += price * qty

            if net_qty == 0:
                continue

            avg_cost = buy_total_cost / buy_total_qty if buy_total_qty > 0 else Decimal("0")
            avg_sell_price = (
                sell_total_cost / sell_total_qty if sell_total_qty > 0 else Decimal("0")
            )

            positions.append(
                PaperPosition(
                    strategy_name=strategy_name,
                    leg_role=leg_role,
                    net_qty=net_qty,
                    avg_cost=avg_cost,
                    avg_sell_price=avg_sell_price,
                    instrument_key=cycle_instrument_key,
                    entry_date=cycle_start_date,
                    # BUG-014: flat (net_qty == 0) groups are filtered out above, so
                    # every position reaching here is live and safe to resolve. A
                    # closed group's instrument_key would reference a settled/delisted
                    # contract that can never resolve again once it drops out of the
                    # BOD file — resolving it would produce a permanent, unactionable
                    # warning on every snapshot run, which is why it's excluded rather
                    # than resolved-and-discarded.
                    option_type=self._resolve_option_type(cycle_instrument_key),
                )
            )
        return positions

    def get_position(
        self,
        strategy_name: str,
        leg_role: str,
        instrument_key: str | None = None,
    ) -> PaperPosition:
        """Compute net open position for a leg from the paper_trades ledger.

        Net quantity = SUM(BUY qty) - SUM(SELL qty).
        Average cost = weighted average of BUY prices only (SELL prices excluded,
        consistent with live PortfolioStore.get_position semantics).

        Post-PG-1, ``get_positions()`` can return multiple rows sharing a
        ``leg_role`` during a roll overlap (old contract not yet fully closed,
        new contract already open). Resolution order (PG-2a):

        - ``instrument_key`` given: filter to that exact ``(leg_role,
          instrument_key)`` pair; fall through to the flat-position default if
          no match.
        - ``instrument_key`` is ``None`` and exactly one position matches
          ``leg_role``: return it (unchanged pre-PG-2a behavior).
        - ``instrument_key`` is ``None`` and more than one position matches
          ``leg_role``: pick the one with the most recent ``entry_date`` and
          log a WARNING — callers not yet updated to pass ``instrument_key``
          get a visible signal instead of a silent, iteration-order-dependent
          guess. See docs/plan/paper-store-position-granularity/stories.md
          PG-2a.

        Args:
            strategy_name: Paper strategy name.
            leg_role: Leg identifier within the strategy.
            instrument_key: Optional Upstox instrument key to disambiguate
                between multiple open positions sharing ``leg_role``.

        Returns:
            PaperPosition with net_qty=0 and avg_cost=Decimal("0") if no
            matching trades exist.
        """
        flat_default = PaperPosition(
            strategy_name=strategy_name,
            leg_role=leg_role,
            net_qty=0,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("0"),
            instrument_key="",
            option_type=None,
        )

        matches = [p for p in self.get_positions(strategy_name) if p.leg_role == leg_role]

        if instrument_key is not None:
            for p in matches:
                if p.instrument_key == instrument_key:
                    return p
            return flat_default

        if not matches:
            return flat_default
        if len(matches) == 1:
            return matches[0]

        logger.warning(
            "paper_store.get_position_ambiguous",
            strategy_name=strategy_name,
            leg_role=leg_role,
            match_count=len(matches),
        )
        return max(matches, key=lambda p: p.entry_date or date.min)

    def _resolve_instrument_lookup(self) -> InstrumentLookup | None:
        """Lazily construct and cache the InstrumentLookup used for option_type resolution.

        Not called from `__init__` — BOD JSON is only loaded on first actual need
        (`get_position`/`get_positions`), consistent with the lazy-resolution
        decision for B002.3 (read-time, not write-time).

        `option_type` is a read-time classification signal, not a hard gate: a
        missing, truncated, or corrupt BOD file must never take down position
        reads (`get_position`/`get_positions` had zero dependency on this file
        before B002.3, and callers like monitor/executor/snapshot scripts must
        keep working even if the BOD download job failed). Failure is logged
        and `None` is returned so callers degrade to `option_type=None` for the
        batch rather than raising. The failure is not cached, so a subsequent
        call can pick up the file once it becomes available again.

        Not thread-safe: concurrent calls on the same PaperStore instance can
        both pass the "is None" check and construct duplicate InstrumentLookup
        objects (wasteful, not corrupting — last write wins). Construct one
        PaperStore per thread/process, or inject a shared InstrumentLookup via
        the constructor, if this is ever used from a threaded/async context.
        """
        if self._instrument_lookup is None:
            try:
                self._instrument_lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
            except (OSError, ValueError) as exc:
                # OSError covers FileNotFoundError/gzip's BadGzipFile/EOFError;
                # ValueError covers json.JSONDecodeError.
                logger.warning(
                    "instrument_lookup_load_failed",
                    bod_path=str(DEFAULT_BOD_PATH),
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                return None
        return self._instrument_lookup

    def _resolve_option_type(self, instrument_key: str) -> Literal["PE", "CE", "FUT", "EQ"] | None:
        """Classify an instrument_key as PE/CE/FUT/EQ for PaperPosition.option_type.

        NiftyBees short-circuits to "EQ" without a lookup. Everything else is
        resolved via `InstrumentLookup.get_by_key`: CE/PE/FUT pass through
        as-is; any other resolved `instrument_type` (e.g. "EQ", "INDEX") or an
        unresolved key logs a warning and returns None rather than raising or
        mis-labelling — this is a read-time classification signal, not a hard
        gate.

        Args:
            instrument_key: Upstox instrument key from the open position.

        Returns:
            "PE" / "CE" / "FUT" / "EQ", or None if the key could not be
            resolved or classified (BOD file unavailable, key not found, or
            resolved type is not one of CE/PE/FUT).
        """
        if instrument_key == NIFTYBEES_KEY:
            return "EQ"

        lookup = self._resolve_instrument_lookup()
        if lookup is None:
            return None

        inst = lookup.get_by_key(instrument_key)
        if inst is None:
            logger.warning(
                "option_type_resolution_failed",
                instrument_key=instrument_key,
                reason="instrument_key not found in BOD JSON",
            )
            return None

        instrument_type = inst.get("instrument_type")
        if instrument_type in ("CE", "PE", "FUT"):
            return cast(Literal["CE", "PE", "FUT"], instrument_type)

        logger.warning(
            "option_type_resolution_unrecognised_type",
            instrument_key=instrument_key,
            instrument_type=instrument_type,
            reason="resolved instrument_type is not CE/PE/FUT",
        )
        return None

    # ── NAV snapshots ─────────────────────────────────────────────────────────

    def record_nav_snapshot(self, snapshot: PaperNavSnapshot) -> None:
        """Upsert a daily NAV snapshot for a paper strategy.

        Asserts ``snapshot.total_pnl == snapshot.unrealized_pnl +
        snapshot.realized_pnl`` before writing. Raises ``ValueError`` on
        mismatch — same invariant class enforced by ``record_leg_snapshot``
        (added SNAP-5, 2026-08-07, after 42/267 historical rows were found
        with a drifted total_pnl — see docs/plan/paper-ic-daily-snapshot/
        stories.md SNAP-5).

        ON CONFLICT UPDATE replaces the row if the same (strategy_name,
        snapshot_date) already exists — idempotent re-runs are safe.

        Args:
            snapshot: The PaperNavSnapshot to persist.

        Raises:
            ValueError: If total_pnl != unrealized_pnl + realized_pnl.
        """
        expected = snapshot.unrealized_pnl + snapshot.realized_pnl
        if snapshot.total_pnl != expected:
            raise ValueError(
                f"PaperNavSnapshot total_pnl invariant violated: "
                f"total_pnl={snapshot.total_pnl} but "
                f"unrealized_pnl + realized_pnl={expected} "
                f"(strategy={snapshot.strategy_name!r}, "
                f"snapshot_date={snapshot.snapshot_date!r})"
            )
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO paper_nav_snapshots
                   (strategy_name, snapshot_date, unrealized_pnl,
                    realized_pnl, total_pnl, underlying_price)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(strategy_name, snapshot_date)
                   DO UPDATE SET
                       unrealized_pnl   = excluded.unrealized_pnl,
                       realized_pnl     = excluded.realized_pnl,
                       total_pnl        = excluded.total_pnl,
                       underlying_price = excluded.underlying_price""",
                (
                    snapshot.strategy_name,
                    snapshot.snapshot_date.isoformat(),
                    str(snapshot.unrealized_pnl),
                    str(snapshot.realized_pnl),
                    str(snapshot.total_pnl),
                    str(snapshot.underlying_price)
                    if snapshot.underlying_price is not None
                    else None,
                ),
            )

    def get_nav_snapshots(
        self,
        strategy_name: str,
    ) -> list[PaperNavSnapshot]:
        """Return all NAV snapshots for a strategy, ordered by date ASC.

        Args:
            strategy_name: Paper strategy to fetch snapshots for.

        Returns:
            List of PaperNavSnapshot ordered by snapshot_date ASC.
        """
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT strategy_name, snapshot_date, unrealized_pnl,"
                " realized_pnl, total_pnl, underlying_price"
                " FROM paper_nav_snapshots"
                " WHERE strategy_name = ?"
                " ORDER BY snapshot_date ASC",
                (strategy_name,),
            ).fetchall()

        return [
            PaperNavSnapshot(
                strategy_name=r["strategy_name"],
                snapshot_date=date.fromisoformat(r["snapshot_date"]),
                unrealized_pnl=Decimal(r["unrealized_pnl"]),
                realized_pnl=Decimal(r["realized_pnl"]),
                total_pnl=Decimal(r["total_pnl"]),
                underlying_price=(
                    Decimal(r["underlying_price"]) if r["underlying_price"] is not None else None
                ),
            )
            for r in rows
        ]

    def get_latest_nav_snapshot(
        self,
        strategy_name: str,
    ) -> PaperNavSnapshot | None:
        """Return the most recent NAV snapshot for a strategy.

        Args:
            strategy_name: Paper strategy name.

        Returns:
            Most recent PaperNavSnapshot, or None if no snapshots exist.
        """
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT strategy_name, snapshot_date, unrealized_pnl,"
                " realized_pnl, total_pnl, underlying_price"
                " FROM paper_nav_snapshots"
                " WHERE strategy_name = ?"
                " ORDER BY snapshot_date DESC LIMIT 1",
                (strategy_name,),
            ).fetchone()

        if row is None:
            return None

        return PaperNavSnapshot(
            strategy_name=row["strategy_name"],
            snapshot_date=date.fromisoformat(row["snapshot_date"]),
            unrealized_pnl=Decimal(row["unrealized_pnl"]),
            realized_pnl=Decimal(row["realized_pnl"]),
            total_pnl=Decimal(row["total_pnl"]),
            underlying_price=(
                Decimal(row["underlying_price"]) if row["underlying_price"] is not None else None
            ),
        )

    def get_strategy_names(self) -> list[str]:
        """Return distinct paper strategy names that have at least one trade.

        Returns:
            Sorted list of strategy_name strings.
        """
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT strategy_name FROM paper_trades ORDER BY strategy_name"
            ).fetchall()
        return [r["strategy_name"] for r in rows]

    # ── Proxy Delta Log ───────────────────────────────────────────────────────

    def record_proxy_delta_log(
        self, strategy_name: str, log_date: date, delta: Decimal, is_below_threshold: bool
    ) -> None:
        """Record the daily delta value and threshold status for a proxy strategy.

        Args:
            strategy_name: Strategy name (e.g., 'paper_nifty_proxy').
            log_date: The date of the snapshot.
            delta: The current delta value.
            is_below_threshold: True if delta < 0.40.
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO paper_proxy_delta_log
                   (strategy_name, log_date, delta, is_below_threshold)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(strategy_name, log_date)
                   DO UPDATE SET
                       delta              = excluded.delta,
                       is_below_threshold = excluded.is_below_threshold""",
                (
                    strategy_name,
                    log_date.isoformat(),
                    str(delta),
                    1 if is_below_threshold else 0,
                ),
            )

    def get_proxy_delta_consecutive_days(self, strategy_name: str, current_date: date) -> int:
        """Get the number of consecutive trading days where delta was below threshold.

        Counts backward from current_date. Stops if there's a gap of more than
        3 calendar days between two entries, implying a break in the sequence.

        Args:
            strategy_name: Strategy name.
            current_date: The date to start counting backwards from.

        Returns:
            Number of consecutive days immediately preceding (and including)
            current_date where is_below_threshold was True.
        """
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT log_date, is_below_threshold "
                "FROM paper_proxy_delta_log "
                "WHERE strategy_name = ? AND log_date <= ? "
                "ORDER BY log_date DESC",
                (strategy_name, current_date.isoformat()),
            ).fetchall()

        consecutive = 0
        last_date = None
        for row in rows:
            row_date = date.fromisoformat(row["log_date"])
            if last_date is not None:
                if (last_date - row_date).days > 3:
                    break

            if row["is_below_threshold"]:
                consecutive += 1
                last_date = row_date
            else:
                break

        return consecutive

    def get_proxy_delta_breach_count(self, strategy_name: str) -> int:
        """Return the number of consecutive trading days the Proxy delta has been below
        _PROXY_DELTA_CRITICAL (0.40). Returns 0 if no record exists.

        Args:
            strategy_name: Strategy namespace (e.g. 'paper_nifty_proxy').

        Returns:
            Non-negative integer.
        """
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT proxy_delta_breach_count FROM paper_strategies WHERE strategy_name = ?",
                (strategy_name,),
            ).fetchone()
        if row is None:
            return 0
        return int(row["proxy_delta_breach_count"])

    def set_proxy_delta_breach_count(self, strategy_name: str, count: int) -> None:
        """Persist the consecutive Proxy delta breach count.
        Resets to 0 when delta recovers above _PROXY_DELTA_CRITICAL.

        Args:
            strategy_name: Strategy namespace.
            count: New breach count (0 to reset, N to increment).
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO paper_strategies (strategy_name, proxy_delta_breach_count)
                   VALUES (?, ?)
                   ON CONFLICT(strategy_name)
                   DO UPDATE SET proxy_delta_breach_count = excluded.proxy_delta_breach_count""",
                (strategy_name, count),
            )

    def get_profit_lock_state(self, strategy_name: str) -> ProfitLockState:
        """Return current profit-lock state; inserts default row if missing."""
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT profit_lock_zone, zone2_lock_executed, zone3_lock_executed, "
                "cumulative_lock_debit, active_put_width_pts, active_call_width_pts, cycle_id "
                "FROM paper_strategies WHERE strategy_name = ?",
                (strategy_name,),
            ).fetchone()

            if row is None:
                conn.execute(
                    "INSERT INTO paper_strategies (strategy_name) VALUES (?)", (strategy_name,)
                )
                return ProfitLockState(
                    profit_lock_zone=0,
                    zone2_lock_executed=False,
                    zone3_lock_executed=False,
                    cumulative_lock_debit_pts=Decimal("0"),
                    active_put_width_pts=0,
                    active_call_width_pts=0,
                    cycle_id="",
                )

            return ProfitLockState(
                profit_lock_zone=row["profit_lock_zone"],
                zone2_lock_executed=bool(row["zone2_lock_executed"]),
                zone3_lock_executed=bool(row["zone3_lock_executed"]),
                cumulative_lock_debit_pts=Decimal(row["cumulative_lock_debit"]),
                active_put_width_pts=row["active_put_width_pts"],
                active_call_width_pts=row["active_call_width_pts"],
                cycle_id=row["cycle_id"],
            )

    def set_profit_lock_state(self, strategy_name: str, state: ProfitLockState) -> None:
        """Upsert all profit-lock state fields atomically."""
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO paper_strategies (
                       strategy_name, profit_lock_zone, zone2_lock_executed, zone3_lock_executed,
                       cumulative_lock_debit, active_put_width_pts, active_call_width_pts, cycle_id
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(strategy_name) DO UPDATE SET
                       profit_lock_zone = excluded.profit_lock_zone,
                       zone2_lock_executed = excluded.zone2_lock_executed,
                       zone3_lock_executed = excluded.zone3_lock_executed,
                       cumulative_lock_debit = excluded.cumulative_lock_debit,
                       active_put_width_pts = excluded.active_put_width_pts,
                       active_call_width_pts = excluded.active_call_width_pts,
                       cycle_id = excluded.cycle_id""",
                (
                    strategy_name,
                    state.profit_lock_zone,
                    1 if state.zone2_lock_executed else 0,
                    1 if state.zone3_lock_executed else 0,
                    str(state.cumulative_lock_debit_pts),
                    state.active_put_width_pts,
                    state.active_call_width_pts,
                    state.cycle_id,
                ),
            )

    def set_original_entry_credit(self, strategy_name: str, original_entry_credit: Decimal) -> None:
        """Persist the original 4-leg entry credit for one strategy's current cycle.

        BUG-020 Phase 1/2: captured atomically at entry so the profit-target/
        loss-stop branches can reference the basket's original economics
        instead of recomputing from whatever legs are still open after a
        partial close. Upserts into the same ``paper_strategies`` row used by
        profit-lock state — one row per strategy_name, not per cycle, so a
        new entry's call here overwrites the prior cycle's value.

        Args:
            strategy_name: Strategy identifier, e.g. ``paper_ic_nifty_v2_monthly``.
            original_entry_credit: Net credit at entry, index points per unit.
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO paper_strategies (strategy_name, original_entry_credit)
                   VALUES (?, ?)
                   ON CONFLICT(strategy_name) DO UPDATE SET
                       original_entry_credit = excluded.original_entry_credit""",
                (strategy_name, str(original_entry_credit)),
            )

    def get_original_entry_credit(self, strategy_name: str) -> Decimal | None:
        """Return the persisted original entry credit, or None if never recorded.

        BUG-020 Phase 1: read-only counterpart to ``set_original_entry_credit``.
        Returns None both when the strategy has no ``paper_strategies`` row yet
        and when the row exists but the column is still NULL (pre-Phase-2
        positions, or a strategy that has never called the setter) — callers
        must treat None as "fall back to recompute", never as zero credit.

        Args:
            strategy_name: Strategy identifier, e.g. ``paper_ic_nifty_v2_monthly``.

        Returns:
            The persisted Decimal credit, or None if unknown.
        """
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT original_entry_credit FROM paper_strategies WHERE strategy_name = ?",
                (strategy_name,),
            ).fetchone()
            if row is None or row["original_entry_credit"] is None:
                return None
            return Decimal(row["original_entry_credit"])

    def reset_profit_lock_state(self, strategy_name: str, cycle_id: str) -> None:
        """Reset all fields to defaults for a new entry cycle."""
        default_state = ProfitLockState(
            profit_lock_zone=0,
            zone2_lock_executed=False,
            zone3_lock_executed=False,
            cumulative_lock_debit_pts=Decimal("0"),
            active_put_width_pts=0,
            active_call_width_pts=0,
            cycle_id=cycle_id,
        )
        self.set_profit_lock_state(strategy_name, default_state)

    # ── Leg snapshots ─────────────────────────────────────────────────────────

    def record_leg_snapshot(self, snap: PaperLegSnapshot) -> None:
        """Upsert a per-leg daily P&L snapshot.

        Asserts ``snap.total_pnl == snap.unrealized_pnl + snap.realized_pnl``
        before writing. Raises ``ValueError`` on mismatch — same invariant
        class as the Decimal-as-TEXT rule.

        ON CONFLICT UPDATE replaces the row if the same
        (strategy_name, leg_role, snapshot_date) already exists — idempotent
        re-runs are safe.

        Args:
            snap: The PaperLegSnapshot to persist.

        Raises:
            ValueError: If total_pnl != unrealized_pnl + realized_pnl.
        """
        expected = snap.unrealized_pnl + snap.realized_pnl
        if snap.total_pnl != expected:
            raise ValueError(
                f"PaperLegSnapshot total_pnl invariant violated: "
                f"total_pnl={snap.total_pnl} but "
                f"unrealized_pnl + realized_pnl={expected} "
                f"(strategy={snap.strategy_name!r}, leg_role={snap.leg_role!r})"
            )
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO paper_leg_snapshots
                   (strategy_name, leg_role, snapshot_date, unrealized_pnl,
                    realized_pnl, total_pnl, ltp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(strategy_name, leg_role, snapshot_date)
                   DO UPDATE SET
                       unrealized_pnl = excluded.unrealized_pnl,
                       realized_pnl   = excluded.realized_pnl,
                       total_pnl      = excluded.total_pnl,
                       ltp            = excluded.ltp""",
                (
                    snap.strategy_name,
                    snap.leg_role,
                    snap.snapshot_date.isoformat(),
                    str(snap.unrealized_pnl),
                    str(snap.realized_pnl),
                    str(snap.total_pnl),
                    str(snap.ltp) if snap.ltp is not None else None,
                ),
            )

    def get_leg_snapshot(
        self,
        strategy_name: str,
        leg_role: str,
        snap_date: date,
    ) -> PaperLegSnapshot | None:
        """Return the leg snapshot for a specific (strategy, leg, date), or None.

        Args:
            strategy_name: Paper strategy name.
            leg_role: Leg identifier within the strategy.
            snap_date: Exact snapshot date to look up.

        Returns:
            The matching PaperLegSnapshot, or None if not found.
        """
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT strategy_name, leg_role, snapshot_date, unrealized_pnl,"
                " realized_pnl, total_pnl, ltp"
                " FROM paper_leg_snapshots"
                " WHERE strategy_name = ? AND leg_role = ? AND snapshot_date = ?",
                (strategy_name, leg_role, snap_date.isoformat()),
            ).fetchone()

        if row is None:
            return None
        return _row_to_leg_snapshot(row)

    def get_prev_leg_snapshot(
        self,
        strategy_name: str,
        leg_role: str,
        before_date: date,
    ) -> PaperLegSnapshot | None:
        """Return the most recent leg snapshot strictly before ``before_date``.

        Used to compute delta-from-yesterday: call with ``before_date=today``
        to get the prior trading day's snapshot.

        Args:
            strategy_name: Paper strategy name.
            leg_role: Leg identifier within the strategy.
            before_date: Upper bound (exclusive) on snapshot_date.

        Returns:
            The PaperLegSnapshot with MAX(snapshot_date) < before_date,
            or None if no prior snapshot exists.
        """
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT strategy_name, leg_role, snapshot_date, unrealized_pnl,"
                " realized_pnl, total_pnl, ltp"
                " FROM paper_leg_snapshots"
                " WHERE strategy_name = ? AND leg_role = ? AND snapshot_date < ?"
                " ORDER BY snapshot_date DESC LIMIT 1",
                (strategy_name, leg_role, before_date.isoformat()),
            ).fetchone()

        if row is None:
            return None
        return _row_to_leg_snapshot(row)

    # ── Track comparison snapshots (S3 — base-leg only, overlay excluded) ──────

    def record_track_comparison_snapshot(self, snap: TrackComparisonSnapshot) -> None:
        """Upsert a daily base-leg-only track comparison snapshot.

        ON CONFLICT UPDATE replaces the row if the same
        (strategy_name, snapshot_date) already exists — idempotent re-runs
        are safe, matching ``record_leg_snapshot``'s pattern.

        Args:
            snap: The TrackComparisonSnapshot to persist. ``strategy_name``
                may be one of the three 3-track strategy names or the
                synthetic ``"nifty_index"`` value for the spot series.
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO paper_track_comparison_snapshots
                   (strategy_name, snapshot_date, pnl_1d_abs, pnl_1d_pct,
                    pnl_inception_abs, pnl_inception_pct, tracking_error_pct)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(strategy_name, snapshot_date)
                   DO UPDATE SET
                       pnl_1d_abs         = excluded.pnl_1d_abs,
                       pnl_1d_pct         = excluded.pnl_1d_pct,
                       pnl_inception_abs  = excluded.pnl_inception_abs,
                       pnl_inception_pct  = excluded.pnl_inception_pct,
                       tracking_error_pct = excluded.tracking_error_pct""",
                (
                    snap.strategy_name,
                    snap.snapshot_date.isoformat(),
                    str(snap.pnl_1d_abs),
                    str(snap.pnl_1d_pct),
                    str(snap.pnl_inception_abs),
                    str(snap.pnl_inception_pct),
                    str(snap.tracking_error_pct) if snap.tracking_error_pct is not None else None,
                ),
            )

    def get_track_comparison_snapshots(
        self,
        strategy_name: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[TrackComparisonSnapshot]:
        """Return the comparison-snapshot history for one strategy, ordered by date.

        Args:
            strategy_name: One of the three 3-track strategy names, or the
                synthetic ``"nifty_index"`` value for the Nifty spot series.
            start_date: Inclusive lower bound on snapshot_date. None = no bound.
            end_date: Inclusive upper bound on snapshot_date. None = no bound.

        Returns:
            TrackComparisonSnapshot rows for ``strategy_name``, ordered
            ascending by snapshot_date. Empty list if none exist.
        """
        query = (
            "SELECT strategy_name, snapshot_date, pnl_1d_abs, pnl_1d_pct,"
            " pnl_inception_abs, pnl_inception_pct, tracking_error_pct"
            " FROM paper_track_comparison_snapshots"
            " WHERE strategy_name = ?"
        )
        params: list[Any] = [strategy_name]
        if start_date is not None:
            query += " AND snapshot_date >= ?"
            params.append(start_date.isoformat())
        if end_date is not None:
            query += " AND snapshot_date <= ?"
            params.append(end_date.isoformat())
        query += " ORDER BY snapshot_date ASC"

        with _connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_track_comparison_snapshot(row) for row in rows]

    # ── Overlay P&L snapshots (S8 — per-overlay, mirrors S3's shape) ────────────

    def record_overlay_pnl_snapshot(self, snap: OverlayPnLSnapshot) -> None:
        """Upsert a daily per-overlay P&L comparison snapshot.

        ON CONFLICT UPDATE replaces the row if the same
        (strategy_name, overlay_type, snapshot_date) already exists —
        idempotent re-runs are safe, matching
        ``record_track_comparison_snapshot``'s pattern.

        Args:
            snap: The OverlayPnLSnapshot to persist.
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO paper_overlay_pnl_snapshots
                   (strategy_name, overlay_type, snapshot_date, pnl_1d_abs,
                    pnl_1d_pct, pnl_inception_abs, pnl_inception_pct)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(strategy_name, overlay_type, snapshot_date)
                   DO UPDATE SET
                       pnl_1d_abs        = excluded.pnl_1d_abs,
                       pnl_1d_pct        = excluded.pnl_1d_pct,
                       pnl_inception_abs = excluded.pnl_inception_abs,
                       pnl_inception_pct = excluded.pnl_inception_pct""",
                (
                    snap.strategy_name,
                    snap.overlay_type,
                    snap.snapshot_date.isoformat(),
                    str(snap.pnl_1d_abs),
                    str(snap.pnl_1d_pct),
                    str(snap.pnl_inception_abs),
                    str(snap.pnl_inception_pct),
                ),
            )

    def get_overlay_pnl_snapshots(
        self,
        strategy_name: str,
        overlay_type: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[OverlayPnLSnapshot]:
        """Return the overlay P&L snapshot history, ordered by date.

        Args:
            strategy_name: 3-track strategy the overlay is attached to.
            overlay_type: One of ``"cc"``, ``"pp"``, ``"collar"``.
            start_date: Inclusive lower bound on snapshot_date. None = no bound.
            end_date: Inclusive upper bound on snapshot_date. None = no bound.

        Returns:
            OverlayPnLSnapshot rows for (strategy_name, overlay_type),
            ordered ascending by snapshot_date. Empty list if none exist.
        """
        query = (
            "SELECT strategy_name, overlay_type, snapshot_date, pnl_1d_abs,"
            " pnl_1d_pct, pnl_inception_abs, pnl_inception_pct"
            " FROM paper_overlay_pnl_snapshots"
            " WHERE strategy_name = ? AND overlay_type = ?"
        )
        params: list[Any] = [strategy_name, overlay_type]
        if start_date is not None:
            query += " AND snapshot_date >= ?"
            params.append(start_date.isoformat())
        if end_date is not None:
            query += " AND snapshot_date <= ?"
            params.append(end_date.isoformat())
        query += " ORDER BY snapshot_date ASC"

        with _connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_overlay_pnl_snapshot(row) for row in rows]

    # ── Protection recovery snapshots (S9 — NiftyBees vs overlay recovery) ─────

    def record_protection_recovery_snapshot(self, snap: ProtectionRecoverySnapshot) -> None:
        """Upsert a daily NiftyBees-vs-overlay recovery comparison row.

        ON CONFLICT UPDATE replaces the row if the same ``snapshot_date``
        already exists — idempotent re-runs are safe, matching
        ``record_overlay_pnl_snapshot``'s pattern.

        Args:
            snap: The ProtectionRecoverySnapshot to persist.
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO paper_protection_recovery_snapshots
                   (snapshot_date, niftybees_pnl_1d, cc_pnl_1d, pp_pnl_1d,
                    collar_pnl_1d, niftybees_pnl_inception, cc_pnl_inception,
                    pp_pnl_inception, collar_pnl_inception, best_overlay,
                    best_recovery_pct, best_overlay_inception,
                    best_recovery_pct_inception)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(snapshot_date)
                   DO UPDATE SET
                       niftybees_pnl_1d             = excluded.niftybees_pnl_1d,
                       cc_pnl_1d                    = excluded.cc_pnl_1d,
                       pp_pnl_1d                    = excluded.pp_pnl_1d,
                       collar_pnl_1d                = excluded.collar_pnl_1d,
                       niftybees_pnl_inception       = excluded.niftybees_pnl_inception,
                       cc_pnl_inception              = excluded.cc_pnl_inception,
                       pp_pnl_inception              = excluded.pp_pnl_inception,
                       collar_pnl_inception          = excluded.collar_pnl_inception,
                       best_overlay                  = excluded.best_overlay,
                       best_recovery_pct             = excluded.best_recovery_pct,
                       best_overlay_inception        = excluded.best_overlay_inception,
                       best_recovery_pct_inception   = excluded.best_recovery_pct_inception""",
                (
                    snap.snapshot_date.isoformat(),
                    str(snap.niftybees_pnl_1d),
                    str(snap.cc_pnl_1d),
                    str(snap.pp_pnl_1d),
                    str(snap.collar_pnl_1d),
                    str(snap.niftybees_pnl_inception),
                    str(snap.cc_pnl_inception),
                    str(snap.pp_pnl_inception),
                    str(snap.collar_pnl_inception),
                    snap.best_overlay,
                    str(snap.best_recovery_pct) if snap.best_recovery_pct is not None else None,
                    snap.best_overlay_inception,
                    (
                        str(snap.best_recovery_pct_inception)
                        if snap.best_recovery_pct_inception is not None
                        else None
                    ),
                ),
            )

    def get_protection_recovery_snapshots(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[ProtectionRecoverySnapshot]:
        """Return the protection-recovery snapshot history, ordered by date.

        Args:
            start_date: Inclusive lower bound on snapshot_date. None = no bound.
            end_date: Inclusive upper bound on snapshot_date. None = no bound.

        Returns:
            ProtectionRecoverySnapshot rows, ordered ascending by
            snapshot_date. Empty list if none exist.
        """
        query = (
            "SELECT snapshot_date, niftybees_pnl_1d, cc_pnl_1d, pp_pnl_1d,"
            " collar_pnl_1d, niftybees_pnl_inception, cc_pnl_inception,"
            " pp_pnl_inception, collar_pnl_inception, best_overlay,"
            " best_recovery_pct, best_overlay_inception,"
            " best_recovery_pct_inception"
            " FROM paper_protection_recovery_snapshots"
            " WHERE 1=1"
        )
        params: list[Any] = []
        if start_date is not None:
            query += " AND snapshot_date >= ?"
            params.append(start_date.isoformat())
        if end_date is not None:
            query += " AND snapshot_date <= ?"
            params.append(end_date.isoformat())
        query += " ORDER BY snapshot_date ASC"

        with _connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_protection_recovery_snapshot(row) for row in rows]

    def delete_trade(self, trade: PaperTrade) -> None:
        """Delete a single paper trade by its unique constraint fields.

        Keyed on (strategy_name, leg_role, instrument_key, trade_date, action)
        so that a roll on a different instrument on the same day cannot
        accidentally delete the wrong row.  No-op if the row does not exist;
        safe to call in a rollback path where the write may not have committed.

        Args:
            trade: The PaperTrade to delete.
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM paper_trades"
                " WHERE strategy_name = ? AND leg_role = ?"
                " AND instrument_key = ? AND trade_date = ? AND action = ?",
                (
                    trade.strategy_name,
                    trade.leg_role,
                    trade.instrument_key,
                    trade.trade_date.isoformat(),
                    trade.action.value,
                ),
            )

    def delete_trade_by_id(self, trade_id: int) -> None:
        """Delete a paper trade by its primary-key ``id``.

        Preferred rollback primitive when the exact ``PaperTrade`` object is not
        available but the row ``id`` (e.g. from ``lastrowid``) is known.
        No-op if the id does not exist.

        Args:
            trade_id: The ``id`` column value of the row to delete.
        """
        with _connect(self.db_path) as conn:
            conn.execute("DELETE FROM paper_trades WHERE id = ?", (trade_id,))

    def create_approval(
        self,
        strategy_name: str,
        event_type: str,
        council_output_json: str,
        telegram_msg_id: int | None,
        expires_at: str,
    ) -> int:
        """INSERT into pending_approvals, status=PENDING. Returns new row id."""
        created_at = datetime.now(timezone.utc).isoformat()
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO pending_approvals
                   (strategy_name, event_type, council_output, status,
                    expires_at, telegram_msg_id, created_at)
                   VALUES (?, ?, ?, 'PENDING', ?, ?, ?)""",
                (
                    strategy_name,
                    event_type,
                    council_output_json,
                    expires_at,
                    telegram_msg_id,
                    created_at,
                ),
            )
            if cur.lastrowid is None:
                raise ValueError("Failed to insert pending approval")
            return cur.lastrowid

    def resolve_approval(
        self,
        approval_id: int,
        status: Literal["APPROVED", "REJECTED", "EXPIRED"],
        approved_rank: int | None = None,
    ) -> None:
        """UPDATE pending_approvals status and approved_rank."""
        resolved_at = datetime.now(timezone.utc).isoformat()
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """UPDATE pending_approvals
                   SET status = ?, resolved_at = ?, approved_rank = ?
                   WHERE id = ?""",
                (status, resolved_at, approved_rank, approval_id),
            )
            if cur.rowcount != 1:
                raise ValueError(f"No pending_approval row with id={approval_id}")

    def expire_all_pending_approvals(self) -> None:
        """Set all PENDING approvals to EXPIRED with resolved_at set to now."""
        resolved_at = datetime.now(timezone.utc).isoformat()
        with _connect(self.db_path) as conn:
            conn.execute(
                """UPDATE pending_approvals
                   SET status = 'EXPIRED', resolved_at = ?
                   WHERE status = 'PENDING'""",
                (resolved_at,),
            )

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        """SELECT all PENDING approvals ordered by created_at ASC."""
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT id, strategy_name, event_type, council_output, status,
                          approved_rank, expires_at, telegram_msg_id,
                          created_at, resolved_at
                   FROM pending_approvals
                   WHERE status = 'PENDING'
                   ORDER BY created_at ASC"""
            ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["council_output"] = json.loads(d["council_output"])
            results.append(d)
        return results

    def get_pending_approval_by_msg_id(
        self,
        telegram_msg_id: int,
    ) -> dict[str, Any] | None:
        """SELECT a PENDING approval by Telegram message ID."""
        with _connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT id, strategy_name, event_type, council_output, status,
                          approved_rank, expires_at, telegram_msg_id,
                          created_at, resolved_at
                   FROM pending_approvals
                   WHERE telegram_msg_id = ? AND status = 'PENDING'""",
                (telegram_msg_id,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["council_output"] = json.loads(d["council_output"])
        return d

    def write_heartbeat(
        self,
        pid: int,
        strategies: list[str],
        last_event: str | None = None,
    ) -> None:
        """INSERT OR REPLACE into daemon_heartbeat (id=1) with UTC timestamp."""
        last_beat = datetime.now(timezone.utc).isoformat()
        strategies_json = json.dumps(strategies)
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO daemon_heartbeat
                   (id, pid, last_beat, strategies, last_event)
                   VALUES (1, ?, ?, ?, ?)""",
                (pid, last_beat, strategies_json, last_event),
            )

    def get_heartbeat(self) -> dict[str, Any] | None:
        """SELECT the daemon_heartbeat row. Returns None if absent."""
        with _connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT id, pid, last_beat, strategies, last_event
                   FROM daemon_heartbeat
                   WHERE id = 1"""
            ).fetchone()
        if row is None:
            return None
        res = dict(row)
        res["strategies"] = json.loads(res["strategies"])
        return res

    def create_council_output(
        self,
        approval_id: int,
        persona: str,
        model: str,
        prompt_tokens: int | None,
        output_tokens: int | None,
        latency_ms: int | None,
        response: str,
    ) -> int:
        """INSERT into council_outputs. Returns new row id."""
        created_at = datetime.now(timezone.utc).isoformat()
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO council_outputs
                   (approval_id, persona, model, prompt_tokens, output_tokens,
                    latency_ms, response, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    approval_id,
                    persona,
                    model,
                    prompt_tokens,
                    output_tokens,
                    latency_ms,
                    response,
                    created_at,
                ),
            )
            if cur.lastrowid is None:
                raise ValueError("Failed to insert council output")
            return cur.lastrowid

    def get_council_outputs(self, approval_id: int) -> list[dict[str, Any]]:
        """SELECT all council outputs for an approval ordered by created_at ASC."""
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT id, approval_id, persona, model, prompt_tokens,
                          output_tokens, latency_ms, response, created_at
                   FROM council_outputs
                   WHERE approval_id = ?
                   ORDER BY created_at ASC""",
                (approval_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_action_audit(
        self,
        strategy_name: str,
        action_type: str,
        leg_role: str,
        price: Decimal,
        qty: int,
        rationale: str | None,
    ) -> int:
        """INSERT one row into paper_action_audit. Returns new row id.

        Records each leg fill for audit purposes. Never raises — callers
        must treat failure as non-fatal.

        Args:
            strategy_name: Strategy that executed the action.
            action_type: e.g. ``"CLOSE_FULL"``, ``"PROFIT_TARGET"``.
            leg_role: e.g. ``"short_put"``.
            price: Fill price as Decimal.
            qty: Absolute quantity filled.
            rationale: Free-text rationale from the approved action.

        Returns:
            Inserted row id.
        """
        executed_at = datetime.now(timezone.utc).isoformat()
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO paper_action_audit
                   (strategy_name, action_type, leg_role, price, qty, rationale, executed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    strategy_name,
                    action_type,
                    leg_role,
                    str(price),
                    qty,
                    rationale,
                    executed_at,
                ),
            )
            if cur.lastrowid is None:
                raise ValueError("Failed to insert action audit row")
            return cur.lastrowid

    # ── Exit events ───────────────────────────────────────────────────────────

    @staticmethod
    def _parse_exit_event_row(row: Any) -> dict[str, Any]:
        """Convert a raw DB row from paper_exit_events to a typed dict.

        Monetary TEXT columns (ltp, mid, bid, ask, entry_price, threshold_value)
        are read back as Decimal; None values remain None.
        All other columns are returned as-is.
        """
        d = dict(row)
        for field in ("ltp", "mid", "bid", "ask", "entry_price", "threshold_value"):
            raw = d.get(field)
            d[field] = Decimal(raw) if raw is not None else None
        return d

    def create_exit_event(
        self,
        strategy_name: str,
        leg_name: str,
        trade_id: str,
        event_time: datetime,
        detected_by: Literal["EOD", "INTRADAY", "MANUAL"],
        exit_signal: ExitSignal,
        severity: Literal["INFO", "WARNING", "ACTION"],
        entry_price: Decimal,
        *,
        snapshot_id: int | None = None,
        ltp: Decimal | None = None,
        mid: Decimal | None = None,
        bid: Decimal | None = None,
        ask: Decimal | None = None,
        delta: float | None = None,
        dte: int | None = None,
        threshold_value: Decimal | None = None,
        delta_stop_would_fire: int | None = None,
        premium_stop_would_fire: int | None = None,
        actual_rule_used: str | None = None,
        counterfactual_dte_marks: str | None = None,
        notes: str | None = None,
    ) -> int:
        """Insert an exit event with status='OPEN' and return the generated row ID.

        Args:
            strategy_name: Name of the paper strategy.
            leg_name: Leg identifier within the strategy.
            trade_id: Paper trade ID referencing the trigger trade.
            event_time: Time when the exit event was detected.
            detected_by: How the signal was detected (EOD, INTRADAY, MANUAL).
            exit_signal: The specific exit signal enum value.
            severity: Severity level (INFO, WARNING, ACTION).
            entry_price: Original entry price.
            snapshot_id: Optional snapshot reference ID.
            ltp: Last traded price of the option at detection.
            mid: Mid price of the option at detection.
            bid: Bid price of the option at detection.
            ask: Ask price of the option at detection.
            delta: Delta of the option at detection.
            dte: Days to expiry at detection.
            threshold_value: Fired threshold value.
            delta_stop_would_fire: 1 if delta stop would have fired, 0 if not.
            premium_stop_would_fire: 1 if premium multiple stop would have fired, 0 if not.
            actual_rule_used: The rule that fired the event (DELTA, PREMIUM, BOTH, NEITHER).
            notes: Qualitative notes to save.

        Returns:
            The generated ID of the inserted event row.
        """
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO paper_exit_events
                   (strategy_name, leg_name, trade_id, snapshot_id, event_time,
                    detected_by, exit_signal, severity, ltp, mid, bid, ask,
                    delta, dte, entry_price, threshold_value,
                    delta_stop_would_fire, premium_stop_would_fire,
                    actual_rule_used, counterfactual_dte_marks,
                    status, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, 'OPEN', ?)""",
                (
                    strategy_name,
                    leg_name,
                    trade_id,
                    snapshot_id,
                    event_time.isoformat(),
                    detected_by,
                    exit_signal.value,
                    severity,
                    str(ltp) if ltp is not None else None,
                    str(mid) if mid is not None else None,
                    str(bid) if bid is not None else None,
                    str(ask) if ask is not None else None,
                    delta,
                    dte,
                    str(entry_price),
                    str(threshold_value) if threshold_value is not None else None,
                    delta_stop_would_fire,
                    premium_stop_would_fire,
                    actual_rule_used,
                    counterfactual_dte_marks,
                    notes,
                ),
            )
            if cur.lastrowid is None:
                raise ValueError("Failed to insert paper exit event")
            return cur.lastrowid

    def get_open_exit_events(
        self,
        strategy_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve open/acknowledged events ordered by event_time ASC.

        Args:
            strategy_name: Optional strategy name to filter by.

        Returns:
            List of open or acknowledged exit events.
        """
        with _connect(self.db_path) as conn:
            if strategy_name is not None:
                rows = conn.execute(
                    """SELECT id, strategy_name, leg_name, trade_id, snapshot_id,
                              event_time, detected_by, exit_signal, severity,
                              ltp, mid, bid, ask, delta, dte, entry_price,
                              threshold_value, delta_stop_would_fire,
                              premium_stop_would_fire, actual_rule_used,
                              counterfactual_dte_marks, status, notes,
                              created_at
                       FROM paper_exit_events
                       WHERE strategy_name = ? AND status IN ('OPEN', 'ACKNOWLEDGED')
                       ORDER BY event_time ASC, id ASC""",
                    (strategy_name,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, strategy_name, leg_name, trade_id, snapshot_id,
                              event_time, detected_by, exit_signal, severity,
                              ltp, mid, bid, ask, delta, dte, entry_price,
                              threshold_value, delta_stop_would_fire,
                              premium_stop_would_fire, actual_rule_used,
                              counterfactual_dte_marks, status, notes,
                              created_at
                       FROM paper_exit_events
                       WHERE status IN ('OPEN', 'ACKNOWLEDGED')
                       ORDER BY event_time ASC, id ASC"""
                ).fetchall()
        return [self._parse_exit_event_row(r) for r in rows]

    def get_exit_event(self, event_id: int) -> dict[str, Any] | None:
        """Fetch a single exit event row by ID."""
        with _connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT id, strategy_name, leg_name, trade_id, snapshot_id,
                          event_time, detected_by, exit_signal, severity,
                          ltp, mid, bid, ask, delta, dte, entry_price,
                          threshold_value, delta_stop_would_fire,
                          premium_stop_would_fire, actual_rule_used,
                          counterfactual_dte_marks, status, notes,
                          created_at
                   FROM paper_exit_events
                   WHERE id = ?""",
                (event_id,),
            ).fetchone()
        return self._parse_exit_event_row(row) if row is not None else None

    # ── Margin snapshots ─────────────────────────────────────────────────────

    def record_margin_snapshot(self, snapshot: MarginSnapshot) -> None:
        """Upsert the entry-cycle margin snapshot for a strategy.

        Idempotent on (strategy_name, entry_date) — safe to call more than
        once for the same entry cycle (e.g. a retried entry script run); the
        latest call wins.

        Args:
            snapshot: The MarginSnapshot to persist.
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO paper_margin_snapshots
                   (strategy_name, entry_date, required_margin, final_margin, captured_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(strategy_name, entry_date) DO UPDATE SET
                       required_margin = excluded.required_margin,
                       final_margin = excluded.final_margin,
                       captured_at = excluded.captured_at""",
                (
                    snapshot.strategy_name,
                    snapshot.entry_date.isoformat(),
                    str(snapshot.required_margin),
                    str(snapshot.final_margin),
                    snapshot.captured_at.isoformat(),
                ),
            )

    def get_margin_snapshot(self, strategy_name: str, entry_date: date) -> MarginSnapshot | None:
        """Fetch the margin snapshot for a strategy's entry cycle, if captured.

        Args:
            strategy_name: Paper strategy name.
            entry_date: Entry cycle date — matches ``PaperPosition.entry_date``.

        Returns:
            MarginSnapshot if one was recorded for this (strategy, entry_date)
            pair, else None (e.g. entry predates this feature, or the
            margin-calculator call failed at entry time and was logged but
            not persisted).
        """
        with _connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT strategy_name, entry_date, required_margin, final_margin, captured_at
                   FROM paper_margin_snapshots
                   WHERE strategy_name = ? AND entry_date = ?""",
                (strategy_name, entry_date.isoformat()),
            ).fetchone()
        if row is None:
            return None
        return MarginSnapshot(
            strategy_name=row["strategy_name"],
            entry_date=date.fromisoformat(row["entry_date"]),
            required_margin=Decimal(row["required_margin"]),
            final_margin=Decimal(row["final_margin"]),
            captured_at=datetime.fromisoformat(row["captured_at"]),
        )

    # ── Gate violations ──────────────────────────────────────────────────────

    # ── WARN signal dedup state ──────────────────────────────────────────
    def is_warn_active(
        self, strategy_name: str, event_type: str, leg_role: str, expiry: str = ""
    ) -> bool:
        """Return whether a WARN condition is already flagged active.

        Used by ``StrategyMonitor._route_event`` to suppress repeat Telegram
        sends for a WARN-severity ``SignalEvent`` that fires on every tick
        while its underlying condition (e.g. delta breach) persists — the
        alert should fire once on the OFF→ON transition, not every ~2 min.

        Args:
            strategy_name: Strategy that emitted the event.
            event_type: Event type string, e.g. "DELTA_WARN".
            leg_role: Leg the warning applies to, e.g. "short_call".
            expiry: ISO expiry date of the chain the event was evaluated
                against (``chain.expiry.isoformat()``), included in the key
                so two distinct expiry groups sharing a ``leg_role`` under
                the same ``strategy_name`` (e.g. a future calendar/multi-
                expiry strategy) never alias to one dedup row. Defaults to
                "" for callers that don't carry expiry context.

        Returns:
            True if this condition was already active as of the last tick.
        """
        with _connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT active FROM warn_signal_state
                   WHERE strategy_name = ? AND event_type = ? AND leg_role = ? AND expiry = ?""",
                (strategy_name, event_type, leg_role, expiry),
            ).fetchone()
        return bool(row is not None and row["active"])

    def set_warn_active(
        self,
        strategy_name: str,
        event_type: str,
        leg_role: str,
        active: bool,
        expiry: str = "",
    ) -> None:
        """Upsert the active/inactive state for a WARN condition.

        Args:
            strategy_name: Strategy that emitted the event.
            event_type: Event type string, e.g. "DELTA_WARN".
            leg_role: Leg the warning applies to.
            active: True to mark the condition as currently ongoing (alert
                already sent this occurrence); False to clear it on recovery
                so the next breach re-alerts.
            expiry: ISO expiry date, see ``is_warn_active`` docstring.
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO warn_signal_state
                   (strategy_name, event_type, leg_role, expiry, active, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(strategy_name, event_type, leg_role, expiry)
                   DO UPDATE SET active = excluded.active, updated_at = excluded.updated_at""",
                (
                    strategy_name,
                    event_type,
                    leg_role,
                    expiry,
                    1 if active else 0,
                    datetime.now(tz=timezone.utc).isoformat(),
                ),
            )

    def reconcile_warn_state(
        self, strategy_name: str, fired_keys: set[tuple[str, str, str]]
    ) -> None:
        """Clear active WARN state for conditions that did not fire this tick.

        Called once per strategy per tick after all its ``SignalEvent``s have
        been routed. Any ``(event_type, leg_role, expiry)`` previously marked
        active but absent from ``fired_keys`` has recovered (the strategy's
        ``check_signals`` only emits a WARN event while the condition holds)
        — clearing it means the next re-breach alerts immediately rather than
        staying silent forever after the first occurrence.

        Args:
            strategy_name: Strategy whose WARN state is being reconciled.
            fired_keys: Set of (event_type, leg_role, expiry) triples that
                fired as WARN-severity events during this tick for this
                strategy, unioned across all of its expiry groups.
        """
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT event_type, leg_role, expiry FROM warn_signal_state
                   WHERE strategy_name = ? AND active = 1""",
                (strategy_name,),
            ).fetchall()
            recovered = [
                (r["event_type"], r["leg_role"], r["expiry"])
                for r in rows
                if (r["event_type"], r["leg_role"], r["expiry"]) not in fired_keys
            ]
            for event_type, leg_role, expiry in recovered:
                conn.execute(
                    """UPDATE warn_signal_state SET active = 0, updated_at = ?
                       WHERE strategy_name = ? AND event_type = ? AND leg_role = ? AND expiry = ?""",
                    (
                        datetime.now(tz=timezone.utc).isoformat(),
                        strategy_name,
                        event_type,
                        leg_role,
                        expiry,
                    ),
                )

    def record_gate_violation(self, violation: GateViolation) -> int:
        """Insert a threshold-gate violation and return the generated row ID.

        Called under ``--log-only-gates`` mode when a threshold/discretionary
        gate (IVR floor, DTE window, liquidity floor, portfolio-delta cap)
        would have blocked entry. Structural gates never call this — they
        hard-block via ``sys.exit(1)`` regardless of the flag.

        Args:
            violation: The GateViolation to persist.

        Returns:
            The generated ID of the inserted row.
        """
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO gate_violations
                   (gate_name, threshold, actual, strategy_name, logged_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    violation.gate_name,
                    violation.threshold,
                    violation.actual,
                    violation.strategy_name,
                    violation.logged_at.isoformat(),
                ),
            )
            if cur.lastrowid is None:
                raise ValueError("Failed to insert gate violation")
            return cur.lastrowid

    def get_gate_violation_counts(
        self,
        strategy_name: str | None = None,
        gate_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate gate-violation counts, GROUP BY (strategy_name, gate_name).

        Pre-aggregates at the DB layer per project Rule 1 — callers never
        receive a raw per-row dump.

        Args:
            strategy_name: Optional filter to a single strategy.
            gate_name: Optional filter to a single gate.

        Returns:
            List of dicts with keys ``strategy_name``, ``gate_name``,
            ``violation_count``, ordered by count descending.
        """
        clauses = []
        params: list[str] = []
        if strategy_name is not None:
            clauses.append("strategy_name = ?")
            params.append(strategy_name)
        if gate_name is not None:
            clauses.append("gate_name = ?")
            params.append(gate_name)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with _connect(self.db_path) as conn:
            rows = conn.execute(
                f"""SELECT strategy_name, gate_name, COUNT(*) AS violation_count
                    FROM gate_violations
                    {where}
                    GROUP BY strategy_name, gate_name
                    ORDER BY violation_count DESC""",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def acknowledge_exit_event(self, event_id: int) -> None:
        """Update event status to 'ACKNOWLEDGED' if status is 'OPEN'.

        Args:
            event_id: The ID of the event to acknowledge.

        Raises:
            ValueError: If the event row is not found or is not in 'OPEN' state.
        """
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """UPDATE paper_exit_events
                   SET status = 'ACKNOWLEDGED'
                   WHERE id = ? AND status = 'OPEN'""",
                (event_id,),
            )
            if cur.rowcount == 0:
                raise ValueError(f"No open paper_exit_events row with id={event_id}")

    def resolve_exit_event(
        self,
        event_id: int,
        status: Literal["ACTED", "DISMISSED"],
        notes: str | None = None,
    ) -> None:
        """Resolve event and append notes if provided.

        Args:
            event_id: The ID of the event to resolve.
            status: The resolution status (ACTED, DISMISSED).
            notes: Optional notes to append.

        Raises:
            ValueError: If the event row is not found or is not in open/acknowledged state.
        """
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """UPDATE paper_exit_events
                   SET status = ?,
                       notes = CASE
                           WHEN ? IS NULL THEN notes
                           WHEN notes IS NULL OR notes = '' THEN ?
                           ELSE notes || '\n' || ?
                       END
                   WHERE id = ? AND status IN ('OPEN', 'ACKNOWLEDGED')""",
                (status, notes, notes, notes, event_id),
            )
            if cur.rowcount == 0:
                raise ValueError(
                    f"No open or acknowledged paper_exit_events row with id={event_id}"
                )

    def resolve_exit_event_with_audit(
        self,
        event_id: int,
        status: Literal["ACTED", "DISMISSED"],
        *,
        delta_stop_would_fire: int | None = None,
        premium_stop_would_fire: int | None = None,
        actual_rule_used: str | None = None,
        notes: str | None = None,
    ) -> None:
        """Resolve event, update audit fields, and append notes if provided."""
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """UPDATE paper_exit_events
                   SET status = ?,
                       delta_stop_would_fire = COALESCE(?, delta_stop_would_fire),
                       premium_stop_would_fire = COALESCE(?, premium_stop_would_fire),
                       actual_rule_used = COALESCE(?, actual_rule_used),
                       notes = CASE
                           WHEN ? IS NULL THEN notes
                           WHEN notes IS NULL OR notes = '' THEN ?
                           ELSE notes || '\n' || ?
                       END
                   WHERE id = ? AND status IN ('OPEN', 'ACKNOWLEDGED')""",
                (
                    status,
                    delta_stop_would_fire,
                    premium_stop_would_fire,
                    actual_rule_used,
                    notes,
                    notes,
                    notes,
                    event_id,
                ),
            )
            if cur.rowcount == 0:
                raise ValueError(
                    f"No open or acknowledged paper_exit_events row with id={event_id}"
                )
