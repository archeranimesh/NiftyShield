import argparse
from decimal import Decimal
from pathlib import Path

import pytest

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


def test_backfill_happy_path(tmp_path: Path, monkeypatch) -> None:
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

    from scripts.mvp import _backfill

    # Mock the backfill logic to just verify pick creation
    called_run_backfill = False

    def mock_run_backfill(store_arg, pick_id, eq_closes, idx_closes, end_date):
        nonlocal called_run_backfill
        called_run_backfill = True

    monkeypatch.setattr("src.mvp.backfill.run_backfill", mock_run_backfill)
    monkeypatch.setattr("scripts.mvp.fetch_historical_closes", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "src.mvp.backfill.fetch_historical_index_closes", lambda *args, **kwargs: {}
    )

    args = argparse.Namespace(
        symbol="UNIPARTS",
        reco_date="2023-01-01",
        provider="prov",
        category="cat",
        reco_price=100.0,
        target=150.0,
        sl=80.0,
        defer_key=True,
    )

    _backfill(store, args)

    assert called_run_backfill
    picks = store.list_picks()
    assert len(picks) == 1
    p = picks[0]
    assert p.symbol == "UNIPARTS"
    assert p.reco_price == Decimal("100.0")
    assert p.target_price == Decimal("150.0")
    assert p.stop_loss == Decimal("80.0")
    assert p.pick_date == "2023-01-01T00:00:00Z"


def test_backfill_missing_provider(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "test.db"
    store = MVPStore(db_path)
    store.init_db()

    from scripts.mvp import _backfill

    args = argparse.Namespace(
        symbol="UNIPARTS",
        reco_date="2023-01-01",
        provider="missing",
        category="cat",
        reco_price=None,
        target=None,
        sl=None,
        defer_key=True,
    )

    with pytest.raises(SystemExit):
        _backfill(store, args)

    captured = capsys.readouterr().out
    assert "Provider 'missing' not found" in captured
