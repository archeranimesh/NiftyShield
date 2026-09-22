from decimal import Decimal

from src.mvp.models import MVPSnapshot, MVPTranche, Pick, PickStatus, ProviderSource


def test_pick_all_fields_populated_defaults_to_pending():
    """Test 1: Pick with all fields populated -> status is PENDING by default."""
    pick = Pick(
        pick_id="p1",
        category_id="c1",
        symbol="RELIANCE",
        instrument_key="NSE_EQ|2885",
        analyst="TV Analyst",
        entry_price=Decimal("2500"),
        pick_date="2026-09-22",
        target_price=Decimal("3000"),
        stop_loss=Decimal("2000"),
        notes="Solid",
        closed_at=None,
        close_price=None,
        capital_allotted=Decimal("200000"),
        tranche_step_pct=Decimal("5"),
        max_drawdown_pct=Decimal("25"),
        deployed_capital=Decimal("50000"),
        total_qty=20,
        avg_cost=Decimal("2500"),
        idle_cash=Decimal("150000"),
        realized_pnl=Decimal("0"),
        benchmark_entry=Decimal("25000"),
        created_at="2026-09-22T10:00:00Z",
        updated_at="2026-09-22T10:00:00Z",
    )
    assert pick.status == PickStatus.PENDING


def test_pick_entry_price_none_defaults_to_pending():
    """Test 2: Pick with entry_price=None -> status defaults to PENDING."""
    pick = Pick(
        pick_id="p2",
        symbol="TCS",
        pick_date="2026-09-22",
        created_at="2026-09-22T10:00:00Z",
        updated_at="2026-09-22T10:00:00Z",
    )
    assert pick.entry_price is None
    assert pick.status == PickStatus.PENDING


def test_pick_defaults_capital_tranche_drawdown():
    """Test 3: Pick defaults: capital_allotted=100000, tranche_step_pct=6, max_drawdown_pct=30 when unset."""
    pick = Pick(
        pick_id="p3",
        symbol="INFY",
        pick_date="2026-09-22",
        created_at="2026-09-22T10:00:00Z",
        updated_at="2026-09-22T10:00:00Z",
    )
    assert pick.capital_allotted == Decimal("100000")
    assert pick.tranche_step_pct == Decimal("6")
    assert pick.max_drawdown_pct == Decimal("30")


def test_provider_source_enum_members():
    """Test 4: ProviderSource enum members match expected string values."""
    assert ProviderSource.TV.value == "TV"
    assert ProviderSource.TELEGRAM.value == "TELEGRAM"
    assert ProviderSource.YOUTUBE.value == "YOUTUBE"
    assert ProviderSource.OTHER.value == "OTHER"


def test_pick_entry_target_price_round_trips():
    """Test 5: Pick with entry_price=Decimal('1200'), target_price=None -> round-trips without error."""
    pick = Pick(
        pick_id="p5",
        symbol="HDFCBANK",
        entry_price=Decimal("1200"),
        pick_date="2026-09-22",
        target_price=None,
        created_at="2026-09-22T10:00:00Z",
        updated_at="2026-09-22T10:00:00Z",
    )
    assert pick.entry_price == Decimal("1200")
    assert pick.target_price is None


def test_mvp_tranche_pre_fill_valid():
    """Test 6: MVPTranche with tranche_index=0, fill_price=None, qty=None -> valid (pre-fill state)."""
    tranche = MVPTranche(
        tranche_id="t1",
        pick_id="p1",
        tranche_index=0,
        trigger_pct=Decimal("0"),
        fill_price=None,
        qty=None,
    )
    assert tranche.tranche_index == 0
    assert tranche.fill_price is None
    assert tranche.qty is None


def test_mvp_snapshot_pre_insert_valid():
    """Test 7: MVPSnapshot with snapshot_id=None -> valid (pre-insert state)."""
    snapshot = MVPSnapshot(
        snapshot_id=None,
        pick_id="p1",
        ltp=Decimal("150.50"),
        captured_at="2026-09-22T12:00:00Z",
    )
    assert snapshot.snapshot_id is None
    assert snapshot.ltp == Decimal("150.50")
