"""SQLite persistence for the MVP value-picks tracker."""

from __future__ import annotations

from pathlib import Path

from src.db import connect
from src.mvp.models import Category, Provider


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
