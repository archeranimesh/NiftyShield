"""Read-only verification for the overlay cleanup discussion (BUG-028 follow-on).

Not part of the BUG-028 Phase 3 deliverable — throwaway inspection script per
CLAUDE.md's scratch/ convention. Prints exactly what each candidate DELETE/UPDATE
would touch, split into "legacy-attributed only" (spot/futures/proxy) vs. "all
overlay data including today's live paper_nifty_overlay PP trade" so Animesh can
decide scope before anything runs for real. No writes.

Usage:
    python3 scratch/2026-08-10_overlay_cleanup_verify.py
"""

import sqlite3

DB = "data/portfolio/portfolio.sqlite"
LEGACY = ("paper_nifty_spot", "paper_nifty_futures", "paper_nifty_proxy")
ALL_OVERLAY_STRATEGIES = LEGACY + ("paper_nifty_overlay",)


def show(conn, label, sql, params=()):
    rows = conn.execute(sql, params).fetchall()
    print(f"\n=== {label} ({len(rows)} row(s)) ===")
    for r in rows:
        print(" ", dict(r))


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print("############################################")
    print("# SCOPE A: legacy-attributed only (spot/futures/proxy)")
    print("# — what the 'clean up misattribution, keep live PP' plan touches")
    print("############################################")

    show(
        conn,
        "paper_trades under legacy strategy_names, overlay leg_role",
        f"""SELECT strategy_name, leg_role, trade_date, action, quantity, price
            FROM paper_trades
            WHERE strategy_name IN ({",".join("?" * len(LEGACY))})
              AND leg_role LIKE 'overlay_%'
            ORDER BY trade_date""",
        LEGACY,
    )

    show(
        conn,
        "paper_overlay_pnl_snapshots under legacy strategy_names",
        f"""SELECT strategy_name, overlay_type, snapshot_date
            FROM paper_overlay_pnl_snapshots
            WHERE strategy_name IN ({",".join("?" * len(LEGACY))})
            ORDER BY snapshot_date""",
        LEGACY,
    )

    show(
        conn,
        "paper_leg_snapshots under legacy strategy_names, overlay leg_role",
        f"""SELECT strategy_name, leg_role, COUNT(*) n, MIN(snapshot_date) first, MAX(snapshot_date) last
            FROM paper_leg_snapshots
            WHERE strategy_name IN ({",".join("?" * len(LEGACY))})
              AND leg_role LIKE 'overlay_%'
            GROUP BY strategy_name, leg_role""",
        LEGACY,
    )

    show(
        conn,
        "paper_exit_events under legacy strategy_names, overlay leg_name",
        f"""SELECT strategy_name, leg_name, COUNT(*) n
            FROM paper_exit_events
            WHERE strategy_name IN ({",".join("?" * len(LEGACY))})
              AND leg_name LIKE 'overlay_%'
            GROUP BY strategy_name, leg_name""",
        LEGACY,
    )

    show(
        conn,
        "paper_protection_recovery_snapshots rows with any non-null overlay column",
        """SELECT snapshot_date, cc_pnl_1d, pp_pnl_1d, collar_pnl_1d
            FROM paper_protection_recovery_snapshots
            WHERE cc_pnl_1d IS NOT NULL OR pp_pnl_1d IS NOT NULL OR collar_pnl_1d IS NOT NULL
            ORDER BY snapshot_date""",
    )

    print("\n\n############################################")
    print("# SCOPE B: everything overlay-related, INCLUDING today's live PP")
    print("# — additional rows Scope A does NOT touch")
    print("############################################")

    show(
        conn,
        "paper_trades under paper_nifty_overlay (the live trade)",
        """SELECT strategy_name, leg_role, trade_date, action, quantity, price, state
            FROM paper_trades WHERE strategy_name = 'paper_nifty_overlay'
            ORDER BY trade_date""",
    )

    show(
        conn,
        "paper_leg_snapshots under paper_nifty_overlay",
        """SELECT leg_role, COUNT(*) n, MIN(snapshot_date) first, MAX(snapshot_date) last
            FROM paper_leg_snapshots WHERE strategy_name = 'paper_nifty_overlay'
            GROUP BY leg_role""",
    )

    show(
        conn,
        "paper_overlay_pnl_snapshots under paper_nifty_overlay",
        """SELECT overlay_type, snapshot_date FROM paper_overlay_pnl_snapshots
            WHERE strategy_name = 'paper_nifty_overlay' ORDER BY snapshot_date""",
    )

    show(
        conn,
        "paper_action_audit under paper_nifty_overlay",
        """SELECT action_type, leg_role, executed_at FROM paper_action_audit
            WHERE strategy_name = 'paper_nifty_overlay' ORDER BY executed_at""",
    )

    conn.close()
    print("\nNo writes performed — this script is read-only.")


if __name__ == "__main__":
    main()
