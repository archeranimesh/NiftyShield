# scripts/strategies/ic/paper_ic_snapshot.py
"""EOD audit cron for all Iron Condor variants.

Iterates over all four Iron Condor variants, evaluates exit signals, queries for
intraday acted events, and sends/prints an EOD audit report.
"""

# fmt: off
from __future__ import annotations

import argparse
import asyncio
import re
import sqlite3
import sys
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
from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.notifications.telegram_gateway import TelegramGateway
from src.paper.constants import DEFAULT_BOD_PATH, DEFAULT_DB_PATH, LOT_SIZE
from src.paper.store import PaperStore
from src.strategy.ic_expiry_config import CONFIGS
from src.strategy.ic_expiry_config_v2 import CONFIGS_V2
from src.strategy.ic_nifty_v1 import IronCondorV1
from src.strategy.ic_nifty_v2 import IronCondorV2
from src.utils.logging import setup_logging

load_dotenv()

_SCRIPT_NAME = "scripts.strategies.ic.paper_ic_snapshot"
logger = structlog.get_logger(_SCRIPT_NAME)



def parse_key_details(instrument_key: str) -> tuple[str, str]:
    """Extract strike and CE/PE from instrument key.

    Supports:
      - NSE_FO|NIFTY26JUN202624000PE -> ("24000", "PE")
      - NSE_FO|NIFTY26JUN2026PE24000 -> ("24000", "PE")
      - NSE_FO|NIFTY22000PE          -> ("22000", "PE")
    """
    m1 = re.search(
        r"NIFTY(?:\d{2}[A-Za-z]{3}\d{4})?(\d+)(PE|CE)",
        instrument_key,
        re.IGNORECASE,
    )
    if m1:
        return m1.group(1), m1.group(2).upper()
    m2 = re.search(
        r"NIFTY(?:\d{2}[A-Za-z]{3}\d{4})?(PE|CE)(\d+)",
        instrument_key,
        re.IGNORECASE,
    )
    if m2:
        return m2.group(2), m2.group(1).upper()
    return "", ""


def format_leg_label(
    instrument_key: str, lookup: InstrumentLookup, expiry: date
) -> str:
    """Build a human-readable leg label for the EOD report, e.g. "NIFTY 22900 PE 28 JUL 26".

    Tries the fast regex parse first (``parse_key_details``); real Upstox
    keys are numeric-only (e.g. ``NSE_FO|63930``) and never match, so those
    fall back to a BOD instrument-master lookup for ``strike_price``, same
    fallback already used by ``IronCondorV1/V2._find_leg`` (BUG-012).
    ``expiry`` is passed in rather than re-resolved per leg since the
    variant's expiry is already known from the earlier reverse-lookup pass
    in ``process_variant`` and is identical for every leg of one IC.

    Args:
        instrument_key: Position's Upstox instrument key.
        lookup: Offline BOD instrument master.
        expiry: The IC variant's resolved expiry date.

    Returns:
        Formatted label, or the raw ``instrument_key`` when neither the
        regex nor the BOD lookup can resolve a strike/option type.
    """
    strike_num, opt_type = parse_key_details(instrument_key)
    if not strike_num:
        try:
            inst = lookup.get_by_key(instrument_key)
        except Exception as exc:  # Intentional: fail-safe BOD lookup
            logger.warning(
                "ic_snapshot.leg_label_bod_lookup_failed",
                instrument_key=instrument_key,
                error=str(exc),
            )
            inst = None
        if inst is not None and inst.get("strike_price") is not None:
            resolved_type = inst.get("instrument_type")
            if resolved_type in ("CE", "PE"):
                strike_decimal = Decimal(str(inst["strike_price"]))
                strike_num = (
                    str(int(strike_decimal))
                    if strike_decimal == strike_decimal.to_integral_value()
                    else str(strike_decimal)
                )
                opt_type = resolved_type

    if not strike_num:
        return instrument_key

    return f"NIFTY {strike_num} {opt_type} {expiry.strftime('%d %b %y').upper()}"


def get_action_taken(row: dict[str, Any]) -> str:
    """Determine the action taken for an acted exit event."""
    if row.get("actual_rule_used"):
        return row["actual_rule_used"]
    notes = row.get("notes") or ""
    for act in [
        "CLOSE_FULL",
        "CLOSE_CALL_SPREAD",
        "CLOSE_PUT_SPREAD",
        "ROLL_WING",
    ]:
        if act in notes:
            return act
    sig = row.get("exit_signal")
    if sig in ["PROFIT_TARGET", "LOSS_STOP", "TIME_STOP", "DELTA_STOP"]:
        return "CLOSE_FULL"
    elif sig == "ROLL_WING":
        return "ROLL_WING"
    return "CLOSE_FULL"


