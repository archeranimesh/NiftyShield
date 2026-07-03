# scripts/strategies/ic/paper_ic_monthly_comparison.py
"""EOD cron script comparing V1 and V2 monthly Iron Condors side-by-side."""

import argparse
import asyncio
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.client.factory import create_client
from src.client.upstox_market import parse_upstox_option_chain
from src.config import settings
from src.notifications.telegram_gateway import TelegramGateway
from src.paper.constants import DEFAULT_DB_PATH
from src.paper.store import PaperStore
from src.strategy.ic_expiry_config import CONFIGS as V1_CONFIGS
from src.strategy.ic_expiry_config_v2 import IC_V2_MONTHLY as V2_CONFIG
from src.strategy.ic_nifty_v1 import IronCondorV1
from src.strategy.ic_nifty_v2 import IronCondorV2
from src.utils.logging import setup_logging

V1_CONFIG = V1_CONFIGS["monthly"]

load_dotenv()

_SCRIPT_NAME = "scripts.strategies.ic.paper_ic_monthly_comparison"
logger = structlog.get_logger(_SCRIPT_NAME)


@dataclass
class ICMonthlyStats:
    strategy_name: str
    entry_credit_pts: Decimal | None
    current_mark_pts: Decimal | None
    captured_fraction: Decimal | None
    dte: int | None
    short_put_delta: Decimal | None
    short_call_delta: Decimal | None
    profit_lock_zone: int
    realized_pnl_month: Decimal
    unrealized_pnl: Decimal
    signals_fired_today: list[str]
    roll_count: int
    lock_count: int


def _get_monthly_realized_pnl(store: PaperStore, strategy_name: str, today: date) -> Decimal:
    start_of_month = date(today.year, today.month, 1)
    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        curr_row = conn.execute(
            """SELECT realized_pnl FROM paper_nav_snapshots
               WHERE strategy_name = ? AND snapshot_date <= ?
               ORDER BY snapshot_date DESC LIMIT 1""",
            (strategy_name, today.isoformat()),
        ).fetchone()

        prev_row = conn.execute(
            """SELECT realized_pnl FROM paper_nav_snapshots
               WHERE strategy_name = ? AND snapshot_date < ?
               ORDER BY snapshot_date DESC LIMIT 1""",
            (strategy_name, start_of_month.isoformat()),
        ).fetchone()

        curr_val = Decimal(curr_row["realized_pnl"]) if curr_row else Decimal("0")
        prev_val = Decimal(prev_row["realized_pnl"]) if prev_row else Decimal("0")
        return curr_val - prev_val


def _get_cycle_start_date(store: PaperStore, strategy_name: str) -> str | None:
    positions = store.get_positions(strategy_name)
    open_pos = [p for p in positions if p.net_qty != 0]
    if not open_pos:
        return None
    dts = [p.entry_date for p in open_pos if p.entry_date is not None]
    if not dts:
        return None
    return min(dts).isoformat()


def _get_adjustment_count(
    store: PaperStore, strategy_name: str, cycle_start_str: str | None
) -> tuple[int, int]:
    if not cycle_start_str:
        return 0, 0
    with sqlite3.connect(store.db_path) as conn:
        rolls = conn.execute(
            """SELECT COUNT(*) as cnt FROM paper_exit_events
               WHERE strategy_name = ?
                 AND status = 'ACTED'
                 AND event_time >= ?
                 AND exit_signal = 'ROLL_WING'""",
            (strategy_name, cycle_start_str),
        ).fetchone()
        locks = conn.execute(
            """SELECT COUNT(*) as cnt FROM paper_exit_events
               WHERE strategy_name = ?
                 AND status = 'ACTED'
                 AND event_time >= ?
                 AND exit_signal = 'PROFIT_LOCK_ZONE2'""",
            (strategy_name, cycle_start_str),
        ).fetchone()
        return (rolls[0] if rolls else 0), (locks[0] if locks else 0)


def _get_signals_today(store: PaperStore, strategy_name: str, today: date) -> list[str]:
    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT exit_signal FROM paper_exit_events
               WHERE strategy_name = ?
                 AND event_time >= ?""",
            (strategy_name, today.isoformat()),
        ).fetchall()

        # Unique signals preserving order
        seen = set()
        out = []
        for r in rows:
            sig = r["exit_signal"]
            if sig not in seen:
                seen.add(sig)
                out.append(sig)
        return out


def _get_unrealized_pnl(store: PaperStore, strategy_name: str, today: date) -> Decimal:
    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT unrealized_pnl FROM paper_nav_snapshots
               WHERE strategy_name = ? AND snapshot_date = ?
               LIMIT 1""",
            (strategy_name, today.isoformat()),
        ).fetchone()
        return Decimal(row["unrealized_pnl"]) if row else Decimal("0")


def _get_profit_lock_zone(store: PaperStore, strategy_name: str) -> int:
    try:
        state = store.get_profit_lock_state(strategy_name)
        return state.profit_lock_zone
    except AttributeError:
        # Expected for V1 or if method not found
        return 0
    except Exception:
        return 0


