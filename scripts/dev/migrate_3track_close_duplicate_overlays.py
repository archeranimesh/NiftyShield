"""One-time data migration: retire duplicate overlay legs (S1r).

Story: docs/plan/3track-consolidation/stories.md#S1r. Supersedes S1's original
"leave survivor under paper_nifty_spot" outcome — the survivor is now
re-homed to the track-independent strategy_name ``paper_nifty_overlay``.

Three steps, in order:

1. Close the genuine Futures/Proxy overlay duplicates (``overlay_collar_call``,
   ``overlay_collar_put``, ``overlay_pp``) at live LTP, with intrinsic-value
   fallback for post-expiry legs — reuses ``close_ic_legs()``'s LTP-fetch/
   fallback logic (it is IC-agnostic despite the name: it only needs a
   BrokerClient, a PaperStore, a list of PaperPosition, and a set of
   leg_role values to close).
2. Fix the S1b state bug: the ``overlay_cc`` closing BUY (NSE_FO|71474,
   2026-06-08) is tagged ``state='OPEN'`` for ``paper_nifty_spot`` and
   ``paper_nifty_proxy`` even though it is net flat (bought back) — the
   near-identical ``overlay_collar_call`` closing BUY at the same
   price/date is correctly ``CLOSED``.
3. Re-home every ``overlay_*`` leg_role row still under ``paper_nifty_spot``
   to ``strategy_name='paper_nifty_overlay'`` — a rename of ownership, not a
   new trade. Same trade_date/price/quantity, only strategy_name changes.

Registry note: neither ``paper_trades.strategy_name`` nor ``paper_strategies``
enforce a static strategy registry (confirmed via graph query before writing
this script) — ``paper_strategies`` rows are created lazily by PaperStore on
first write, and ``paper_trades.strategy_name`` is unconstrained TEXT. No
schema change or registry edit is needed to introduce ``paper_nifty_overlay``.

Idempotent — safe to re-run. Step 1 is naturally idempotent (nothing left to
close once duplicates are gone). Steps 2 and 3 use ``WHERE`` clauses that
select nothing once already applied.

``--dry-run`` (default): reports what would happen, writes nothing.
``--apply``: executes all three steps.

Usage:
    python -m scripts.dev.migrate_3track_close_duplicate_overlays
    python -m scripts.dev.migrate_3track_close_duplicate_overlays --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.client.factory import create_client
from src.config import settings
from src.paper.constants import DEFAULT_DB_PATH
from src.paper.store import PaperStore
from src.strategy.ic_close_executor import close_ic_legs

_SCRIPT_NAME = "scripts.dev.migrate_3track_close_duplicate_overlays"
logger = structlog.get_logger(_SCRIPT_NAME)

# Strategy namespaces whose overlay legs are duplicates to be closed (S1).
_DUPLICATE_STRATEGIES: tuple[str, ...] = ("paper_nifty_futures", "paper_nifty_proxy")

# Overlay leg roles that exist as physical duplicates across tracks under RQ2.
_DUPLICATE_OVERLAY_ROLES: frozenset[str] = frozenset(
    {"overlay_collar_call", "overlay_collar_put", "overlay_pp"}
)

# S1b: the specific mis-tagged closing BUY row.
_CC_BUG_LEG_ROLE = "overlay_cc"
_CC_BUG_INSTRUMENT_KEY = "NSE_FO|71474"
_CC_BUG_TRADE_DATE = "2026-06-08"
_CC_BUG_STRATEGIES: tuple[str, ...] = ("paper_nifty_spot", "paper_nifty_proxy")

# S1r destination: track-independent overlay namespace.
_SOURCE_STRATEGY = "paper_nifty_spot"
_OVERLAY_STRATEGY = "paper_nifty_overlay"

_CLOSE_NOTES = "S1r: retire duplicate Futures/Proxy overlay leg (RQ2 cleanup)"


def _fix_cc_state_bug(conn: sqlite3.Connection, *, apply: bool) -> list[sqlite3.Row]:
    """Find (and, if applying, fix) the S1b mis-tagged overlay_cc state row.

    Args:
        conn: Open SQLite connection.
        apply: If True, execute the UPDATE. If False, only report matches.

    Returns:
        The matching rows (pre-fix), for reporting.
    """
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in _CC_BUG_STRATEGIES)
    rows = conn.execute(
        f"""
        SELECT id, strategy_name, leg_role, instrument_key, trade_date, action, state
        FROM paper_trades
        WHERE strategy_name IN ({placeholders})
          AND leg_role = ?
          AND instrument_key = ?
          AND trade_date = ?
          AND action = 'BUY'
          AND state = 'OPEN'
        """,
        (*_CC_BUG_STRATEGIES, _CC_BUG_LEG_ROLE, _CC_BUG_INSTRUMENT_KEY, _CC_BUG_TRADE_DATE),
    ).fetchall()

    if apply and rows:
        conn.execute(
            f"""
            UPDATE paper_trades
            SET state = 'CLOSED'
            WHERE strategy_name IN ({placeholders})
              AND leg_role = ?
              AND instrument_key = ?
              AND trade_date = ?
              AND action = 'BUY'
              AND state = 'OPEN'
            """,
            (*_CC_BUG_STRATEGIES, _CC_BUG_LEG_ROLE, _CC_BUG_INSTRUMENT_KEY, _CC_BUG_TRADE_DATE),
        )
        conn.commit()

    return rows


def _rehome_surviving_overlay_rows(conn: sqlite3.Connection, *, apply: bool) -> list[sqlite3.Row]:
    """Find (and, if applying, rename) surviving overlay rows to the new namespace.

    Args:
        conn: Open SQLite connection.
        apply: If True, execute the UPDATE. If False, only report matches.

    Returns:
        The matching rows (pre-rename), for reporting.
    """
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, strategy_name, leg_role, instrument_key, trade_date, action, state
        FROM paper_trades
        WHERE strategy_name = ?
          AND leg_role LIKE 'overlay_%'
        """,
        (_SOURCE_STRATEGY,),
    ).fetchall()

    if apply and rows:
        conn.execute(
            """
            UPDATE paper_trades
            SET strategy_name = ?
            WHERE strategy_name = ?
              AND leg_role LIKE 'overlay_%'
            """,
            (_OVERLAY_STRATEGY, _SOURCE_STRATEGY),
        )
        conn.commit()

    return rows