async def process_variant(
    expiry_type: str,
    config: Any,
    store: PaperStore,
    broker: Any,
    lookup: InstrumentLookup,
    notifier: TelegramGateway | None,
    snap_date: date,
    save: bool,
    strategy_cls: type | None = None,
) -> str | None:
    """Process a single IC variant and return the generated report string."""
    if strategy_cls is None:
        strategy_cls = IronCondorV1
    positions = store.get_positions(config.strategy_name)
    ic_positions = [
        p for p in positions
        if p.strategy_name == config.strategy_name and p.net_qty != 0
    ]
    if not ic_positions:
        return None

    # Determine expiry date via reverse lookup against the offline instrument
    # master (numeric instrument_key, e.g. "NSE_FO|63930", has no embedded
    # date substring -- a regex against it can never match; see BUG-009).
    expiry = None
    for p in ic_positions:
        inst = lookup.get_by_key(p.instrument_key)
        if inst is None:
            continue
        expiry_str = parse_expiry(inst.get("expiry"))
        if expiry_str is None:
            continue
        try:
            expiry = date.fromisoformat(expiry_str)
            break
        except ValueError:
            pass

    if expiry is None:
        logger.warning(
            "ic_snapshot.no_expiry_found",
            strategy=config.strategy_name,
        )
        return (
            f"📋 IC EOD Audit — {expiry_type} ({config.strategy_name})\n"
            f"Error: Expiry date could not be parsed from positions."
        )

    dte = (expiry - snap_date).days

    # Fetch live option chain
    try:
        raw_chain = await broker.get_option_chain(
            "NSE_INDEX|Nifty 50", expiry.isoformat()
        )
        chain_data = raw_chain if isinstance(raw_chain, list) else []
        chain = parse_upstox_option_chain(chain_data)
    except Exception as exc:  # Intentional: fail-safe chain fetch
        logger.error(
            "ic_snapshot.chain_fetch_failed",
            strategy=config.strategy_name,
            expiry=expiry.isoformat(),
            error=str(exc),
        )
        return (
            f"📋 IC EOD Audit — {expiry_type} ({config.strategy_name})\n"
            f"Error: Failed to fetch live option chain."
        )

    # Fetch Nifty spot and VIX LTP
    nifty_spot = chain.underlying_spot

    # Instantiate strategy. Keyword args are mandatory here: IronCondorV1 and
    # IronCondorV2 declare their __init__ params in different orders
    # (V1: broker, store, notifier, config / V2: config, broker, store,
    # notifier), so a positional call binds the wrong object to `self._config`
    # for whichever class doesn't match. See BUG entry for the resulting
    # 'UpstoxLiveClient' object has no attribute 'expiry_type' failure.
    ic = strategy_cls(broker=broker, store=store, notifier=notifier, config=config)

    # Evaluate signals
    try:
        events = await ic.check_signals(chain, positions)
    except Exception as exc:  # Intentional: fail-safe signal checks
        logger.error(
            "ic_snapshot.check_signals_failed",
            strategy=config.strategy_name,
            error=str(exc),
        )
        return (
            f"📋 IC EOD Audit — {expiry_type} ({config.strategy_name})\n"
            f"Error: Signal evaluation failed."
        )

    # IVR
    ivr_str = ic._compute_ivr_str().split(": ")[1]

    # Build position lines
    role_order = [
        "short_put",
        "long_put_hedge",
        "short_call",
        "long_call_hedge",
    ]
    role_labels = {
        "short_put": "Short Put  ",
        "long_put_hedge": "Long Put   ",
        "short_call": "Short Call ",
        "long_call_hedge": "Long Call  ",
    }

    pos_lines = []
    for role in role_order:
        pos = next((p for p in ic_positions if p.leg_role == role), None)
        if pos is None:
            continue

        opt_leg = ic._find_leg(chain, pos.instrument_key)
        strike_suffix = format_leg_label(pos.instrument_key, lookup, expiry)

        ltp_val = opt_leg.ltp if opt_leg is not None else None
        ltp_str = f"LTP=₹{ltp_val:.2f}" if ltp_val is not None else "LTP=N/A"

        if role in ["short_put", "short_call"]:
            delta_val = (
                opt_leg.delta
                if (opt_leg is not None and opt_leg.delta is not None)
                else 0.0
            )
            delta_str = f"δ={delta_val:.2f}"
            entry_val = pos.avg_sell_price
            entry_str = f"(entry ₹{entry_val:.2f})"
            pos_lines.append(
                f"  {role_labels[role]} {strike_suffix}  "
                f"{delta_str}  {ltp_str}  {entry_str}"
            )
        else:
            label = role_labels[role]
            pos_lines.append(
                f"  {label} {strike_suffix}  {ltp_str}"
            )

    position_block = "\n".join(pos_lines)

    # Combined mark / entry credit
    combined_mark, entry_credit = ic._compute_combined_pnl(chain, ic_positions)
    if combined_mark is not None and entry_credit > Decimal("0"):
        captured_pct = (entry_credit - combined_mark) / entry_credit
        pct_val = int(round(captured_pct * 100))
        pnl_line = (
            f"P&L: combined mark ₹{combined_mark:.2f} vs "
            f"entry credit ₹{entry_credit:.2f} → {pct_val}% captured so far"
        )
    else:
        pnl_line = (
            f"P&L: combined mark N/A vs "
            f"entry credit ₹{entry_credit:.2f} → N/A% captured so far"
        )

    # ROI on margin — divides total ₹ P&L by the final_margin captured once at
    # entry (see MarginSnapshot docstring). entry_date is shared across every
    # leg of one entry cycle, so any position's value works as the lookup key.
    # Absent for cycles opened before this feature existed, or where the
    # margin-calculator call failed non-fatally at entry time.
    entry_date = ic_positions[0].entry_date
    roi_line = "ROI on margin: N/A (no margin snapshot for this entry)"
    if entry_date is not None:
        margin_snapshot = store.get_margin_snapshot(config.strategy_name, entry_date)
        if margin_snapshot is not None and margin_snapshot.final_margin > Decimal("0"):
            if combined_mark is not None:
                total_pnl_rupees = (entry_credit - combined_mark) * LOT_SIZE
                roi_pct = (total_pnl_rupees / margin_snapshot.final_margin) * Decimal("100")
                roi_line = (
                    f"ROI on margin: ₹{total_pnl_rupees:,.0f} / "
                    f"₹{margin_snapshot.final_margin:,.0f} margin → {roi_pct:.1f}%"
                )
            else:
                roi_line = (
                    f"ROI on margin: N/A (no live mark) — "
                    f"margin blocked ₹{margin_snapshot.final_margin:,.0f}"
                )

    # Signals
    sig_strs = []
    for ev in events:
        emoji = "ℹ️"
        if ev.severity == "ACTION":
            emoji = "🔴"
        elif ev.severity in ["WARN", "WARNING"]:
            emoji = "⚠️"
        sig_strs.append(f"{ev.event_type} {emoji}")

    # Add DTE_WARN if DTE <= config.dte_warn and not already in sigs
    dte_warn_threshold = getattr(config, "dte_warn", -1)
    has_dte_warn = any(s.startswith("DTE_WARN") for s in sig_strs)
    if dte <= dte_warn_threshold and not has_dte_warn:
        sig_strs.append("DTE_WARN ℹ️")

    sigs_str = ", ".join(sig_strs) if sig_strs else "none"

    # Intraday acted events
    acted_events = []
    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT exit_signal, notes, event_time, actual_rule_used
               FROM paper_exit_events
               WHERE strategy_name = ? AND status = 'ACTED'
               ORDER BY event_time ASC""",
            (config.strategy_name,),
        ).fetchall()
        for row in rows:
            if row["event_time"][:10] == snap_date.isoformat():
                acted_events.append(row)

    if acted_events:
        intraday_lines = []
        for row in acted_events:
            action_taken = get_action_taken(row)
            # Parse execution time from event_time
            time_str = "11:42"
            try:
                dt = datetime.fromisoformat(row["event_time"])
                time_str = dt.strftime("%H:%M")
            except (ValueError, TypeError):
                if (
                    isinstance(row.get("event_time"), str)
                    and len(row["event_time"]) >= 16
                ):
                    time_str = row["event_time"][11:16]
            intraday_lines.append(
                f"{row['exit_signal']} → {action_taken} "
                f"executed at {time_str}"
            )
        intraday_str = ", ".join(intraday_lines)
    else:
        intraday_str = "none"

    report = (
        f"📋 IC EOD Audit — {expiry_type} ({config.strategy_name})\n"
        f"DTE: {dte}  |  Nifty: {nifty_spot:,.0f}  |  IVR: {ivr_str}\n\n"
        f"Position:\n"
        f"{position_block}\n\n"
        f"{pnl_line}\n"
        f"{roi_line}\n\n"
        f"Today's signals: {sigs_str}\n"
        f"Intraday actions: {intraday_str}"
    )

    # Append unresolved ACTION signals if present in events
    unresolved = [e for e in events if e.severity == "ACTION"]
    if unresolved:
        unresolved_lines = []
        for e in unresolved:
            unresolved_lines.append(f"  {e.event_type} 🔴  {e.description}")
        sig_join = "\n".join(unresolved_lines)
        report += f"\n\n⚠️  Unresolved ACTION signals:\n{sig_join}"

    return report


async def _run(args: argparse.Namespace) -> None:
    setup_logging()
    snap_date: date = args.date or date.today()
    save: bool = not args.dry_run

    store = PaperStore(args.db_path)
    lookup = InstrumentLookup.from_file(args.bod_path)

    # Broker client setup
    try:
        broker = create_client(settings.upstox_env)
    except ValueError:
        if args.dry_run:
            logger.warning("ic_snapshot.broker_init_failed_mock_fallback")

            class _MockBroker:
                async def get_ltp(self, keys: list[str]) -> dict[str, Decimal]:
                    return {k: Decimal("0.0") for k in keys}

                async def get_option_chain(
                    self, underlying: str, expiry: str
                ) -> list[dict[str, Any]]:
                    return []

            broker = _MockBroker()
        else:
            logger.error("ic_snapshot.broker_init_failed")
            sys.exit(1)

    # Telegram notifier
    bot_token = settings.telegram_bot_token or ""
    chat_id = settings.telegram_chat_id or ""
    notifier = (
        TelegramGateway(
            bot_token=bot_token,
            chat_id=chat_id,
            db_path=str(args.db_path),
        )
        if (bot_token and chat_id)
        else None
    )

    reports: list[str] = []
    has_any_positions = False

    for expiry_type, config in CONFIGS.items():
        # Quick check for positions before processing
        positions = store.get_positions(config.strategy_name)
        active = [
            p for p in positions
            if p.strategy_name == config.strategy_name and p.net_qty != 0
        ]
        if active:
            has_any_positions = True

        try:
            report = await process_variant(
                expiry_type,
                config,
                store,
                broker,
                lookup,
                notifier,
                snap_date,
                save,
            )
            if report is not None:
                reports.append(report)
        except Exception as exc:  # Intentional: fail-safe variant run
            logger.error(
                "ic_snapshot.variant_failed",
                strategy=config.strategy_name,
                error=str(exc),
                variant_version="v1",
            )
            reports.append(
                f"📋 IC EOD Audit — {expiry_type} ({config.strategy_name})\n"
                f"Error: Snapshot generation failed due to "
                f"unexpected error."
            )

    for expiry_type, config in CONFIGS_V2.items():
        positions = store.get_positions(config.strategy_name)
        active = [p for p in positions if p.net_qty != 0]
        if active:
            has_any_positions = True
        try:
            report = await process_variant(
                expiry_type, config, store, broker, lookup,
                notifier, snap_date, save,
                strategy_cls=IronCondorV2,
            )
            if report is not None:
                reports.append(report)
        except Exception as exc:
            logger.error(
                "ic_snapshot.variant_failed",
                strategy=config.strategy_name,
                error=str(exc),
                variant_version="v2",
            )
            reports.append(f"📋 IC EOD Audit — {expiry_type} ({config.strategy_name})\nError: Snapshot failed.")

    if not has_any_positions:
        msg = "IC EOD: no open positions across all expiry types."
        print(msg)
        if notifier and save:
            logger.info(
                "ic_snapshot.report_sent",
                channel="telegram",
                report_count=0,
                snap_date=snap_date.isoformat(),
            )
            try:
                await notifier.send_notification(msg)
            except Exception as exc:  # Intentional: fail-safe delivery
                logger.warning(
                    "ic_snapshot.telegram_failed", error=str(exc)
                )
        return

    # Print reports and send to Telegram
    for idx, r in enumerate(reports):
        print(f"\n{r}\n")
        if notifier and save:
            logger.info(
                "ic_snapshot.report_sent",
                channel="telegram",
                report_index=idx,
                report_count=len(reports),
                snap_date=snap_date.isoformat(),
            )
            try:
                await notifier.send_notification(r)
            except Exception as exc:  # Intentional: fail-safe delivery
                logger.warning(
                    "ic_snapshot.telegram_failed", error=str(exc)
                )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "EOD audit cron for all scheduled Iron Condor variants."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--date",
        default=None,
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="Snapshot date (default: today).",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print report only — do not write/notify (default: on).",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite DB path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"BOD instruments JSON path (default: {DEFAULT_BOD_PATH})",
    )

    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