async def build_stats(
    strategy_name: str,
    strategy_cls: type,
    config: Any,
    store: PaperStore,
    broker: Any,
    today: date,
) -> ICMonthlyStats:
    positions = store.get_positions(strategy_name)
    open_pos = [p for p in positions if p.net_qty != 0]

    realized_month = _get_monthly_realized_pnl(store, strategy_name, today)
    unrealized = _get_unrealized_pnl(store, strategy_name, today)
    signals_today = _get_signals_today(store, strategy_name, today)
    cycle_start = _get_cycle_start_date(store, strategy_name)
    roll_count, lock_count = _get_adjustment_count(store, strategy_name, cycle_start)
    lock_zone = _get_profit_lock_zone(store, strategy_name)

    if not open_pos:
        return ICMonthlyStats(
            strategy_name=strategy_name,
            entry_credit_pts=None,
            current_mark_pts=None,
            captured_fraction=None,
            dte=None,
            short_put_delta=None,
            short_call_delta=None,
            profit_lock_zone=0,
            realized_pnl_month=realized_month,
            unrealized_pnl=unrealized,
            signals_fired_today=signals_today,
            roll_count=0,
            lock_count=0,
        )

    ic = strategy_cls(broker, store, None, config)

    # Determine expiry date
    _EXPIRY_RE = re.compile(r"NIFTY(\d{2}[A-Za-z]{3}\d{4})", re.IGNORECASE)
    expiry = None
    for p in open_pos:
        m = _EXPIRY_RE.search(p.instrument_key)
        if m:
            try:
                expiry = datetime.strptime(m.group(1).upper(), "%d%b%Y").date()
                break
            except ValueError:
                pass

    dte = (expiry - today).days if expiry else None

    # Fetch live option chain
    try:
        raw_chain = await broker.get_option_chain(
            "NSE_INDEX|Nifty 50", expiry.isoformat() if expiry else ""
        )
        chain_data = raw_chain if isinstance(raw_chain, list) else []
        chain = parse_upstox_option_chain(chain_data)
    except Exception:
        chain = None

    entry_credit = None
    combined_mark = None
    captured_fraction = None
    short_put_delta = None
    short_call_delta = None

    if chain:
        try:
            combined_mark, entry_credit = ic._compute_combined_pnl(chain, open_pos)
            if entry_credit and entry_credit > 0 and combined_mark is not None:
                captured_fraction = (entry_credit - combined_mark) / entry_credit
        except Exception:
            pass

        try:
            put_pos = next((p for p in open_pos if p.leg_role == "short_put"), None)
            if put_pos:
                leg = ic._find_leg(chain, put_pos.instrument_key)
                if leg:
                    short_put_delta = leg.delta
        except Exception:
            pass

        try:
            call_pos = next((p for p in open_pos if p.leg_role == "short_call"), None)
            if call_pos:
                leg = ic._find_leg(chain, call_pos.instrument_key)
                if leg:
                    short_call_delta = leg.delta
        except Exception:
            pass

    return ICMonthlyStats(
        strategy_name=strategy_name,
        entry_credit_pts=entry_credit,
        current_mark_pts=combined_mark,
        captured_fraction=captured_fraction,
        dte=dte,
        short_put_delta=short_put_delta,
        short_call_delta=short_call_delta,
        profit_lock_zone=lock_zone,
        realized_pnl_month=realized_month,
        unrealized_pnl=unrealized,
        signals_fired_today=signals_today,
        roll_count=roll_count,
        lock_count=lock_count,
    )


