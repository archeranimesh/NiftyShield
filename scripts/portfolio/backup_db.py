"""Online SQLite backup script with retention pruning.

Creates a safe, online backup of the WAL-mode portfolio database using the
sqlite3.Connection.backup() API, followed by retention pruning to keep
a specified window of daily and monthly snapshots.
"""

from __future__ import annotations

import collections
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

from src.config import settings
from src.db import connect
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.portfolio.backup_db"
logger = structlog.get_logger(_SCRIPT_NAME)


def backup_database(backup_dir: Path) -> Path:
    """Take an online backup of the live SQLite database.

    Args:
        backup_dir: Directory where the backup file will be written.

    Returns:
        Path to the created backup file.
    """
    source_db_path = Path(settings.db_path)
    if not source_db_path.exists():
        logger.error("source_db_not_found", path=str(source_db_path))
        sys.exit(1)

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"portfolio_{timestamp}.sqlite"

    logger.info(
        "starting_online_backup",
        source=str(source_db_path),
        target=str(backup_file),
    )

    with connect(source_db_path) as source_conn:
        with sqlite3.connect(backup_file) as dest_conn:
            source_conn.backup(dest_conn)

    logger.info(
        "backup_completed",
        target=str(backup_file),
        size_bytes=backup_file.stat().st_size,
    )
    return backup_file


def prune_backups(backup_dir: Path, daily_keep: int = 30, monthly_keep: int = 12) -> None:
    """Prune older backups outside the retention window.

    Keeps the newest `daily_keep` daily backups and the newest
    `monthly_keep` monthly backups.

    Args:
        backup_dir: Directory containing the backup files.
        daily_keep: Number of newest daily backups to retain.
        monthly_keep: Number of newest monthly backups to retain.
    """
    backups: list[tuple[datetime, Path]] = []
    for p in backup_dir.glob("portfolio_*.sqlite"):
        try:
            stem_parts = p.stem.split("_")
            if len(stem_parts) == 3:
                date_str = stem_parts[1]
                time_str = stem_parts[2]
                dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                backups.append((dt, p))
        except ValueError:
            continue

    backups.sort(key=lambda x: x[0], reverse=True)

    daily_candidates: dict[str, Path] = collections.OrderedDict()
    monthly_candidates: dict[str, Path] = collections.OrderedDict()

    for dt, p in backups:
        day_key = dt.strftime("%Y%m%d")
        month_key = dt.strftime("%Y%m")

        if day_key not in daily_candidates:
            daily_candidates[day_key] = p
        if month_key not in monthly_candidates:
            monthly_candidates[month_key] = p

    retained_daily = set(list(daily_candidates.values())[:daily_keep])
    retained_monthly = set(list(monthly_candidates.values())[:monthly_keep])
    retained_all = retained_daily | retained_monthly

    deleted_count = 0
    for _dt, p in backups:
        if p not in retained_all:
            logger.info("pruning_old_backup", file=p.name)
            p.unlink()
            deleted_count += 1

    logger.info(
        "pruning_completed",
        retained=len(retained_all),
        deleted=deleted_count,
    )


def main() -> None:
    setup_logging()
    backup_dir = Path("backups/portfolio")
    backup_database(backup_dir)
    prune_backups(backup_dir)


if __name__ == "__main__":
    main()
