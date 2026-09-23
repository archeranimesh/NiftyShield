"""CLI for the Multi-bagger Value Picks Tracker.

Usage:
    python -m scripts.mvp provider add <slug> <display_name> --source <tv|telegram|youtube|other>
    python -m scripts.mvp provider list
    python -m scripts.mvp category add <provider_slug> <slug> <display_name>
    python -m scripts.mvp category list <provider_slug>
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.mvp.models import Category, Provider, ProviderSource
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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    store = MVPStore(DB_PATH)
    store.init_db()
    args.func(store, args)


if __name__ == "__main__":
    main()
