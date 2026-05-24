"""One-shot migration: legs.strike REAL → TEXT.

SQLite does not support ALTER COLUMN, so we use the recommended
rename-new-column approach:
  1. Add strike_text TEXT column.
  2. Copy REAL → TEXT via CAST (REAL integer strikes like 23000.0
     come back as '23000.0'; we normalise to '23000' by stripping
     trailing '.0' for whole numbers).
  3. Drop strike_text into place via a full table rebuild
     (new_legs temp → INSERT SELECT → DROP old → rename new).

Run once against the live DB after deploying faac98c:

    python -m scripts.migrate_strike_to_text [--db path/to/portfolio.sqlite]

Safe to re-run: checks column type first and exits early if already TEXT.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


DEFAULT_DB = Path(__file__).parent.parent / "data" / "portfolio" / "portfolio.sqlite"


def _col_type(conn: sqlite3.Connection, table: str, col: str) -> str | None:
    """Return declared type of *col* in *table*, or None if not found."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    for r in rows:
        if r[1] == col:
            return r[2]
    return None


def _to_text_strike(raw: float | None) -> str | None:
    """Convert a REAL strike value to canonical TEXT representation.

    Whole-number floats (23000.0) → '23000'.
    Fractional values (17525.5) → '17525.5'.
    None → None.
    """
    if raw is None:
        return None
    d = float(raw)
    if d == int(d):
        return str(int(d))
    return str(d)


def migrate(db_path: Path) -> None:
    """Run the REAL→TEXT migration on *db_path* in a single transaction."""
    if not db_path.exists():
        print(f"ERROR: database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        current_type = _col_type(conn, "legs", "strike")
        if current_type == "TEXT":
            print("legs.strike is already TEXT — nothing to do.")
            conn.close()
            return

        print(f"legs.strike is currently {current_type!r} — migrating to TEXT ...")

        # Read all rows before touching the schema.
        rows = conn.execute("SELECT * FROM legs").fetchall()
        print(f"  {len(rows)} leg rows to migrate.")

        with conn:  # single transaction
            # Step 1: rebuild the legs table with strike as TEXT.
            conn.executescript("""
                CREATE TABLE legs_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id INTEGER NOT NULL REFERENCES strategies(id),
                    instrument_key TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    lot_size INTEGER NOT NULL DEFAULT 1,
                    entry_price TEXT NOT NULL,
                    entry_date TEXT NOT NULL,
                    expiry TEXT,
                    strike TEXT,
                    product_type TEXT NOT NULL
                );
            """)

            # Step 2: insert rows with normalised strike TEXT.
            for r in rows:
                conn.execute(
                    """INSERT INTO legs_new
                       (id, strategy_id, instrument_key, display_name,
                        asset_type, direction, quantity, lot_size,
                        entry_price, entry_date, expiry, strike, product_type)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        r["id"],
                        r["strategy_id"],
                        r["instrument_key"],
                        r["display_name"],
                        r["asset_type"],
                        r["direction"],
                        r["quantity"],
                        r["lot_size"],
                        r["entry_price"],
                        r["entry_date"],
                        r["expiry"],
                        _to_text_strike(r["strike"]),
                        r["product_type"],
                    ),
                )

            # Step 3: swap old table out, new table in.
            conn.executescript("""
                DROP TABLE legs;
                ALTER TABLE legs_new RENAME TO legs;
                CREATE INDEX IF NOT EXISTS idx_legs_strategy ON legs(strategy_id);
            """)

        # Verify.
        new_type = _col_type(conn, "legs", "strike")
        migrated_rows = conn.execute("SELECT COUNT(*) FROM legs").fetchone()[0]
        print(f"  Done. legs.strike is now {new_type!r}. {migrated_rows} rows present.")

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"Path to portfolio.sqlite (default: {DEFAULT_DB})",
    )
    args = parser.parse_args()
    migrate(args.db)


if __name__ == "__main__":
    main()
