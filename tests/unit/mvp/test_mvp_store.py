"""Tests for MVPStore init_db and provider/category persistence."""

from pathlib import Path

from src.mvp.models import Category, Provider, ProviderSource
from src.mvp.store import MVPStore


def _make_provider(provider_id: str = "prov-1", slug: str = "dsij") -> Provider:
    return Provider(
        provider_id=provider_id,
        slug=slug,
        display_name="DSIJ",
        source_type=ProviderSource.TV,
        notes=None,
        created_at="2026-09-22T00:00:00Z",
    )


def _make_category(
    category_id: str = "cat-1",
    provider_id: str = "prov-1",
    slug: str = "value-picks",
) -> Category:
    return Category(
        category_id=category_id,
        provider_id=provider_id,
        slug=slug,
        display_name="Value Picks",
        notes=None,
        created_at="2026-09-22T00:00:00Z",
    )


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.init_db()


def test_add_provider_get_provider_round_trip(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    provider = _make_provider()
    store.add_provider(provider)

    fetched = store.get_provider("dsij")

    assert fetched is not None
    assert fetched.slug == provider.slug
    assert fetched.display_name == provider.display_name


def test_get_provider_missing_slug_returns_none(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()

    assert store.get_provider("nonexistent") is None


def test_list_providers_returns_all_sorted_by_display_name(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider(provider_id="prov-1", slug="dsij"))
    store.add_provider(
        Provider(
            provider_id="prov-2",
            slug="prudentequity",
            display_name="Prudent Equity",
            source_type=ProviderSource.TELEGRAM,
            notes=None,
            created_at="2026-09-22T00:00:00Z",
        )
    )

    providers = store.list_providers()

    assert [p.display_name for p in providers] == ["DSIJ", "Prudent Equity"]


def test_add_category_get_category_round_trip(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    category = _make_category()
    store.add_category(category)

    fetched = store.get_category("prov-1", "value-picks")

    assert fetched is not None
    assert fetched.category_id == category.category_id
    assert fetched.display_name == category.display_name


def test_add_category_duplicate_is_ignored(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    store.add_category(_make_category())
    store.add_category(_make_category())

    categories = store.list_categories("prov-1")
    assert len(categories) == 1


def test_list_categories_filters_by_provider(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider(provider_id="prov-1", slug="dsij"))
    store.add_provider(
        Provider(
            provider_id="prov-2",
            slug="prudentequity",
            display_name="Prudent Equity",
            source_type=ProviderSource.TELEGRAM,
            notes=None,
            created_at="2026-09-22T00:00:00Z",
        )
    )
    store.add_category(
        _make_category(category_id="cat-1", provider_id="prov-1", slug="value-picks")
    )
    store.add_category(
        _make_category(category_id="cat-2", provider_id="prov-2", slug="multibagger")
    )

    prov1_categories = store.list_categories("prov-1")
    prov2_categories = store.list_categories("prov-2")

    assert len(prov1_categories) == 1
    assert prov1_categories[0].provider_id == "prov-1"
    assert len(prov2_categories) == 1
    assert prov2_categories[0].provider_id == "prov-2"