async def _close_duplicates(store: PaperStore, *, apply: bool) -> dict[str, list[str]]:
    """Close the genuine Futures/Proxy overlay duplicates.

    Args:
        store: PaperStore for position lookup and (if applying) persistence.
        apply: If True, actually fetch LTP and write closing trades. If
            False, only report which positions would be closed.

    Returns:
        Mapping of strategy_name -> list of leg_role values closed (or, in
        dry-run mode, that would be closed).
    """
    broker = create_client(settings.upstox_env)
    result: dict[str, list[str]] = {}

    for strategy_name in _DUPLICATE_STRATEGIES:
        positions = store.get_positions(strategy_name)
        to_close = [p for p in positions if p.leg_role in _DUPLICATE_OVERLAY_ROLES]
        if not to_close:
            result[strategy_name] = []
            continue

        if not apply:
            result[strategy_name] = [f"{p.leg_role}:{p.instrument_key}" for p in to_close]
            continue

        closed = await close_ic_legs(
            broker=broker,
            store=store,
            positions=positions,
            closed_roles=_DUPLICATE_OVERLAY_ROLES,
            strategy_name=strategy_name,
            notes=_CLOSE_NOTES,
        )
        result[strategy_name] = [t.leg_role for t in closed]

    return result


async def migrate(db_path: Path, *, apply: bool) -> None:
    """Run the S1r migration against the given database.

    Args:
        db_path: Path to the portfolio SQLite database.
        apply: If True, execute all writes. If False (default), report only.
    """
    mode = "APPLY" if apply else "DRY-RUN"
    logger.info("migrate.start", mode=mode, db_path=str(db_path))

    store = PaperStore(db_path)
    closed = await _close_duplicates(store, apply=apply)
    for strategy_name, roles in closed.items():
        logger.info(
            "migrate.duplicates_closed" if apply else "migrate.duplicates_would_close",
            strategy_name=strategy_name,
            legs=roles,
        )

    with sqlite3.connect(db_path) as conn:
        cc_rows = _fix_cc_state_bug(conn, apply=apply)
        logger.info(
            "migrate.cc_state_bug_fixed" if apply else "migrate.cc_state_bug_would_fix",
            row_ids=[r["id"] for r in cc_rows],
            strategies=sorted({r["strategy_name"] for r in cc_rows}),
        )

        rehomed = _rehome_surviving_overlay_rows(conn, apply=apply)
        logger.info(
            "migrate.overlay_rehomed" if apply else "migrate.overlay_would_rehome",
            row_count=len(rehomed),
            leg_roles=sorted({r["leg_role"] for r in rehomed}),
            destination=_OVERLAY_STRATEGY,
        )

    logger.info("migrate.complete", mode=mode)


def main() -> None:
    """CLI entry point."""
    from src.utils.logging import setup_logging

    setup_logging()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite DB (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the migration. Without this flag, runs in dry-run mode (default).",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: DB not found at {args.db_path}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(migrate(args.db_path, apply=args.apply))


if __name__ == "__main__":
    main()
