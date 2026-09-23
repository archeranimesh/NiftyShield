import argparse
from decimal import Decimal
from pathlib import Path

from scripts.mvp import _list, _summary_by_symbol, _summary_grouped
from src.mvp.models import Category, Pick, Provider, ProviderSource
from src.mvp.store import MVPStore


def test_deviation_display_list(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "test.db"
    store = MVPStore(db_path)
    store.init_db()

    provider = Provider(
        provider_id="prov_1",
        slug="prov",
        display_name="Prov",
        source_type=ProviderSource.OTHER,
        created_at="2024-01-01",
    )
    store.add_provider(provider)
    category = Category(
        category_id="cat_1",
        provider_id="prov_1",
        slug="cat",
        display_name="Cat",
        created_at="2024-01-01",
    )
    store.add_category(category)

    # Happy path: +10% deviation (entry=110, reco=100)
    store.add_pick(
        Pick(
            pick_id="pick_happy",
            category_id="cat_1",
            symbol="HAPP",
            entry_price=Decimal("110.0"),
            reco_price=Decimal("100.0"),
            pick_date="2024-01-01",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
    )
    # Edge cases: no reco, no entry, reco=0
    store.add_pick(
        Pick(
            pick_id="pick_no_reco",
            category_id="cat_1",
            symbol="NORE",
            entry_price=Decimal("100.0"),
            reco_price=None,
            pick_date="2024-01-01",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
    )
    store.add_pick(
        Pick(
            pick_id="pick_no_entry",
            category_id="cat_1",
            symbol="NOEN",
            entry_price=None,
            reco_price=Decimal("100.0"),
            pick_date="2024-01-01",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
    )
    store.add_pick(
        Pick(
            pick_id="pick_zero_reco",
            category_id="cat_1",
            symbol="ZERO",
            entry_price=Decimal("100.0"),
            reco_price=Decimal("0.0"),
            pick_date="2024-01-01",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
    )

    args = argparse.Namespace(all=True, open=False, provider=None, category=None)
    _list(store, args)

    captured = capsys.readouterr().out
    lines = captured.strip().split("\n")
    assert any("HAPP" in line and "+10.00%" in line for line in lines)

    # Assert edge cases have "-" for dev
    for symbol in ["NORE", "NOEN", "ZERO"]:
        line = next(ln for ln in lines if symbol in ln)
        cols = line.split(" | ")
        assert cols[5].strip() == "-"  # DEV% is the 6th column


def test_deviation_display_summary_by_symbol(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "test.db"
    store = MVPStore(db_path)
    store.init_db()

    provider = Provider(
        provider_id="prov_1",
        slug="prov",
        display_name="Prov",
        source_type=ProviderSource.OTHER,
        created_at="2024-01-01",
    )
    store.add_provider(provider)
    category = Category(
        category_id="cat_1",
        provider_id="prov_1",
        slug="cat",
        display_name="Cat",
        created_at="2024-01-01",
    )
    store.add_category(category)

    # Happy path: -5% deviation (entry=95, reco=100)
    store.add_pick(
        Pick(
            pick_id="pick_happy",
            category_id="cat_1",
            symbol="HAPP",
            entry_price=Decimal("95.0"),
            reco_price=Decimal("100.0"),
            pick_date="2024-01-01",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
    )

    # Edge case: zero reco
    store.add_pick(
        Pick(
            pick_id="pick_zero",
            category_id="cat_1",
            symbol="HAPP",
            entry_price=Decimal("100.0"),
            reco_price=Decimal("0.0"),
            pick_date="2024-01-01",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
    )

    _summary_by_symbol(store, "HAPP")

    captured = capsys.readouterr().out
    lines = captured.strip().split("\n")
    assert any("-5.00%" in line for line in lines)

    # Second pick should have "-" for dev
    # Find the line with 0 for reco
    zero_line = next(ln for ln in lines[1:] if ln.split(" | ")[2].strip() == "0.0")
    assert zero_line.split(" | ")[4].strip() == "-"


def test_deviation_display_summary_grouped(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "test.db"
    store = MVPStore(db_path)
    store.init_db()

    provider = Provider(
        provider_id="prov_1",
        slug="prov",
        display_name="Prov",
        source_type=ProviderSource.OTHER,
        created_at="2024-01-01",
    )
    store.add_provider(provider)
    category = Category(
        category_id="cat_1",
        provider_id="prov_1",
        slug="cat",
        display_name="Cat",
        created_at="2024-01-01",
    )
    store.add_category(category)

    # Happy path 1: +10%
    store.add_pick(
        Pick(
            pick_id="pick_1",
            category_id="cat_1",
            symbol="HAPP1",
            entry_price=Decimal("110.0"),
            reco_price=Decimal("100.0"),
            pick_date="2024-01-01",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
    )
    # Happy path 2: +20%
    store.add_pick(
        Pick(
            pick_id="pick_2",
            category_id="cat_1",
            symbol="HAPP2",
            entry_price=Decimal("120.0"),
            reco_price=Decimal("100.0"),
            pick_date="2024-01-01",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
    )
    # Edge case: no reco (should be ignored in avg)
    store.add_pick(
        Pick(
            pick_id="pick_3",
            category_id="cat_1",
            symbol="NORE",
            entry_price=Decimal("100.0"),
            reco_price=None,
            pick_date="2024-01-01",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
    )
    # Edge case: zero reco (should be ignored in avg)
    store.add_pick(
        Pick(
            pick_id="pick_4",
            category_id="cat_1",
            symbol="ZERO",
            entry_price=Decimal("100.0"),
            reco_price=Decimal("0.0"),
            pick_date="2024-01-01",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
    )

    args = argparse.Namespace(provider=None, category=None)
    _summary_grouped(store, args)

    captured = capsys.readouterr().out
    lines = captured.strip().split("\n")
    # Avg of 10% and 20% is 15%
    assert any("Prov/Cat" in line and "+15.00%" in line for line in lines)
