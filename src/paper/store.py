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

from datetime import date
from decimal import Decimal
from pathlib import Path

from src.db import connect as _connect
from src.paper.models import PaperNavSnapshot, PaperPosition, PaperTrade
from src.models.portfolio import TradeAction

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
"""


def _row_to_trade(row) -> PaperTrade:
    return PaperTrade(
        strategy_name=row["strategy_name"],
        leg_role=row["leg_role"],
        instrument_key=row["instrument_key"],
        trade_date=date.fromisoformat(row["trade_date"]),
        action=TradeAction(row["action"]),
        quantity=row["quantity"],
        price=Decimal(row["price"]),
        notes=row["notes"],
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

    # ── Trades ledger ─────────────────────────────────────────────────────────

    def record_trade(self, trade: PaperTrade) -> None:
        """Insert a paper trade into the ledger. Silently skips exact duplicates.

        Uniqueness is on (strategy_name, leg_role, trade_date, action).
        Re-running record_paper_trade.py with the same args is always safe.

        Args:
            trade: The paper trade to persist.
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO paper_trades
                   (strategy_name, leg_role, instrument_key, trade_date,
                    action, quantity, price, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )

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
                    " action, quantity, price, notes"
                    " FROM paper_trades"
                    " WHERE strategy_name = ? AND leg_role = ?"
                    " ORDER BY trade_date ASC",
                    (strategy_name, leg_role),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT strategy_name, leg_role, instrument_key, trade_date,"
                    " action, quantity, price, notes"
                    " FROM paper_trades"
                    " WHERE strategy_name = ?"
                    " ORDER BY trade_date ASC",
                    (strategy_name,),
                ).fetchall()
        return [_row_to_trade(r) for r in rows]

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
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT action, quantity, price, instrument_key"
                " FROM paper_trades"
                " WHERE strategy_name = ? AND leg_role = ?"
                " ORDER BY trade_date ASC",
                (strategy_name, leg_role),
            ).fetchall()

        if not rows:
            return PaperPosition(
                strategy_name=strategy_name,
                leg_role=leg_role,
                net_qty=0,
                avg_cost=Decimal("0"),
                avg_sell_price=Decimal("0"),
                instrument_key="",
            )

        net_qty = 0
        buy_total_qty = 0
        buy_total_cost = Decimal("0")
        sell_total_qty = 0
        sell_total_cost = Decimal("0")
        instrument_key = ""

        for row in rows:
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

        avg_cost = (
            buy_total_cost / buy_total_qty
            if buy_total_qty > 0
            else Decimal("0")
        )
        avg_sell_price = (
            sell_total_cost / sell_total_qty
            if sell_total_qty > 0
            else Decimal("0")
        )

        return PaperPosition(
            strategy_name=strategy_name,
            leg_role=leg_role,
            net_qty=net_qty,
            avg_cost=avg_cost,
            avg_sell_price=avg_sell_price,
            instrument_key=instrument_key,
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
                    Decimal(r["underlying_price"])
                    if r["underlying_price"] is not None
                    else None
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
                Decimal(row["underlying_price"])
                if row["underlying_price"] is not None
                else None
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