def build_comparison_report(v1: ICMonthlyStats, v2: ICMonthlyStats, report_date: date) -> str:
    """Build a Telegram-formatted plain-text comparison table."""

    def fmt_pts(v: Decimal | None) -> str:
        return f"₹{v:,.0f}" if v is not None else "N/A"

    def fmt_pct(v: Decimal | None) -> str:
        return f"{int(round(v * 100))}%" if v is not None else "N/A"

    def fmt_delta(v: Decimal | None) -> str:
        return f"{v:.2f}" if v is not None else "N/A"

    def fmt_dte(v: int | None) -> str:
        return str(v) if v is not None else "N/A"

    def fmt_pnl(v: Decimal) -> str:
        return f"₹{v:,.0f}"

    def fmt_zone(z: int, is_v2: bool) -> str:
        if not is_v2:
            return "N/A"
        return f"Zone {z} ✓" if z > 0 else "None"

    def fmt_adj(v1_stat: bool, rolls: int, locks: int) -> str:
        if v1_stat:
            return f"{rolls} rolls"
        else:
            return f"{rolls} rolls + {locks} locks"

    def fmt_sigs(sigs: list[str]) -> str:
        if not sigs:
            return "—"
        return ", ".join(sigs)

    # Edge calculation
    v1_total = v1.realized_pnl_month + v1.unrealized_pnl
    v2_total = v2.realized_pnl_month + v2.unrealized_pnl
    edge_diff = v2_total - v1_total

    if edge_diff > 0:
        edge_line = f"Edge so far:  V2 +₹{edge_diff:,.0f} vs V1"
    elif edge_diff < 0:
        edge_line = f"Edge so far:  V1 +₹{-edge_diff:,.0f} vs V2"
    else:
        edge_line = "Edge so far:  Tied"

    # Handle missing positions gracefully
    v1_open = v1.dte is not None
    v2_open = v2.dte is not None

    def safe_col(val: str, is_open: bool) -> str:
        return val if is_open else "No open position"

    lines = [
        f"📊 IC Monthly Comparison — {report_date.isoformat()}",
        "",
        "                    V1 Monthly      V2 Monthly",
        "─────────────────────────────────────────────",
        f"Entry credit        {safe_col(fmt_pts(v1.entry_credit_pts), v1_open):<15} {safe_col(fmt_pts(v2.entry_credit_pts), v2_open)}",
        f"Captured            {safe_col(fmt_pct(v1.captured_fraction), v1_open):<15} {safe_col(fmt_pct(v2.captured_fraction), v2_open)}",
        f"Short put Δ         {safe_col(fmt_delta(v1.short_put_delta), v1_open):<15} {safe_col(fmt_delta(v2.short_put_delta), v2_open)}",
        f"Short call Δ        {safe_col(fmt_delta(v1.short_call_delta), v1_open):<15} {safe_col(fmt_delta(v2.short_call_delta), v2_open)}",
        f"DTE                 {safe_col(fmt_dte(v1.dte), v1_open):<15} {safe_col(fmt_dte(v2.dte), v2_open)}",
        f"Unrealized P&L      {fmt_pnl(v1.unrealized_pnl):<15} {fmt_pnl(v2.unrealized_pnl)}",
        f"Realized (month)    {fmt_pnl(v1.realized_pnl_month):<15} {fmt_pnl(v2.realized_pnl_month)}",
        f"Profit-lock zone    {safe_col(fmt_zone(v1.profit_lock_zone, False), v1_open):<15} {safe_col(fmt_zone(v2.profit_lock_zone, True), v2_open)}",
        f"Adjustments         {safe_col(fmt_adj(True, v1.roll_count, v1.lock_count), v1_open):<15} {safe_col(fmt_adj(False, v2.roll_count, v2.lock_count), v2_open)}",
        f"Signals today       {fmt_sigs(v1.signals_fired_today):<15} {fmt_sigs(v2.signals_fired_today)}",
        "",
        edge_line,
    ]

    return "\n".join(lines)


async def _run(args: argparse.Namespace) -> None:
    setup_logging()
    report_date: date = args.date or date.today()
    save: bool = not args.dry_run

    store = PaperStore(args.db_path)

    try:
        broker = create_client(settings.upstox_env)
    except ValueError:
        if args.dry_run:

            class _MockBroker:
                async def get_ltp(self, keys: list[str]) -> dict[str, Decimal]:
                    return {k: Decimal("0.0") for k in keys}

                async def get_option_chain(
                    self, underlying: str, expiry: str
                ) -> list[dict[str, Any]]:
                    return []

            broker = _MockBroker()
        else:
            logger.error("ic_monthly_comparison.broker_init_failed")
            sys.exit(1)

    bot_token = settings.telegram_bot_token or ""
    chat_id = settings.telegram_chat_id or ""
    notifier = (
        TelegramGateway(bot_token, chat_id, str(args.db_path)) if bot_token and chat_id else None
    )

    v1_stats = await build_stats(
        strategy_name="paper_ic_nifty_v1_monthly",
        strategy_cls=IronCondorV1,
        config=V1_CONFIG,
        store=store,
        broker=broker,
        today=report_date,
    )

    v2_stats = await build_stats(
        strategy_name="paper_ic_nifty_v2_monthly",
        strategy_cls=IronCondorV2,
        config=V2_CONFIG,
        store=store,
        broker=broker,
        today=report_date,
    )

    report_str = build_comparison_report(v1_stats, v2_stats, report_date)
    print(f"\n{report_str}\n")

    if notifier and save:
        logger.info(
            "ic_monthly_comparison.report_sent",
            channel="telegram",
            report_date=report_date.isoformat(),
            v1_strategy=v1_stats.strategy_name,
            v2_strategy=v2_stats.strategy_name,
        )
        try:
            await notifier.send_notification(report_str)
        except Exception as exc:
            logger.warning("ic_monthly_comparison.telegram_failed", error=str(exc))


def main() -> None:
    parser = argparse.ArgumentParser(description="EOD IC V1 vs V2 Monthly comparison cron.")
    parser.add_argument(
        "--date",
        default=None,
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="Report date (default: today).",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print report only (default: on).",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite DB path (default: {DEFAULT_DB_PATH})",
    )

    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
