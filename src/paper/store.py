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
from typing import Any, Literal

from src.db import connect as _connect
from src.models.portfolio import TradeAction
from src.paper.models import (
    ExitSignal,
    PaperLegSnapshot,
    PaperNavSnapshot,
    PaperPosition,
    PaperTrade,
)

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
    UNIQUE(strategy_name, leg_role, trade_date, action)
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
    ltp                     REAL,
    mid                     REAL,
    bid                     REAL,
    ask                     REAL,
    delta                   REAL,
    dte                     INTEGER,
    entry_price             REAL    NOT NULL,
    threshold_value         REAL,
    delta_stop_would_fire   INTEGER,
    premium_stop_would_fire INTEGER,
    actual_rule_used        TEXT,
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


class PaperStore:
    """SQLite-backed store for paper trading records.

    Creates the paper_trades and paper_nav_snapshots tables on first
    instantiation if they do not exist.  Uses the shared portfolio.sqlite
    database via the src.db connection manager.

    Args:
        db_path: Path to the shared portfolio SQLite database.
    """

    def __init__(self, db_path: Path | str) -> None:
        """Initialize store, creating tables if needed.

        Args:
            db_path: Path to SQLite database file (str or Path).
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with _connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)
            # Migration: add ivr_at_entry to paper_trades if missing
            try:
                conn.execute("ALTER TABLE paper_trades ADD COLUMN ivr_at_entry REAL DEFAULT NULL")
            except sqlite3.OperationalError:
                pass  # Column already exists

    # ── Trades ledger ─────────────────────────────────────────────────────────

    def record_trade(self, trade: PaperTrade) -> bool:
        """Insert a paper trade into the ledger. Silently skips exact duplicates.

        Uniqueness is on (strategy_name, leg_role, trade_date, action).
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
                    action, quantity, price, notes, ivr_at_entry)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(strategy_name, leg_role, trade_date, action)
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
                        action, quantity, price, notes, ivr_at_entry)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(strategy_name, leg_role, trade_date, action)
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
                    ),
                )
                if cur.rowcount == 1:
                    inserted_trades.append(trade)
                else:
                    skipped_trades.append(trade)
        return inserted_trades, skipped_trades

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
                    " action, quantity, price, notes, ivr_at_entry"
                    " FROM paper_trades"
                    " WHERE strategy_name = ? AND leg_role = ?"
                    " ORDER BY trade_date ASC, id ASC",
                    (strategy_name, leg_role),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT strategy_name, leg_role, instrument_key, trade_date,"
                    " action, quantity, price, notes, ivr_at_entry"
                    " FROM paper_trades"
                    " WHERE strategy_name = ?"
                    " ORDER BY trade_date ASC, id ASC",
                    (strategy_name,),
                ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def get_positions(self, strategy_name: str) -> list[PaperPosition]:
        """Compute net open positions for all legs of a strategy in a single query.

        Args:
            strategy_name: Paper strategy name.

        Returns:
            List of PaperPosition.
        """
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT leg_role, action, quantity, price, instrument_key"
                " FROM paper_trades"
                " WHERE strategy_name = ?"
                " ORDER BY trade_date ASC, id ASC",
                (strategy_name,),
            ).fetchall()

        if not rows:
            return []

        leg_rows = defaultdict(list)
        for row in rows:
            leg_rows[row["leg_role"]].append(row)

        positions = []
        for leg_role, rows_for_leg in leg_rows.items():
            net_qty = 0
            buy_total_qty = 0
            buy_total_cost = Decimal("0")
            sell_total_qty = 0
            sell_total_cost = Decimal("0")
            instrument_key = ""

            for row in rows_for_leg:
                instrument_key = row["instrument_key"]
                qty = row["quantity"]
                price = Decimal(row["price"])
                if TradeAction(row["action"]) == TradeAction.BUY:
                    net_qty += qty
                    buy_total_qty += qty
                    buy_total_cost += price * qty
                else:
                    net_qty -= qty
                    sell_total_qty += qty
                    sell_total_cost += price * qty

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
                    instrument_key=instrument_key,
                )
            )
        return positions

    def get_position(
        self,
        strategy_name: str,
        leg_role: str,
    ) -> PaperPosition:
        """Compute net open position for a leg from the paper_trades ledger.

        Net quantity = SUM(BUY qty) - SUM(SELL qty).
        Average cost = weighted average of BUY prices only (SELL prices excluded,
        consistent with live PortfolioStore.get_position semantics).
        Instrument key taken from the most recent trade for this leg.

        Args:
            strategy_name: Paper strategy name.
            leg_role: Leg identifier within the strategy.

        Returns:
            PaperPosition with net_qty=0 and avg_cost=Decimal("0") if no trades exist.
        """
        positions = {p.leg_role: p for p in self.get_positions(strategy_name)}
        return positions.get(
            leg_role,
            PaperPosition(
                strategy_name=strategy_name,
                leg_role=leg_role,
                net_qty=0,
                avg_cost=Decimal("0"),
                avg_sell_price=Decimal("0"),
                instrument_key="",
            ),
        )

    # ── NAV snapshots ─────────────────────────────────────────────────────────

    def record_nav_snapshot(self, snapshot: PaperNavSnapshot) -> None:
        """Upsert a daily NAV snapshot for a paper strategy.

        ON CONFLICT UPDATE replaces the row if the same (strategy_name,
        snapshot_date) already exists — idempotent re-runs are safe.

        Args:
            snapshot: The PaperNavSnapshot to persist.
        """
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

    def delete_trade(self, trade: PaperTrade) -> None:
        """Delete a single paper trade by its unique constraint fields.

        Keyed on (strategy_name, leg_role, trade_date, action) — the same
        unique constraint enforced by the paper_trades table. No-op if the
        row does not exist; safe to call in a rollback path where the write
        may not have committed.

        Args:
            trade: The PaperTrade to delete.
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM paper_trades"
                " WHERE strategy_name = ? AND leg_role = ?"
                " AND trade_date = ? AND action = ?",
                (
                    trade.strategy_name,
                    trade.leg_role,
                    trade.trade_date.isoformat(),
                    trade.action.value,
                ),
            )

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

    # ── Exit events ───────────────────────────────────────────────────────────

    def create_exit_event(
        self,
        strategy_name: str,
        leg_name: str,
        trade_id: str,
        event_time: datetime,
        detected_by: str,
        exit_signal: ExitSignal,
        severity: str,
        entry_price: Decimal | float,
        *,
        snapshot_id: int | None = None,
        ltp: float | None = None,
        mid: float | None = None,
        bid: float | None = None,
        ask: float | None = None,
        delta: float | None = None,
        dte: int | None = None,
        threshold_value: float | None = None,
        delta_stop_would_fire: int | None = None,
        premium_stop_would_fire: int | None = None,
        actual_rule_used: str | None = None,
        notes: str | None = None,
    ) -> int:
        """Insert an exit event with status='OPEN' and return the generated row ID."""
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO paper_exit_events
                   (strategy_name, leg_name, trade_id, snapshot_id, event_time,
                    detected_by, exit_signal, severity, ltp, mid, bid, ask,
                    delta, dte, entry_price, threshold_value, delta_stop_would_fire,
                    premium_stop_would_fire, actual_rule_used, status, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)""",
                (
                    strategy_name,
                    leg_name,
                    trade_id,
                    snapshot_id,
                    event_time.isoformat(),
                    detected_by,
                    exit_signal.value,
                    severity,
                    ltp,
                    mid,
                    bid,
                    ask,
                    delta,
                    dte,
                    float(entry_price),
                    threshold_value,
                    delta_stop_would_fire,
                    premium_stop_would_fire,
                    actual_rule_used,
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
        """Retrieve open/acknowledged events ordered by event_time ASC."""
        with _connect(self.db_path) as conn:
            if strategy_name is not None:
                rows = conn.execute(
                    """SELECT id, strategy_name, leg_name, trade_id, snapshot_id,
                              event_time, detected_by, exit_signal, severity,
                              ltp, mid, bid, ask, delta, dte, entry_price,
                              threshold_value, delta_stop_would_fire,
                              premium_stop_would_fire, actual_rule_used, status,
                              notes, created_at
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
                              premium_stop_would_fire, actual_rule_used, status,
                              notes, created_at
                       FROM paper_exit_events
                       WHERE status IN ('OPEN', 'ACKNOWLEDGED')
                       ORDER BY event_time ASC, id ASC"""
                ).fetchall()
        return [dict(r) for r in rows]

    def acknowledge_exit_event(self, event_id: int) -> None:
        """Update event status to 'ACKNOWLEDGED' if status is 'OPEN'."""
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
        """Resolve event and append notes if provided."""
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
