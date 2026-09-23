"""CLI for the Multi-bagger Value Picks Tracker.

Usage:
    python -m scripts.mvp provider add <slug> <display_name> --source <tv|telegram|youtube|other>
    python -m scripts.mvp provider list
    python -m scripts.mvp category add <provider_slug> <slug> <display_name>
    python -m scripts.mvp category list <provider_slug>
    python -m scripts.mvp add <symbol> [-p <provider_slug>] [-c <category_slug>] [--defer-key]
    python -m scripts.mvp update <pick_id> [--price N] [--target N] [--sl N] [--notes TEXT]
    python -m scripts.mvp close <pick_id> --price N
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from scripts.lookup.instrument_lookup import DEFAULT_BOD_PATH
from src.instruments.lookup import InstrumentLookup
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


def _resolve_instrument_key(symbol: str, defer_key: bool) -> str | None:
    if defer_key:
        return None
    if not DEFAULT_BOD_PATH.exists():
        print(f"⚠ BOD file not found at {DEFAULT_BOD_PATH}; skipping instrument resolution.")
        return None
    lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
    results = lookup.search_equity(symbol)
    if not results:
        print(f"⚠ No instrument match for '{symbol}'; skipping resolution.")
        return None
    if len(results) == 1:
        inst = results[0]
        key = inst["instrument_key"]
        print(f" → instrument_key: {key}")
        return key

    print("#  SYMBOL  NAME  KEY")
    for i, inst in enumerate(results, start=1):
        print(
            f"{i}  {inst.get('trading_symbol')}  {inst.get('name')}  {inst.get('instrument_key')}"
        )
    choice = input("Select [1-N / s=skip / q=quit]: ").strip().lower()
    if choice == "s":
        return None
    if choice == "q":
        print("Aborted.")
        sys.exit(0)
    try:
        idx = int(choice)
        if not 1 <= idx <= len(results):
            raise ValueError
    except ValueError:
        print("Invalid selection; skipping resolution.")
        return None
    key = results[idx - 1]["instrument_key"]
    print(f" → instrument_key: {key}")
    return key


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
    instrument_key = _resolve_instrument_key(args.symbol, args.defer_key)
    now = _now()
    pick = Pick(
        pick_id=str(uuid.uuid4()),
        category_id=category_id,
        symbol=args.symbol,
        instrument_key=instrument_key,
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
    add_parser.add_argument("--defer-key", action="store_true", default=False)
    add_parser.set_defaults(func=_add)

    update_parser = subparsers.add_parser("update", help="Update a pick.")
    update_parser.add_argument("pick_id")
    update_parser.add_argument("--price", type=float, default=None)
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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    store = MVPStore(DB_PATH)
    store.init_db()
    args.func(store, args)


if __name__ == "__main__":
    main()
