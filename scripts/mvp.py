"""CLI for the Multi-bagger Value Picks Tracker.

Usage:
    python -m scripts.mvp provider add <slug> <display_name> --source <tv|telegram|youtube|other>
    python -m scripts.mvp provider list
    python -m scripts.mvp category add <provider_slug> <slug> <display_name>
    python -m scripts.mvp category list <provider_slug>
    python -m scripts.mvp add <symbol> [-p <provider_slug>] [-c <category_slug>] [--defer-key]
    python -m scripts.mvp update <pick_id> [--price N] [--target N] [--sl N] [--notes TEXT]
    python -m scripts.mvp close <pick_id> --price N
    python -m scripts.mvp backfill <symbol> --reco-date YYYY-MM-DD [--reco-price N] [--target N] [--sl N] [-p <provider_slug>] [-c <category_slug>] [--defer-key]
    python -m scripts.mvp backfill --resume <pick_id>
    python -m scripts.mvp list [--open] [--all] [-p <provider_slug>] [-c <category_slug>]
    python -m scripts.mvp summary [-p <provider_slug>] [-c <category_slug>]
    python -m scripts.mvp summary <SYMBOL>
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from scripts.lookup.instrument_lookup import DEFAULT_BOD_PATH
from src.instruments.lookup import InstrumentLookup
from src.mvp.backfill import fetch_historical_closes
from src.mvp.models import Category, Pick, PickStatus, Provider, ProviderSource
from src.mvp.store import MVPStore

DB_PATH = Path("data/portfolio/portfolio.sqlite")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provider_add(store: MVPStore, args: argparse.Namespace) -> None:
    provider = Provider(
        provider_id=str(uuid.uuid4()),
        slug=args.slug,
        display_name=args.display_name,
        source_type=ProviderSource(args.source.upper()),
        created_at=_now(),
    )
    store.add_provider(provider)
    print(f"✓ Provider '{args.slug}' added.")


def _provider_list(store: MVPStore, args: argparse.Namespace) -> None:
    providers = store.list_providers()
    if not providers:
        print("No providers.")
        return
    print("SLUG | DISPLAY_NAME | SOURCE")
    for p in providers:
        print(f"{p.slug} | {p.display_name} | {p.source_type.value}")


def _category_add(store: MVPStore, args: argparse.Namespace) -> None:
    provider = store.get_provider(args.provider_slug)
    if provider is None:
        print(f"✗ Provider '{args.provider_slug}' not found.")
        sys.exit(1)
    category = Category(
        category_id=str(uuid.uuid4()),
        provider_id=provider.provider_id,
        slug=args.slug,
        display_name=args.display_name,
        created_at=_now(),
    )
    store.add_category(category)
    print(f"✓ Category '{args.slug}' added.")


def _category_list(store: MVPStore, args: argparse.Namespace) -> None:
    provider = store.get_provider(args.provider_slug)
    if provider is None:
        print(f"✗ Provider '{args.provider_slug}' not found.")
        sys.exit(1)
    categories = store.list_categories(provider.provider_id)
    if not categories:
        print("No categories.")
        return
    print("SLUG | DISPLAY_NAME")
    for c in categories:
        print(f"{c.slug} | {c.display_name}")


def _resolve_instrument_key(symbol: str, defer_key: bool) -> tuple[str | None, str | None]:
    """Resolve instrument_key and canonical trading_symbol from BOD lookup.

    Returns (None, None) when deferred, BOD file missing, or no match.
    """
    if defer_key:
        return None, None
    if not DEFAULT_BOD_PATH.exists():
        print(f"⚠ BOD file not found at {DEFAULT_BOD_PATH}; skipping instrument resolution.")
        return None, None
    lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
    results = lookup.search_equity(symbol)
    if not results:
        print(f"⚠ No instrument match for '{symbol}'; skipping resolution.")
        return None, None
    if len(results) == 1:
        inst = results[0]
        key = inst["instrument_key"]
        trading_symbol = inst.get("trading_symbol")
        print(f" → instrument_key: {key}")
        return key, trading_symbol

    print("#  SYMBOL  NAME  KEY")
    for i, inst in enumerate(results, start=1):
        print(
            f"{i}  {inst.get('trading_symbol')}  {inst.get('name')}  {inst.get('instrument_key')}"
        )
    choice = input("Select [1-N / s=skip / q=quit]: ").strip().lower()
    if choice == "s":
        return None, None
    if choice == "q":
        print("Aborted.")
        sys.exit(0)
    try:
        idx = int(choice)
        if not 1 <= idx <= len(results):
            raise ValueError
    except ValueError:
        print("Invalid selection; skipping resolution.")
        return None, None
    chosen = results[idx - 1]
    key = chosen["instrument_key"]
    trading_symbol = chosen.get("trading_symbol")
    print(f" → instrument_key: {key}")
    return key, trading_symbol


def _resolve_category_id(
    store: MVPStore, provider_slug: str | None, category_slug: str | None
) -> str | None:
    if provider_slug is None and category_slug is None:
        return None
    if provider_slug is None or category_slug is None:
        print("✗ Both --provider and --category must be given together.")
        sys.exit(1)
    provider = store.get_provider(provider_slug)
    if provider is None:
        print(f"✗ Provider '{provider_slug}' not found.")
        sys.exit(1)
    category = store.get_category(provider.provider_id, category_slug)
    if category is None:
        print(f"✗ Category '{category_slug}' not found.")
        sys.exit(1)
    return category.category_id


def _add(store: MVPStore, args: argparse.Namespace) -> None:
    category_id = _resolve_category_id(store, args.provider, args.category)
    instrument_key, trading_symbol = _resolve_instrument_key(args.symbol, args.defer_key)
    now = _now()
    pick = Pick(
        pick_id=str(uuid.uuid4()),
        category_id=category_id,
        symbol=trading_symbol or args.symbol,
        instrument_key=instrument_key,
        reco_price=Decimal(str(args.reco_price)) if args.reco_price is not None else None,
        pick_date=now,
        created_at=now,
        updated_at=now,
    )
    store.add_pick(pick)
    print(f"✓ Pick added: {pick.pick_id[:8]} — {pick.symbol} (PENDING)")


def _update(store: MVPStore, args: argparse.Namespace) -> None:
    category_id = _resolve_category_id(store, args.provider, args.category)
    fields: dict[str, object] = {}
    if args.price is not None:
        fields["entry_price"] = Decimal(str(args.price))
    if args.reco_price is not None:
        fields["reco_price"] = Decimal(str(args.reco_price))
    if args.target is not None:
        fields["target_price"] = Decimal(str(args.target))
    if args.sl is not None:
        fields["stop_loss"] = Decimal(str(args.sl))
    if args.notes is not None:
        fields["notes"] = args.notes
    if category_id is not None:
        fields["category_id"] = category_id
    if not fields:
        print("Nothing to update.")
        return
    store.update_pick(args.pick_id, **fields)
    print("✓ Updated.")


def _close(store: MVPStore, args: argparse.Namespace) -> None:
    store.close_pick(args.pick_id, Decimal(str(args.price)), PickStatus.MANUAL_CLOSE)
    print(f"✓ Closed at {args.price}.")


def _backfill(store: MVPStore, args: argparse.Namespace) -> None:
    from src.mvp.backfill import fetch_historical_index_closes, run_backfill

    resume_id = getattr(args, "resume", None)
    if resume_id is not None:
        pick = store.get_pick(resume_id)
        if pick is None:
            print(f"No pick found for id {resume_id}.")
            return
        if pick.status != PickStatus.PENDING:
            print(f"Pick {resume_id[:8]} is not PENDING (status: {pick.status.value}).")
            return

        from_date = date.fromisoformat(pick.pick_date[:10])
        to_date = date.today()

        closes_list = fetch_historical_closes(pick.symbol, from_date, to_date)
        equity_closes = dict(closes_list)
        index_closes = fetch_historical_index_closes(from_date, to_date)

        run_backfill(store, pick.pick_id, equity_closes, index_closes, end_date=to_date)

        updated_pick = store.get_pick(pick.pick_id)
        if updated_pick:
            print(f"Backfill resumed. Final status: {updated_pick.status.value}")
            if updated_pick.entry_price:
                print(f"  Entry Price: {updated_pick.entry_price}")
            if updated_pick.close_price:
                print(f"  Close Price: {updated_pick.close_price}")
        else:
            print("Pick not found after backfill.")
        return

    if args.symbol is None or args.reco_date is None:
        print("symbol and --reco-date are required unless --resume is given.")
        return

    category_id = _resolve_category_id(store, args.provider, args.category)
    instrument_key, trading_symbol = _resolve_instrument_key(args.symbol, args.defer_key)

    pick_date_str = args.reco_date + "T00:00:00Z"
    pick = Pick(
        pick_id=str(uuid.uuid4()),
        category_id=category_id,
        symbol=trading_symbol or args.symbol,
        instrument_key=instrument_key,
        reco_price=Decimal(str(args.reco_price)) if args.reco_price is not None else None,
        pick_date=pick_date_str,
        target_price=Decimal(str(args.target)) if args.target is not None else None,
        stop_loss=Decimal(str(args.sl)) if args.sl is not None else None,
        created_at=_now(),
        updated_at=_now(),
        status=PickStatus.PENDING,
    )
    store.add_pick(pick)
    print(
        f"✓ Pick added for backfill: {pick.pick_id[:8]} — {pick.symbol} (PENDING) on {args.reco_date}"
    )

    from_date = date.fromisoformat(args.reco_date)
    to_date = date.today()

    closes_list = fetch_historical_closes(pick.symbol, from_date, to_date)
    equity_closes = dict(closes_list)
    index_closes = fetch_historical_index_closes(from_date, to_date)

    run_backfill(store, pick.pick_id, equity_closes, index_closes, end_date=to_date)

    updated_pick = store.get_pick(pick.pick_id)
    if updated_pick:
        print(f"Backfill complete. Final status: {updated_pick.status.value}")
        if updated_pick.entry_price:
            print(f"  Entry Price: {updated_pick.entry_price}")
        if updated_pick.close_price:
            print(f"  Close Price: {updated_pick.close_price}")
    else:
        print("Pick not found after backfill.")


def _pnl_and_return(pick: Pick, ltp_map: dict[str, Decimal] | None = None) -> tuple[str, str]:
    """Compute display strings for P&L and return% on a pick.

    Realized P&L/return use ``pick.realized_pnl`` for a closed pick.
    Unrealized return for an OPEN pick needs ``ltp_map`` (instrument_key ->
    ltp); without a matching entry it is shown as ``-``.
    """
    ltp_map = ltp_map or {}
    if pick.status != PickStatus.OPEN and pick.status != PickStatus.PENDING:
        if pick.deployed_capital == 0:
            return str(pick.realized_pnl), "-"
        return_pct = pick.realized_pnl / pick.deployed_capital * 100
        return str(pick.realized_pnl), f"{return_pct:+.2f}%"
    ltp = ltp_map.get(pick.instrument_key) if pick.instrument_key else None
    if ltp is None or pick.avg_cost is None or pick.deployed_capital == 0:
        return "-", "-"
    unrealized_pnl = (ltp - pick.avg_cost) * pick.total_qty
    return_pct = unrealized_pnl / pick.deployed_capital * 100
    return str(unrealized_pnl), f"{return_pct:+.2f}%"


def _build_category_map(store: MVPStore) -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    for provider in store.list_providers():
        for category in store.list_categories(provider.provider_id):
            mapping[category.category_id] = (provider.display_name, category.display_name)
    return mapping


def _resolve_filter_ids(
    store: MVPStore, provider_slug: str | None, category_slug: str | None
) -> tuple[str | None, str | None]:
    provider_id: str | None = None
    category_id: str | None = None
    if provider_slug is not None:
        provider = store.get_provider(provider_slug)
        if provider is None:
            print(f"✗ Provider '{provider_slug}' not found.")
            sys.exit(1)
        provider_id = provider.provider_id
    if category_slug is not None:
        if provider_id is None:
            print("✗ --category requires --provider.")
            sys.exit(1)
        category = store.get_category(provider_id, category_slug)
        if category is None:
            print(f"✗ Category '{category_slug}' not found.")
            sys.exit(1)
        category_id = category.category_id
    return provider_id, category_id


def _list(store: MVPStore, args: argparse.Namespace) -> None:
    if args.all:
        status = None
    elif args.open:
        status = PickStatus.OPEN
    else:
        status = PickStatus.PENDING
    provider_id, category_id = _resolve_filter_ids(store, args.provider, args.category)
    picks = store.list_picks(status=status, provider_id=provider_id, category_id=category_id)
    if not picks:
        print("No picks.")
        return
    category_map = _build_category_map(store)
    print(
        "ID | SYMBOL | STATUS | RECO | ENTRY | DEV% | TARGET | SL | DEPLOYED | "
        "AVG_COST | P&L | RETURN% | PROVIDER/CATEGORY | DATE"
    )
    for pick in picks:
        prov_disp, cat_disp = category_map.get(pick.category_id, ("-", "-"))
        dev_str = "-"
        if pick.entry_price is not None and pick.reco_price is not None and pick.reco_price != 0:
            dev_pct = (pick.entry_price - pick.reco_price) / pick.reco_price * 100
            dev_str = f"{dev_pct:+.2f}%"
        pnl_str, return_str = _pnl_and_return(pick)
        print(
            f"{pick.pick_id[:8]} | {pick.symbol} | {pick.status.value} | "
            f"{pick.reco_price if pick.reco_price is not None else '-'} | "
            f"{pick.entry_price if pick.entry_price is not None else '-'} | "
            f"{dev_str} | "
            f"{pick.target_price if pick.target_price is not None else '-'} | "
            f"{pick.stop_loss if pick.stop_loss is not None else '-'} | "
            f"{pick.deployed_capital} | "
            f"{pick.avg_cost if pick.avg_cost is not None else '-'} | "
            f"{pnl_str} | {return_str} | "
            f"{prov_disp}/{cat_disp} | {pick.pick_date}"
        )


def _summary_by_symbol(store: MVPStore, symbol: str) -> None:
    picks = [p for p in store.list_picks() if p.symbol.upper() == symbol.upper()]
    if not picks:
        print("No picks.")
        return
    category_map = _build_category_map(store)
    print(
        "PROVIDER | CATEGORY | RECO | ENTRY | DEV% | STATUS | CLOSE_PRICE | "
        "DEPLOYED | AVG_COST | P&L | RETURN% | DATE"
    )
    for pick in picks:
        prov_disp, cat_disp = category_map.get(pick.category_id, ("-", "-"))
        dev_str = "-"
        if pick.entry_price is not None and pick.reco_price is not None and pick.reco_price != 0:
            dev_pct = (pick.entry_price - pick.reco_price) / pick.reco_price * 100
            dev_str = f"{dev_pct:+.2f}%"
        pnl_str, return_str = _pnl_and_return(pick)
        print(
            f"{prov_disp} | {cat_disp} | "
            f"{pick.reco_price if pick.reco_price is not None else '-'} | "
            f"{pick.entry_price if pick.entry_price is not None else '-'} | "
            f"{dev_str} | "
            f"{pick.status.value} | "
            f"{pick.close_price if pick.close_price is not None else '-'} | "
            f"{pick.deployed_capital} | "
            f"{pick.avg_cost if pick.avg_cost is not None else '-'} | "
            f"{pnl_str} | {return_str} | {pick.pick_date}"
        )


def _summary_grouped(store: MVPStore, args: argparse.Namespace) -> None:
    provider_id, category_id = _resolve_filter_ids(store, args.provider, args.category)
    picks = store.list_picks(provider_id=provider_id, category_id=category_id)
    if not picks:
        print("No picks.")
        return
    category_map = _build_category_map(store)
    groups: dict[tuple[str, str], list[Pick]] = {}
    for pick in picks:
        key = category_map.get(pick.category_id, ("-", "-"))
        groups.setdefault(key, []).append(pick)

    print(
        "PROVIDER/CATEGORY | OPEN | TARGET_HIT | SL_HIT | WIN_RATE | CLOSED | "
        "AVG_DEV% | REALIZED_PNL"
    )
    for (prov_disp, cat_disp), group_picks in sorted(groups.items()):
        open_count = sum(1 for p in group_picks if p.status == PickStatus.OPEN)
        target_hit = sum(1 for p in group_picks if p.status == PickStatus.TARGET_HIT)
        sl_hit = sum(1 for p in group_picks if p.status == PickStatus.SL_HIT)
        manual_close = sum(1 for p in group_picks if p.status == PickStatus.MANUAL_CLOSE)
        closed = target_hit + sl_hit + manual_close
        win_denom = target_hit + sl_hit
        win_rate = f"{(target_hit / win_denom * 100):.1f}%" if win_denom else "-"

        devs = [
            (p.entry_price - p.reco_price) / p.reco_price * 100
            for p in group_picks
            if p.entry_price is not None and p.reco_price is not None and p.reco_price != 0
        ]
        avg_dev = f"{(sum(devs) / len(devs)):+.2f}%" if devs else "-"
        realized_pnl = sum((p.realized_pnl for p in group_picks), Decimal("0"))

        print(
            f"{prov_disp}/{cat_disp} | {open_count} | {target_hit} | {sl_hit} | "
            f"{win_rate} | {closed} | {avg_dev} | {realized_pnl}"
        )


def _summary(store: MVPStore, args: argparse.Namespace) -> None:
    if args.symbol is not None:
        _summary_by_symbol(store, args.symbol)
    else:
        _summary_grouped(store, args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mvp")
    subparsers = parser.add_subparsers(dest="command", required=True)

    provider_parser = subparsers.add_parser("provider", help="Manage providers.")
    provider_sub = provider_parser.add_subparsers(dest="provider_command", required=True)

    provider_add = provider_sub.add_parser("add", help="Add a provider.")
    provider_add.add_argument("slug")
    provider_add.add_argument("display_name")
    provider_add.add_argument(
        "--source",
        required=True,
        choices=["tv", "telegram", "youtube", "other"],
    )
    provider_add.set_defaults(func=_provider_add)

    provider_list = provider_sub.add_parser("list", help="List providers.")
    provider_list.set_defaults(func=_provider_list)

    category_parser = subparsers.add_parser("category", help="Manage categories.")
    category_sub = category_parser.add_subparsers(dest="category_command", required=True)

    category_add = category_sub.add_parser("add", help="Add a category.")
    category_add.add_argument("provider_slug")
    category_add.add_argument("slug")
    category_add.add_argument("display_name")
    category_add.set_defaults(func=_category_add)

    category_list = category_sub.add_parser("list", help="List categories.")
    category_list.add_argument("provider_slug")
    category_list.set_defaults(func=_category_list)

    add_parser = subparsers.add_parser("add", help="Add a pick.")
    add_parser.add_argument("symbol")
    add_parser.add_argument("-p", "--provider", dest="provider", default=None)
    add_parser.add_argument("-c", "--category", dest="category", default=None)
    add_parser.add_argument("--reco-price", type=float, default=None)
    add_parser.add_argument("--defer-key", action="store_true", default=False)
    add_parser.set_defaults(func=_add)

    update_parser = subparsers.add_parser("update", help="Update a pick.")
    update_parser.add_argument("pick_id")
    update_parser.add_argument("--price", type=float, default=None)
    update_parser.add_argument("--reco-price", type=float, default=None)
    update_parser.add_argument("--target", type=float, default=None)
    update_parser.add_argument("--sl", type=float, default=None)
    update_parser.add_argument("-p", "--provider", dest="provider", default=None)
    update_parser.add_argument("-c", "--category", dest="category", default=None)
    update_parser.add_argument("--notes", default=None)
    update_parser.set_defaults(func=_update)

    close_parser = subparsers.add_parser("close", help="Close a pick.")
    close_parser.add_argument("pick_id")
    close_parser.add_argument("--price", type=float, required=True)
    close_parser.set_defaults(func=_close)

    backfill_parser = subparsers.add_parser(
        "backfill", help="Add a past pick and backfill its snapshot history."
    )
    backfill_parser.add_argument("symbol", nargs="?", default=None)
    backfill_parser.add_argument("--reco-date", default=None, help="YYYY-MM-DD")
    backfill_parser.add_argument(
        "--resume", dest="resume", default=None, help="Resume an existing PENDING pick_id."
    )
    backfill_parser.add_argument("-p", "--provider", dest="provider", default=None)
    backfill_parser.add_argument("-c", "--category", dest="category", default=None)
    backfill_parser.add_argument("--reco-price", type=float, default=None)
    backfill_parser.add_argument("--target", type=float, default=None)
    backfill_parser.add_argument("--sl", type=float, default=None)
    backfill_parser.add_argument("--defer-key", action="store_true", default=False)
    backfill_parser.set_defaults(func=_backfill)

    list_parser = subparsers.add_parser("list", help="List picks.")
    list_parser.add_argument("--open", action="store_true", default=False)
    list_parser.add_argument("--all", action="store_true", default=False)
    list_parser.add_argument("-p", "--provider", dest="provider", default=None)
    list_parser.add_argument("-c", "--category", dest="category", default=None)
    list_parser.set_defaults(func=_list)

    summary_parser = subparsers.add_parser("summary", help="Summarize picks.")
    summary_parser.add_argument("symbol", nargs="?", default=None)
    summary_parser.add_argument("-p", "--provider", dest="provider", default=None)
    summary_parser.add_argument("-c", "--category", dest="category", default=None)
    summary_parser.set_defaults(func=_summary)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    store = MVPStore(DB_PATH)
    store.init_db()
    args.func(store, args)


if __name__ == "__main__":
    main()
