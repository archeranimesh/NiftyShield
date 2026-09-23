"""SQLite persistence for the MVP value-picks tracker."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from src.db import connect
from src.mvp.models import Category, MVPSnapshot, Pick, PickStatus, Provider


class MVPStore:
    """SQLite-backed store for MVP providers, categories, picks, and snapshots."""

    def __init__(self, db_path: str | Path) -> None:
        """Store the database path; no connection is held open.

        Args:
            db_path: Filesystem path to the SQLite database file.
        """
        self.db_path = Path(db_path)

    def init_db(self) -> None:
        """Create the MVP tables if they do not already exist.

        Safe to call repeatedly.
        """
        with connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mvp_providers (
                    provider_id   TEXT PRIMARY KEY,
                    slug          TEXT NOT NULL UNIQUE,
                    display_name  TEXT NOT NULL,
                    source_type   TEXT NOT NULL,
                    notes         TEXT,
                    created_at    TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mvp_categories (
                    category_id   TEXT PRIMARY KEY,
                    provider_id   TEXT NOT NULL REFERENCES mvp_providers(provider_id),
                    slug          TEXT NOT NULL,
                    display_name  TEXT NOT NULL,
                    notes         TEXT,
                    created_at    TEXT NOT NULL,
                    UNIQUE (provider_id, slug)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mvp_recommendations (
                    pick_id           TEXT PRIMARY KEY,
                    category_id       TEXT REFERENCES mvp_categories(category_id),
                    symbol            TEXT NOT NULL,
                    instrument_key    TEXT,
                    analyst           TEXT,
                    entry_price       TEXT,
                    pick_date         TEXT NOT NULL,
                    target_price      TEXT,
                    stop_loss         TEXT,
                    notes             TEXT,
                    status            TEXT NOT NULL DEFAULT 'PENDING',
                    closed_at         TEXT,
                    close_price       TEXT,
                    capital_allotted  TEXT NOT NULL DEFAULT '100000',
                    tranche_step_pct  TEXT NOT NULL DEFAULT '6',
                    max_drawdown_pct  TEXT NOT NULL DEFAULT '30',
                    deployed_capital  TEXT NOT NULL DEFAULT '0',
                    total_qty         INTEGER NOT NULL DEFAULT 0,
                    avg_cost          TEXT,
                    idle_cash         TEXT NOT NULL DEFAULT '0',
                    realized_pnl      TEXT NOT NULL DEFAULT '0',
                    benchmark_entry   TEXT,
                    created_at        TEXT NOT NULL,
                    updated_at        TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mvp_tranches (
                    tranche_id     TEXT PRIMARY KEY,
                    pick_id        TEXT NOT NULL REFERENCES mvp_recommendations(pick_id),
                    tranche_index  INTEGER NOT NULL,
                    trigger_pct    TEXT NOT NULL,
                    fill_price     TEXT,
                    qty            INTEGER,
                    cost_bps       TEXT NOT NULL DEFAULT '25',
                    filled_at      TEXT,
                    UNIQUE (pick_id, tranche_index)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mvp_snapshots (
                    snapshot_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    pick_id       TEXT NOT NULL REFERENCES mvp_recommendations(pick_id),
                    ltp           TEXT NOT NULL,
                    captured_at   TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mvp_snapshots_pick "
                "ON mvp_snapshots (pick_id, captured_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mvp_tranches_pick "
                "ON mvp_tranches (pick_id, tranche_index)"
            )

    def add_provider(self, provider: Provider) -> None:
        """Insert a provider, ignoring the insert if it already exists.

        Args:
            provider: The provider to persist.
        """
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO mvp_providers
                    (provider_id, slug, display_name, source_type, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    provider.provider_id,
                    provider.slug,
                    provider.display_name,
                    provider.source_type.value,
                    provider.notes,
                    provider.created_at,
                ),
            )

    def get_provider(self, slug: str) -> Provider | None:
        """Fetch a provider by slug.

        Args:
            slug: The provider's unique slug.

        Returns:
            The matching ``Provider``, or ``None`` if no row matches.
        """
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM mvp_providers WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            return None
        return Provider(
            provider_id=row["provider_id"],
            slug=row["slug"],
            display_name=row["display_name"],
            source_type=row["source_type"],
            notes=row["notes"],
            created_at=row["created_at"],
        )

    def list_providers(self) -> list[Provider]:
        """List all providers ordered by display name.

        Returns:
            All providers, ordered by ``display_name``.
        """
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM mvp_providers ORDER BY display_name").fetchall()
        return [
            Provider(
                provider_id=row["provider_id"],
                slug=row["slug"],
                display_name=row["display_name"],
                source_type=row["source_type"],
                notes=row["notes"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def add_category(self, category: Category) -> None:
        """Insert a category, ignoring the insert if it already exists.

        Args:
            category: The category to persist.
        """
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO mvp_categories
                    (category_id, provider_id, slug, display_name, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    category.category_id,
                    category.provider_id,
                    category.slug,
                    category.display_name,
                    category.notes,
                    category.created_at,
                ),
            )

    def get_category(self, provider_id: str, slug: str) -> Category | None:
        """Fetch a category by its composite (provider_id, slug) key.

        Args:
            provider_id: The owning provider's id.
            slug: The category's slug, unique within the provider.

        Returns:
            The matching ``Category``, or ``None`` if no row matches.
        """
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM mvp_categories WHERE provider_id = ? AND slug = ?",
                (provider_id, slug),
            ).fetchone()
        if row is None:
            return None
        return Category(
            category_id=row["category_id"],
            provider_id=row["provider_id"],
            slug=row["slug"],
            display_name=row["display_name"],
            notes=row["notes"],
            created_at=row["created_at"],
        )

    def list_categories(self, provider_id: str) -> list[Category]:
        """List all categories for a provider.

        Args:
            provider_id: The owning provider's id.

        Returns:
            All categories belonging to ``provider_id``.
        """
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM mvp_categories WHERE provider_id = ?", (provider_id,)
            ).fetchall()
        return [
            Category(
                category_id=row["category_id"],
                provider_id=row["provider_id"],
                slug=row["slug"],
                display_name=row["display_name"],
                notes=row["notes"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def add_pick(self, pick: Pick) -> None:
        """Insert a pick into ``mvp_recommendations``.

        Args:
            pick: The pick to persist.
        """
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO mvp_recommendations
                    (pick_id, category_id, symbol, instrument_key, analyst,
                     entry_price, pick_date, target_price, stop_loss, notes,
                     status, closed_at, close_price, capital_allotted,
                     tranche_step_pct, max_drawdown_pct, deployed_capital,
                     total_qty, avg_cost, idle_cash, realized_pnl,
                     benchmark_entry, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pick.pick_id,
                    pick.category_id,
                    pick.symbol,
                    pick.instrument_key,
                    pick.analyst,
                    str(pick.entry_price) if pick.entry_price is not None else None,
                    pick.pick_date,
                    str(pick.target_price) if pick.target_price is not None else None,
                    str(pick.stop_loss) if pick.stop_loss is not None else None,
                    pick.notes,
                    pick.status.value,
                    pick.closed_at,
                    str(pick.close_price) if pick.close_price is not None else None,
                    str(pick.capital_allotted),
                    str(pick.tranche_step_pct),
                    str(pick.max_drawdown_pct),
                    str(pick.deployed_capital),
                    pick.total_qty,
                    str(pick.avg_cost) if pick.avg_cost is not None else None,
                    str(pick.idle_cash),
                    str(pick.realized_pnl),
                    str(pick.benchmark_entry) if pick.benchmark_entry is not None else None,
                    pick.created_at,
                    pick.updated_at,
                ),
            )

    def get_pick(self, pick_id: str) -> Pick | None:
        """Fetch a pick by id.

        Args:
            pick_id: The pick's unique id.

        Returns:
            The matching ``Pick``, or ``None`` if no row matches.
        """
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM mvp_recommendations WHERE pick_id = ?", (pick_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_pick(row)

    def update_pick(self, pick_id: str, **kwargs: object) -> None:
        """Update the given fields of a pick and bump ``updated_at``.

        If ``entry_price`` is set and the pick is currently PENDING, the
        status auto-advances to OPEN.

        Args:
            pick_id: The pick to update.
            **kwargs: Any of ``category_id``, ``symbol``, ``instrument_key``,
                ``analyst``, ``entry_price``, ``target_price``, ``stop_loss``,
                ``notes``, ``status``.

        Note:
            Silently no-ops if ``pick_id`` does not exist.
        """
        allowed = {
            "category_id",
            "symbol",
            "instrument_key",
            "analyst",
            "entry_price",
            "target_price",
            "stop_loss",
            "notes",
            "status",
        }
        decimal_fields = {"entry_price", "target_price", "stop_loss"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}

        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT status FROM mvp_recommendations WHERE pick_id = ?", (pick_id,)
            ).fetchone()
            if row is None:
                return

            if "entry_price" in fields and row["status"] == PickStatus.PENDING.value:
                fields["status"] = PickStatus.OPEN.value

            fields["updated_at"] = datetime.now(timezone.utc).isoformat()

            set_clause = ", ".join(f"{k} = ?" for k in fields)
            values = [
                str(v)
                if k in decimal_fields and v is not None
                else v.value
                if k == "status" and isinstance(v, PickStatus)
                else v
                for k, v in fields.items()
            ]
            conn.execute(
                f"UPDATE mvp_recommendations SET {set_clause} WHERE pick_id = ?",
                (*values, pick_id),
            )

    def close_pick(self, pick_id: str, close_price: Decimal, status: PickStatus) -> None:
        """Close a pick, setting ``closed_at``, ``close_price``, and ``status``.

        Args:
            pick_id: The pick to close.
            close_price: The price at which the pick was closed.
            status: The terminal status (``TARGET_HIT``, ``SL_HIT``, or
                ``MANUAL_CLOSE``).

        Raises:
            ValueError: If ``status`` is not a terminal status.
        """
        terminal = {PickStatus.TARGET_HIT, PickStatus.SL_HIT, PickStatus.MANUAL_CLOSE}
        if status not in terminal:
            raise ValueError(f"close_pick requires a terminal status, got {status}")

        now = datetime.now(timezone.utc).isoformat()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE mvp_recommendations
                SET closed_at = ?, close_price = ?, status = ?, updated_at = ?
                WHERE pick_id = ?
                """,
                (now, str(close_price), status.value, now, pick_id),
            )

    def get_distinct_symbols(self) -> set[str]:
        """List every distinct symbol recorded across all picks.

        Returns:
            Distinct `mvp_recommendations.symbol` values, empty if no picks exist.
        """
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT DISTINCT symbol FROM mvp_recommendations").fetchall()
        return {row["symbol"] for row in rows}

    def get_open_picks(self) -> list[Pick]:
        """List all picks with status OPEN.

        Returns:
            All open picks.
        """
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM mvp_recommendations WHERE status = ?",
                (PickStatus.OPEN.value,),
            ).fetchall()
        return [self._row_to_pick(row) for row in rows]

    def list_picks(
        self,
        status: PickStatus | None = None,
        provider_id: str | None = None,
        category_id: str | None = None,
    ) -> list[Pick]:
        """List picks, optionally filtered by status, provider, or category.

        Args:
            status: If given, only return picks with this status.
            provider_id: If given, only return picks whose category belongs
                to this provider.
            category_id: If given, only return picks with this category.

        Returns:
            The filtered list of picks.
        """
        clauses = []
        params: list[object] = []
        query = "SELECT r.* FROM mvp_recommendations r"
        if provider_id is not None:
            query += " JOIN mvp_categories c ON r.category_id = c.category_id"
            clauses.append("c.provider_id = ?")
            params.append(provider_id)
        if status is not None:
            clauses.append("r.status = ?")
            params.append(status.value)
        if category_id is not None:
            clauses.append("r.category_id = ?")
            params.append(category_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        with connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_pick(row) for row in rows]

    def record_snapshot(self, snapshot: MVPSnapshot) -> None:
        """Insert a price snapshot into ``mvp_snapshots``.

        Args:
            snapshot: The snapshot to persist.
        """
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO mvp_snapshots (pick_id, ltp, captured_at) VALUES (?, ?, ?)",
                (snapshot.pick_id, str(snapshot.ltp), snapshot.captured_at),
            )

    def get_snapshots(self, pick_id: str, limit: int = 10) -> list[MVPSnapshot]:
        """List the most recent snapshots for a pick.

        Args:
            pick_id: The pick to fetch snapshots for.
            limit: Maximum number of snapshots to return.

        Returns:
            Snapshots ordered by ``captured_at`` descending.
        """
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM mvp_snapshots
                WHERE pick_id = ?
                ORDER BY captured_at DESC
                LIMIT ?
                """,
                (pick_id, limit),
            ).fetchall()
        return [
            MVPSnapshot(
                snapshot_id=row["snapshot_id"],
                pick_id=row["pick_id"],
                ltp=row["ltp"],
                captured_at=row["captured_at"],
            )
            for row in rows
        ]

    @staticmethod
    def _row_to_pick(row: sqlite3.Row) -> Pick:
        """Build a ``Pick`` from a ``mvp_recommendations`` row."""
        return Pick(
            pick_id=row["pick_id"],
            category_id=row["category_id"],
            symbol=row["symbol"],
            instrument_key=row["instrument_key"],
            analyst=row["analyst"],
            entry_price=row["entry_price"],
            pick_date=row["pick_date"],
            target_price=row["target_price"],
            stop_loss=row["stop_loss"],
            notes=row["notes"],
            status=PickStatus(row["status"]),
            closed_at=row["closed_at"],
            close_price=row["close_price"],
            capital_allotted=row["capital_allotted"],
            tranche_step_pct=row["tranche_step_pct"],
            max_drawdown_pct=row["max_drawdown_pct"],
            deployed_capital=row["deployed_capital"],
            total_qty=row["total_qty"],
            avg_cost=row["avg_cost"],
            idle_cash=row["idle_cash"],
            realized_pnl=row["realized_pnl"],
            benchmark_entry=row["benchmark_entry"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
