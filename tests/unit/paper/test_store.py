"""Unit tests for src/paper/store.py.

All tests use a file-based SQLite DB under pytest's tmp_path — not :memory:
because PaperStore opens a new connection per call (same pattern as PortfolioStore).

Coverage:
- record_trade: inserts correctly; all fields round-trip cleanly.
- record_trade: idempotent — duplicate (strategy, leg, date, action) silently ignored.
- record_trade: multiple distinct trades for same strategy each stored.
- get_trades: returns all trades for a strategy ordered by trade_date ASC.
- get_trades: filtered by leg_role returns only matching rows.
- get_trades: returns empty list for unknown strategy.
- get_position: BUY-only net quantity and avg_cost.
- get_position: SELL-only net qty (short opened via SELL).
- get_position: mixed BUY + SELL net quantity.
- get_position: weighted average cost excludes SELL prices.
- get_position: returns zero position for unknown strategy/leg.
- record_nav_snapshot: inserts row; all fields round-trip cleanly.
- record_nav_snapshot: upsert on re-run — updates existing row.
- record_nav_snapshot: underlying_price stored and retrieved as Decimal.
- record_nav_snapshot: underlying_price None survives round-trip.
- get_nav_snapshots: returns multiple snapshots ordered by date ASC.
- get_nav_snapshots: returns empty list for unknown strategy.
- get_latest_nav_snapshot: returns most recent snapshot.
- get_latest_nav_snapshot: returns None when no snapshots exist.
- get_strategy_names: returns distinct sorted strategy names.
- Schema coexistence: paper tables created alongside existing portfolio tables.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.instruments.lookup import InstrumentLookup
from src.models.portfolio import TradeAction
from src.paper.constants import NIFTYBEES_KEY
from src.paper.models import PaperLegSnapshot, PaperNavSnapshot, PaperTrade, TradeState
from src.paper.store import PaperStore

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_paper.db"


@pytest.fixture
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


# ── Helpers ───────────────────────────────────────────────────────────────────

_STRATEGY = "paper_csp_nifty_v1"
_LEG = "short_put"
_KEY = "NSE_FO|12345"
_DATE = date(2026, 5, 1)


def _sell_trade(**overrides) -> PaperTrade:
    defaults = dict(
        strategy_name=_STRATEGY,
        leg_role=_LEG,
        instrument_key=_KEY,
        trade_date=_DATE,
        action=TradeAction.SELL,
        quantity=75,
        price=Decimal("120.50"),
        notes="entry",
    )
    defaults.update(overrides)
    return PaperTrade(**defaults)


def _buy_trade(**overrides) -> PaperTrade:
    defaults = dict(
        strategy_name=_STRATEGY,
        leg_role=_LEG,
        instrument_key=_KEY,
        trade_date=_DATE,
        action=TradeAction.BUY,
        quantity=75,
        price=Decimal("60.00"),
        notes="exit at 50%",
    )
    defaults.update(overrides)
    return PaperTrade(**defaults)


# ── record_trade ──────────────────────────────────────────────────────────────


def test_record_trade_inserts_row(store: PaperStore) -> None:
    store.record_trade(_sell_trade())
    trades = store.get_trades(_STRATEGY)
    assert len(trades) == 1


def test_record_trade_fields_round_trip(store: PaperStore) -> None:
    original = _sell_trade()
    store.record_trade(original)
    retrieved = store.get_trades(_STRATEGY)[0]
    assert retrieved.strategy_name == original.strategy_name
    assert retrieved.leg_role == original.leg_role
    assert retrieved.instrument_key == original.instrument_key
    assert retrieved.trade_date == original.trade_date
    assert retrieved.action == original.action
    assert retrieved.quantity == original.quantity
    assert retrieved.price == original.price
    assert retrieved.notes == original.notes


def test_record_trade_idempotent(store: PaperStore) -> None:
    t = _sell_trade()
    store.record_trade(t)
    store.record_trade(t)
    store.record_trade(t)
    assert len(store.get_trades(_STRATEGY)) == 1


def test_record_trade_different_legs_both_stored(store: PaperStore) -> None:
    store.record_trade(_sell_trade(leg_role="short_put"))
    store.record_trade(_sell_trade(leg_role="short_call", instrument_key="NSE_FO|99999"))
    assert len(store.get_trades(_STRATEGY)) == 2


def test_record_trade_same_instrument_idempotent(store: PaperStore) -> None:
    """BUG-4: identical (strategy, leg, instrument_key, date, action) is a no-op."""
    t = _sell_trade()
    assert store.record_trade(t) is True
    assert store.record_trade(t) is False
    assert len(store.get_trades(_STRATEGY)) == 1


def test_record_trade_different_instrument_same_day_both_inserted(store: PaperStore) -> None:
    """BUG-4: different instrument_key on same day/action must insert a second row.

    Scenario: leg rolled on the same calendar day — old contract closed,
    new contract opened.  Old constraint (without instrument_key) silently
    dropped the second insert.
    """
    original_key = "NSE_FO|12345"
    rolled_key = "NSE_FO|67890"
    assert store.record_trade(_sell_trade(instrument_key=original_key)) is True
    assert store.record_trade(_sell_trade(instrument_key=rolled_key)) is True
    trades = store.get_trades(_STRATEGY)
    assert len(trades) == 2
    keys = {t.instrument_key for t in trades}
    assert keys == {original_key, rolled_key}


# ── record_trades (batch) ─────────────────────────────────────────────────────


def test_record_trades_happy_path(store: PaperStore) -> None:
    t1 = _sell_trade(leg_role="short_put", trade_date=date(2026, 6, 1))
    t2 = _sell_trade(leg_role="short_call", trade_date=date(2026, 6, 1))
    inserted, skipped = store.record_trades([t1, t2])
    assert len(inserted) == 2
    assert len(skipped) == 0
    trades = store.get_trades(_STRATEGY)
    assert len(trades) == 2


def test_record_trades_duplicate_skip(store: PaperStore) -> None:
    t1 = _sell_trade(leg_role="short_put", trade_date=date(2026, 6, 1))
    t2 = _sell_trade(leg_role="short_call", trade_date=date(2026, 6, 1))
    store.record_trade(t1)  # Insert t1 first

    inserted, skipped = store.record_trades([t1, t2])
    assert len(inserted) == 1
    assert inserted[0].leg_role == "short_call"
    assert len(skipped) == 1
    assert skipped[0].leg_role == "short_put"
    trades = store.get_trades(_STRATEGY)
    assert len(trades) == 2


def test_record_trades_atomicity_rollback(
    store: PaperStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import contextlib

    from src.db import connect as real_connect

    t1 = _sell_trade(leg_role="short_put", trade_date=date(2026, 6, 1))
    t2 = _sell_trade(leg_role="short_call", trade_date=date(2026, 6, 1))

    @contextlib.contextmanager
    def exploding_connect(db_path):
        with real_connect(db_path) as real_conn:

            class Wrapper:
                def __init__(self, conn):
                    self.conn = conn
                    self.call_count = 0

                def execute(self, sql, params=None):
                    if "INSERT INTO paper_trades" in sql:
                        self.call_count += 1
                        if self.call_count == 2:
                            raise RuntimeError("Mocked error")
                    return self.conn.execute(sql, params)

            yield Wrapper(real_conn)

    monkeypatch.setattr("src.paper.store._connect", exploding_connect)

    with pytest.raises(RuntimeError, match="Mocked error"):
        store.record_trades([t1, t2])

    # Verify rollback: t1 should not be in the DB
    trades = store.get_trades(_STRATEGY)
    assert len(trades) == 0


# ── get_trades ────────────────────────────────────────────────────────────────


def test_get_trades_ordered_by_date(store: PaperStore) -> None:
    store.record_trade(_sell_trade(trade_date=date(2026, 6, 1)))
    store.record_trade(_buy_trade(trade_date=date(2026, 5, 1)))
    trades = store.get_trades(_STRATEGY)
    assert trades[0].trade_date < trades[1].trade_date


def test_get_trades_filter_by_leg(store: PaperStore) -> None:
    store.record_trade(_sell_trade(leg_role="short_put"))
    store.record_trade(_sell_trade(leg_role="short_call", instrument_key="NSE_FO|99999"))
    puts = store.get_trades(_STRATEGY, leg_role="short_put")
    assert len(puts) == 1
    assert puts[0].leg_role == "short_put"


def test_get_trades_unknown_strategy_returns_empty(store: PaperStore) -> None:
    assert store.get_trades("paper_unknown") == []


# ── get_position ──────────────────────────────────────────────────────────────


def test_get_position_sell_only(store: PaperStore) -> None:
    store.record_trade(_sell_trade(quantity=75, price=Decimal("120.50")))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.net_qty == -75
    assert pos.avg_cost == Decimal("0")  # no BUYs
    assert pos.avg_sell_price == Decimal("120.50")


def test_get_position_buy_only(store: PaperStore) -> None:
    store.record_trade(_buy_trade(quantity=75, price=Decimal("60.00")))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.net_qty == 75
    assert pos.avg_cost == Decimal("60.00")


def test_get_position_buy_then_sell_net(store: PaperStore) -> None:
    store.record_trade(_buy_trade(trade_date=date(2026, 5, 1)))
    store.record_trade(_sell_trade(trade_date=date(2026, 5, 20)))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.net_qty == 0


def test_get_position_weighted_avg_cost(store: PaperStore) -> None:
    store.record_trade(_buy_trade(trade_date=date(2026, 5, 1), quantity=50, price=Decimal("100")))
    store.record_trade(
        _buy_trade(
            trade_date=date(2026, 5, 2), quantity=50, price=Decimal("120"), action=TradeAction.BUY
        )
    )
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.net_qty == 100
    # (50*100 + 50*120) / 100 = 110
    assert pos.avg_cost == Decimal("110")


def test_get_position_unknown_returns_zero(store: PaperStore) -> None:
    pos = store.get_position("paper_unknown", "missing_leg")
    assert pos.net_qty == 0
    assert pos.avg_cost == Decimal("0")
    assert pos.avg_sell_price == Decimal("0")
    assert pos.instrument_key == ""
    assert pos.option_type is None


# ── get_position / get_positions: option_type resolution (B002.3) ─────────────


def test_get_position_resolves_niftybees_as_eq(db_path: Path) -> None:
    """NiftyBees key short-circuits to EQ without touching InstrumentLookup at all."""
    store = PaperStore(db_path)  # no instrument_lookup injected — must not be needed
    store.record_trade(_sell_trade(instrument_key=NIFTYBEES_KEY))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.option_type == "EQ"


def test_get_position_resolves_short_put_as_pe(db_path: Path) -> None:
    """Happy path: short put resolves to PE via the injected InstrumentLookup."""
    lookup = InstrumentLookup([{"instrument_key": _KEY, "instrument_type": "PE"}])
    store = PaperStore(db_path, instrument_lookup=lookup)
    store.record_trade(_sell_trade(instrument_key=_KEY, quantity=65))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.option_type == "PE"
    assert pos.net_qty == -65


def test_get_position_resolves_call_as_ce(db_path: Path) -> None:
    lookup = InstrumentLookup([{"instrument_key": _KEY, "instrument_type": "CE"}])
    store = PaperStore(db_path, instrument_lookup=lookup)
    store.record_trade(_sell_trade(instrument_key=_KEY))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.option_type == "CE"


def test_get_position_resolves_future_as_fut(db_path: Path) -> None:
    """Resolved instrument with no CE/PE instrument_type (e.g. a future) → FUT."""
    lookup = InstrumentLookup([{"instrument_key": _KEY, "instrument_type": "FUT"}])
    store = PaperStore(db_path, instrument_lookup=lookup)
    store.record_trade(_sell_trade(instrument_key=_KEY))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.option_type == "FUT"


def test_get_position_unrecognised_key_falls_back_to_none_with_warning(
    db_path: Path,
) -> None:
    """Edge case: key not in BOD JSON must not raise — falls back to None + warning.

    Warning is logged via structlog, not routed through Python logging, so not
    assertable via caplog (same constraint documented in
    test_csp_nifty_v1.py::test_find_put_leg_numeric_key_returns_none). Only the
    behavioral contract (no raise, option_type falls back to None) is asserted here.
    """
    lookup = InstrumentLookup([])  # empty — _KEY will never resolve
    store = PaperStore(db_path, instrument_lookup=lookup)
    store.record_trade(_sell_trade(instrument_key=_KEY))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.option_type is None


def test_get_position_unresolvable_bod_file_falls_back_to_none(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BOD JSON missing/corrupt must not raise — get_position degrades to option_type=None.

    Regression guard: get_position/get_positions had zero dependency on the BOD
    file before B002.3 (see code-reviewer findings C1/C2). A stale cron job or
    missing download must not take down position reads.
    """
    import src.paper.store as store_module

    monkeypatch.setattr(store_module, "DEFAULT_BOD_PATH", db_path.parent / "does-not-exist.json.gz")
    store = PaperStore(db_path)  # no instrument_lookup injected — forces lazy load
    store.record_trade(_sell_trade(instrument_key=_KEY))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.option_type is None


def test_get_position_resolved_non_option_type_falls_back_to_none(db_path: Path) -> None:
    """Resolved instrument_type outside CE/PE/FUT (e.g. EQ) must not be mislabeled FUT.

    Regression guard for the reviewer's W1 finding: the original fallback
    returned "FUT" for *any* non-CE/PE resolved type, which would mis-classify
    an equity/index key (anything but NiftyBees, which short-circuits earlier).
    """
    lookup = InstrumentLookup([{"instrument_key": _KEY, "instrument_type": "EQ"}])
    store = PaperStore(db_path, instrument_lookup=lookup)
    store.record_trade(_sell_trade(instrument_key=_KEY))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.option_type is None


def test_get_positions_bulk_resolves_option_type_per_leg(db_path: Path) -> None:
    lookup = InstrumentLookup(
        [
            {"instrument_key": "NSE_FO|11111", "instrument_type": "PE"},
            {"instrument_key": "NSE_FO|22222", "instrument_type": "CE"},
        ]
    )
    store = PaperStore(db_path, instrument_lookup=lookup)
    store.record_trade(
        _sell_trade(leg_role="short_put", instrument_key="NSE_FO|11111", quantity=75)
    )
    store.record_trade(
        _sell_trade(leg_role="short_call", instrument_key="NSE_FO|22222", quantity=75)
    )
    pos_map = {p.leg_role: p for p in store.get_positions(_STRATEGY)}
    assert pos_map["short_put"].option_type == "PE"
    assert pos_map["short_call"].option_type == "CE"


def test_get_positions_still_resolves_option_type_for_open_leg(db_path: Path) -> None:
    """Regression guard for BUG-014's net_qty!=0 gate: an open leg must still resolve."""
    lookup = InstrumentLookup([{"instrument_key": _KEY, "instrument_type": "PE"}])
    store = PaperStore(db_path, instrument_lookup=lookup)
    store.record_trade(_sell_trade(instrument_key=_KEY, quantity=65))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.net_qty == -65
    assert pos.option_type == "PE"


def test_get_positions_skips_option_type_resolution_for_closed_leg(db_path: Path) -> None:
    """BUG-014: a flat (net_qty == 0) leg must not attempt option_type resolution at all.

    Regression guard: get_positions() previously called _resolve_option_type
    unconditionally for every leg_role a strategy has ever traded, including
    fully closed ones. Once a contract expires/is delisted, InstrumentLookup
    can never resolve it again — so a closed leg produced a permanent,
    unactionable option_type_resolution_failed warning on every snapshot run.
    Asserts the resolution call is skipped entirely (not just that it degrades
    to None) by making the call raise if invoked.
    """
    store = PaperStore(db_path)
    store.record_trade(_buy_trade(instrument_key=_KEY, quantity=65))
    store.record_trade(_sell_trade(instrument_key=_KEY, quantity=65, trade_date=date(2026, 5, 20)))

    def _must_not_be_called(instrument_key: str) -> None:
        raise AssertionError(
            f"_resolve_option_type must not be called for a closed leg (net_qty == 0), "
            f"got instrument_key={instrument_key!r}"
        )

    store._resolve_option_type = _must_not_be_called  # type: ignore[method-assign]

    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.net_qty == 0
    assert pos.option_type is None


def test_get_positions_bulk(store: PaperStore) -> None:
    # Record trades for different legs
    store.record_trade(_sell_trade(leg_role="leg_1", quantity=75, price=Decimal("120.50")))
    store.record_trade(_buy_trade(leg_role="leg_2", quantity=75, price=Decimal("60.00")))

    positions = store.get_positions(_STRATEGY)
    assert len(positions) == 2

    # Map by leg_role
    pos_map = {p.leg_role: p for p in positions}
    assert "leg_1" in pos_map
    assert "leg_2" in pos_map

    assert pos_map["leg_1"].net_qty == -75
    assert pos_map["leg_1"].avg_sell_price == Decimal("120.50")

    assert pos_map["leg_2"].net_qty == 75
    assert pos_map["leg_2"].avg_cost == Decimal("60.00")


# ── record_nav_snapshot ───────────────────────────────────────────────────────


def _snap(**overrides) -> PaperNavSnapshot:
    defaults = dict(
        strategy_name=_STRATEGY,
        snapshot_date=date(2026, 5, 1),
        unrealized_pnl=Decimal("500.00"),
        realized_pnl=Decimal("250.00"),
        total_pnl=Decimal("750.00"),
        underlying_price=Decimal("23500.00"),
    )
    defaults.update(overrides)
    return PaperNavSnapshot(**defaults)


def test_record_nav_snapshot_inserts(store: PaperStore) -> None:
    store.record_nav_snapshot(_snap())
    snaps = store.get_nav_snapshots(_STRATEGY)
    assert len(snaps) == 1


def test_record_nav_snapshot_fields_round_trip(store: PaperStore) -> None:
    original = _snap()
    store.record_nav_snapshot(original)
    retrieved = store.get_nav_snapshots(_STRATEGY)[0]
    assert retrieved.strategy_name == original.strategy_name
    assert retrieved.snapshot_date == original.snapshot_date
    assert retrieved.unrealized_pnl == original.unrealized_pnl
    assert retrieved.realized_pnl == original.realized_pnl
    assert retrieved.total_pnl == original.total_pnl
    assert retrieved.underlying_price == original.underlying_price


def test_record_nav_snapshot_upsert_updates(store: PaperStore) -> None:
    store.record_nav_snapshot(_snap(unrealized_pnl=Decimal("100")))
    store.record_nav_snapshot(_snap(unrealized_pnl=Decimal("999")))
    snaps = store.get_nav_snapshots(_STRATEGY)
    assert len(snaps) == 1
    assert snaps[0].unrealized_pnl == Decimal("999")


def test_record_nav_snapshot_underlying_price_none(store: PaperStore) -> None:
    store.record_nav_snapshot(_snap(underlying_price=None))
    retrieved = store.get_nav_snapshots(_STRATEGY)[0]
    assert retrieved.underlying_price is None


def test_record_nav_snapshot_decimal_precision(store: PaperStore) -> None:
    store.record_nav_snapshot(_snap(unrealized_pnl=Decimal("123.456789")))
    retrieved = store.get_nav_snapshots(_STRATEGY)[0]
    assert retrieved.unrealized_pnl == Decimal("123.456789")


# ── get_nav_snapshots ─────────────────────────────────────────────────────────


def test_get_nav_snapshots_ordered_asc(store: PaperStore) -> None:
    store.record_nav_snapshot(_snap(snapshot_date=date(2026, 6, 1)))
    store.record_nav_snapshot(_snap(snapshot_date=date(2026, 5, 1)))
    snaps = store.get_nav_snapshots(_STRATEGY)
    assert snaps[0].snapshot_date < snaps[1].snapshot_date


def test_get_nav_snapshots_unknown_returns_empty(store: PaperStore) -> None:
    assert store.get_nav_snapshots("paper_unknown") == []


# ── get_latest_nav_snapshot ───────────────────────────────────────────────────


def test_get_latest_nav_snapshot_returns_most_recent(store: PaperStore) -> None:
    store.record_nav_snapshot(_snap(snapshot_date=date(2026, 5, 1)))
    store.record_nav_snapshot(_snap(snapshot_date=date(2026, 6, 1)))
    latest = store.get_latest_nav_snapshot(_STRATEGY)
    assert latest is not None
    assert latest.snapshot_date == date(2026, 6, 1)


def test_get_latest_nav_snapshot_none_when_empty(store: PaperStore) -> None:
    assert store.get_latest_nav_snapshot("paper_unknown") is None


# ── get_strategy_names ────────────────────────────────────────────────────────


def test_get_strategy_names_returns_distinct_sorted(store: PaperStore) -> None:
    store.record_trade(_sell_trade(strategy_name="paper_ic_nifty_v1"))
    store.record_trade(_sell_trade(strategy_name="paper_csp_nifty_v1"))
    store.record_trade(_sell_trade(strategy_name="paper_csp_nifty_v1", trade_date=date(2026, 6, 1)))
    names = store.get_strategy_names()
    assert names == ["paper_csp_nifty_v1", "paper_ic_nifty_v1"]


def test_get_strategy_names_empty(store: PaperStore) -> None:
    assert store.get_strategy_names() == []


# ── Schema coexistence ────────────────────────────────────────────────────────


def test_paper_tables_coexist_with_portfolio_tables(db_path: Path) -> None:
    """Paper tables can be created in a DB that already has portfolio tables."""
    from src.portfolio.store import PortfolioStore

    # Create live portfolio schema first
    PortfolioStore(db_path)
    # Now create paper schema in the same DB — must not raise
    ps = PaperStore(db_path)
    ps.record_trade(_sell_trade())
    assert len(ps.get_trades(_STRATEGY)) == 1


# ── TestLegSnapshots ──────────────────────────────────────────────────────────


def _leg_snap(**overrides) -> PaperLegSnapshot:
    defaults = dict(
        strategy_name=_STRATEGY,
        leg_role="overlay_pp",
        snapshot_date=date(2026, 5, 1),
        unrealized_pnl=Decimal("300.00"),
        realized_pnl=Decimal("100.00"),
        total_pnl=Decimal("400.00"),
        ltp=Decimal("220.50"),
    )
    defaults.update(overrides)
    return PaperLegSnapshot(**defaults)


class TestLegSnapshots:
    def test_record_leg_snapshot_roundtrip(self, store: PaperStore) -> None:
        original = _leg_snap()
        store.record_leg_snapshot(original)
        retrieved = store.get_leg_snapshot(_STRATEGY, "overlay_pp", date(2026, 5, 1))
        assert retrieved is not None
        assert retrieved.strategy_name == original.strategy_name
        assert retrieved.leg_role == original.leg_role
        assert retrieved.snapshot_date == original.snapshot_date
        assert retrieved.unrealized_pnl == original.unrealized_pnl
        assert retrieved.realized_pnl == original.realized_pnl
        assert retrieved.total_pnl == original.total_pnl
        assert retrieved.ltp == original.ltp

    def test_record_leg_snapshot_upsert(self, store: PaperStore) -> None:
        store.record_leg_snapshot(
            _leg_snap(unrealized_pnl=Decimal("100"), total_pnl=Decimal("200"))
        )
        store.record_leg_snapshot(
            _leg_snap(unrealized_pnl=Decimal("999"), total_pnl=Decimal("1099"))
        )
        retrieved = store.get_leg_snapshot(_STRATEGY, "overlay_pp", date(2026, 5, 1))
        assert retrieved is not None
        assert retrieved.unrealized_pnl == Decimal("999")
        assert retrieved.total_pnl == Decimal("1099")

    def test_record_leg_snapshot_inconsistent_total_pnl_raises(self, store: PaperStore) -> None:
        # total_pnl=999 but unrealized(300) + realized(100) = 400 — mismatch
        bad = _leg_snap(total_pnl=Decimal("999"))
        with pytest.raises(ValueError, match="total_pnl invariant violated"):
            store.record_leg_snapshot(bad)

    def test_get_leg_snapshot_missing(self, store: PaperStore) -> None:
        result = store.get_leg_snapshot(_STRATEGY, "overlay_pp", date(2026, 5, 1))
        assert result is None

    def test_get_prev_leg_snapshot_returns_max_before_date(self, store: PaperStore) -> None:
        store.record_leg_snapshot(_leg_snap(snapshot_date=date(2026, 5, 1)))
        store.record_leg_snapshot(
            _leg_snap(
                snapshot_date=date(2026, 5, 2),
                unrealized_pnl=Decimal("400"),
                total_pnl=Decimal("500"),
            )
        )
        # before_date=2026-05-03 → should return the 2026-05-02 row (MAX < 2026-05-03)
        prev = store.get_prev_leg_snapshot(_STRATEGY, "overlay_pp", date(2026, 5, 3))
        assert prev is not None
        assert prev.snapshot_date == date(2026, 5, 2)
        assert prev.unrealized_pnl == Decimal("400")

    def test_get_prev_leg_snapshot_no_prior(self, store: PaperStore) -> None:
        store.record_leg_snapshot(_leg_snap(snapshot_date=date(2026, 5, 5)))
        # before_date=2026-05-05 → nothing strictly before it
        prev = store.get_prev_leg_snapshot(_STRATEGY, "overlay_pp", date(2026, 5, 5))
        assert prev is None

    def test_delete_trade_removes_correct_row(self, store: PaperStore) -> None:
        t1 = _sell_trade(leg_role="overlay_pp", trade_date=date(2026, 5, 1))
        t2 = _buy_trade(leg_role="overlay_pp", trade_date=date(2026, 5, 28))
        store.record_trade(t1)
        store.record_trade(t2)
        assert len(store.get_trades(_STRATEGY, leg_role="overlay_pp")) == 2

        store.delete_trade(t1)
        remaining = store.get_trades(_STRATEGY, leg_role="overlay_pp")
        assert len(remaining) == 1
        assert remaining[0].trade_date == date(2026, 5, 28)
        assert remaining[0].action == TradeAction.BUY

    def test_delete_trade_noop_when_not_found(self, store: PaperStore) -> None:
        # Deleting a nonexistent trade must not raise
        ghost = _sell_trade(leg_role="overlay_pp", trade_date=date(2026, 1, 1))
        store.delete_trade(ghost)  # should be silent no-op
        assert store.get_trades(_STRATEGY) == []

    def test_delete_trade_respects_instrument_key(self, store: PaperStore) -> None:
        """delete_trade must not delete a row with a different instrument_key
        even when (strategy, leg_role, trade_date, action) all match."""
        key_a = "NSE_FO|NIFTY25000PE"
        key_b = "NSE_FO|NIFTY24500PE"
        t_a = _sell_trade(leg_role="short_put", trade_date=date(2026, 6, 1), instrument_key=key_a)
        t_b = _sell_trade(leg_role="short_put", trade_date=date(2026, 6, 1), instrument_key=key_b)
        # These share the same (strategy, leg_role, trade_date, action) — different instrument.
        # The unique constraint is on those 4 fields, so only one can be inserted.
        # Record t_a first; t_b will be skipped as a duplicate by the unique constraint.
        store.record_trade(t_a)
        # Now attempt to delete using t_b's instrument_key — should be a no-op.
        store.delete_trade(t_b)
        trades = store.get_trades(_STRATEGY, leg_role="short_put")
        assert len(trades) == 1
        assert trades[0].instrument_key == key_a

    def test_delete_trade_by_id_removes_correct_row(self, store: PaperStore) -> None:
        import sqlite3

        t1 = _sell_trade(leg_role="overlay_cc", trade_date=date(2026, 5, 1))
        t2 = _buy_trade(leg_role="overlay_cc", trade_date=date(2026, 5, 28))
        store.record_trade(t1)
        store.record_trade(t2)
        # Fetch the id of t1
        with sqlite3.connect(store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id FROM paper_trades WHERE action = 'SELL' AND leg_role = 'overlay_cc'"
            ).fetchone()
        assert row is not None
        store.delete_trade_by_id(row["id"])
        remaining = store.get_trades(_STRATEGY, leg_role="overlay_cc")
        assert len(remaining) == 1
        assert remaining[0].action == TradeAction.BUY

    def test_delete_trade_by_id_noop_on_missing_id(self, store: PaperStore) -> None:
        store.delete_trade_by_id(999999)  # must not raise
        assert store.get_trades(_STRATEGY) == []


# ── CR1b: update_trade_state ──────────────────────────────────────────────────


def test_update_trade_state_changes_state(store: PaperStore) -> None:
    trade = _sell_trade()
    store.record_trade(trade)
    # Fetch the id directly from SQLite
    import sqlite3

    conn = sqlite3.connect(store.db_path)
    row = conn.execute(
        "SELECT id FROM paper_trades WHERE strategy_name=? AND leg_role=? AND trade_date=? AND action=?",
        (_STRATEGY, _LEG, _DATE.isoformat(), "SELL"),
    ).fetchone()
    conn.close()
    trade_id = row[0]

    store.update_trade_state(trade_id, TradeState.DEFENDED)

    trades = store.get_trades(_STRATEGY, _LEG)
    assert trades[0].state == TradeState.DEFENDED


def test_update_trade_state_unknown_id_raises(store: PaperStore) -> None:
    import pytest

    with pytest.raises(ValueError, match="No paper trade found"):
        store.update_trade_state(99999, TradeState.DEFENDED)


# ── BUG-6: mark_trade_closed ──────────────────────────────────────────────────


def test_mark_trade_closed_transitions_open_to_closed(store: PaperStore) -> None:
    """Happy path: OPEN trade becomes CLOSED after mark_trade_closed."""
    store.record_trade(_sell_trade())
    store.mark_trade_closed(_STRATEGY, _LEG, _KEY)
    trades = store.get_trades(_STRATEGY, _LEG)
    assert len(trades) == 1
    assert trades[0].state == TradeState.CLOSED


def test_mark_trade_closed_transitions_defended_to_closed(store: PaperStore) -> None:
    """DEFENDED trade (one roll consumed) also transitions to CLOSED."""
    import sqlite3

    store.record_trade(_sell_trade())
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE paper_trades SET state = 'DEFENDED' WHERE strategy_name=? AND leg_role=? AND instrument_key=?",
            (_STRATEGY, _LEG, _KEY),
        )
    store.mark_trade_closed(_STRATEGY, _LEG, _KEY)
    trades = store.get_trades(_STRATEGY, _LEG)
    assert trades[0].state == TradeState.CLOSED


def test_mark_trade_closed_unknown_combination_is_noop(store: PaperStore) -> None:
    """No matching row → no error, no state change."""
    store.record_trade(_sell_trade())
    store.mark_trade_closed(_STRATEGY, _LEG, "NSE_FO|NONEXISTENT")
    # Original trade must be untouched
    trades = store.get_trades(_STRATEGY, _LEG)
    assert trades[0].state == TradeState.OPEN


def test_mark_trade_closed_does_not_touch_re_entry_pending(store: PaperStore) -> None:
    """RE_ENTRY_PENDING is terminal — mark_trade_closed must not change it."""
    import sqlite3

    store.record_trade(_sell_trade())
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE paper_trades SET state = 'RE_ENTRY_PENDING' WHERE strategy_name=? AND leg_role=? AND instrument_key=?",
            (_STRATEGY, _LEG, _KEY),
        )
    store.mark_trade_closed(_STRATEGY, _LEG, _KEY)
    trades = store.get_trades(_STRATEGY, _LEG)
    assert trades[0].state == TradeState.RE_ENTRY_PENDING


def test_record_trade_persists_state_field(store: PaperStore) -> None:
    from src.models.portfolio import TradeAction

    trade = PaperTrade(
        strategy_name=_STRATEGY,
        leg_role=_LEG,
        instrument_key=_KEY,
        trade_date=_DATE,
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("120.00"),
        state=TradeState.DEFENDED,
    )
    store.record_trade(trade)
    trades = store.get_trades(_STRATEGY, _LEG)
    assert trades[0].state == TradeState.DEFENDED


# ── SM-1: get_trade_state + mark_trade_defended ───────────────────────────────


def test_get_trade_state_returns_open_when_no_trade(store: PaperStore) -> None:
    """No trades present → defaults to OPEN (safe fallback)."""
    state = store.get_trade_state(_STRATEGY, _LEG)
    assert state == TradeState.OPEN


def test_get_trade_state_returns_open_for_open_trade(store: PaperStore) -> None:
    """OPEN trade present → returns OPEN."""
    store.record_trade(_sell_trade())
    assert store.get_trade_state(_STRATEGY, _LEG) == TradeState.OPEN


def test_get_trade_state_returns_defended_after_mark(store: PaperStore) -> None:
    """DEFENDED state is persisted and readable via get_trade_state."""
    store.record_trade(_sell_trade())
    store.mark_trade_defended(_STRATEGY, _LEG, _KEY)
    assert store.get_trade_state(_STRATEGY, _LEG) == TradeState.DEFENDED


def test_get_trade_state_ignores_closed_trades(store: PaperStore) -> None:
    """CLOSED trade is invisible to get_trade_state → defaults to OPEN."""
    store.record_trade(_sell_trade())
    store.mark_trade_closed(_STRATEGY, _LEG, _KEY)
    assert store.get_trade_state(_STRATEGY, _LEG) == TradeState.OPEN


def test_mark_trade_defended_only_transitions_open(store: PaperStore) -> None:
    """mark_trade_defended is a no-op when the trade is already DEFENDED."""
    store.record_trade(_sell_trade())
    store.mark_trade_defended(_STRATEGY, _LEG, _KEY)
    store.mark_trade_defended(_STRATEGY, _LEG, _KEY)  # idempotent second call
    assert store.get_trade_state(_STRATEGY, _LEG) == TradeState.DEFENDED


def test_mark_trade_defended_unknown_key_is_noop(store: PaperStore) -> None:
    """Non-existent instrument_key → no error, original trade unchanged."""
    store.record_trade(_sell_trade())
    store.mark_trade_defended(_STRATEGY, _LEG, "NSE_FO|NONEXISTENT")
    assert store.get_trade_state(_STRATEGY, _LEG) == TradeState.OPEN


# ── DBI-3: get_positions entry_date and instrument_key fixes ─────────────────


def test_get_positions_entry_date_for_buy_first_leg(store: PaperStore) -> None:
    """Long-first (BUY-opened) leg must populate entry_date from the BUY trade."""
    buy_date = date(2026, 5, 5)
    store.record_trade(_buy_trade(trade_date=buy_date, leg_role="long_put"))
    positions = store.get_positions(_STRATEGY)
    pos = next(p for p in positions if p.leg_role == "long_put")
    assert pos.entry_date == buy_date


def test_get_positions_entry_date_for_sell_first_leg(store: PaperStore) -> None:
    """Short (SELL-opened) leg entry_date must equal the SELL trade date."""
    sell_date = date(2026, 5, 10)
    store.record_trade(_sell_trade(trade_date=sell_date))
    positions = store.get_positions(_STRATEGY)
    pos = next(p for p in positions if p.leg_role == _LEG)
    assert pos.entry_date == sell_date


def test_get_positions_entry_date_tracks_current_cycle(store: PaperStore) -> None:
    """After a full close+reopen, entry_date must reflect the reopen date, not the first-ever trade."""
    key_a = "NSE_FO|NIFTY22500PE"
    key_b = "NSE_FO|NIFTY23000PE"
    # Cycle 1: open and close
    store.record_trade(_sell_trade(trade_date=date(2026, 5, 1), instrument_key=key_a))
    store.record_trade(_buy_trade(trade_date=date(2026, 5, 10), instrument_key=key_a))
    # Cycle 2: reopen on a later date
    reopen_date = date(2026, 5, 15)
    store.record_trade(_sell_trade(trade_date=reopen_date, instrument_key=key_b))

    positions = store.get_positions(_STRATEGY)
    pos = next(p for p in positions if p.leg_role == _LEG)
    assert pos.net_qty == -75
    assert pos.entry_date == reopen_date


def test_get_positions_instrument_key_from_current_cycle(store: PaperStore) -> None:
    """After a roll (close contract A, reopen contract B), instrument_key must equal B not A."""
    key_a = "NSE_FO|NIFTY22500PE"
    key_b = "NSE_FO|NIFTY23000PE"
    # Cycle 1: open and close A
    store.record_trade(_sell_trade(trade_date=date(2026, 5, 1), instrument_key=key_a))
    store.record_trade(_buy_trade(trade_date=date(2026, 5, 10), instrument_key=key_a))
    # Cycle 2: open B
    store.record_trade(_sell_trade(trade_date=date(2026, 5, 15), instrument_key=key_b))

    positions = store.get_positions(_STRATEGY)
    pos = next(p for p in positions if p.leg_role == _LEG)
    assert pos.instrument_key == key_b


def test_get_positions_multi_cycle_avg_sell_price_current_cycle_only(
    store: PaperStore,
) -> None:
    """BUG-1: avg_sell_price must reflect only the current open cycle, not prior cycles.

    Regression: before the cycle-reset fix, avg_sell_price blended all historical
    SELL prices (e.g. 210.51 instead of 231.68 for the current cycle).
    """
    key_a = "NSE_FO|NIFTY22500PE"
    key_b = "NSE_FO|NIFTY23000PE"
    cycle1_sell_price = Decimal("210.51")
    cycle2_sell_price = Decimal("231.68")

    # Cycle 1: open @ 210.51, close
    store.record_trade(
        _sell_trade(trade_date=date(2026, 5, 1), instrument_key=key_a, price=cycle1_sell_price)
    )
    store.record_trade(_buy_trade(trade_date=date(2026, 5, 8), instrument_key=key_a))
    # Cycle 2: reopen @ 231.68 (current open)
    store.record_trade(
        _sell_trade(trade_date=date(2026, 5, 9), instrument_key=key_b, price=cycle2_sell_price)
    )

    positions = store.get_positions(_STRATEGY)
    pos = next(p for p in positions if p.leg_role == _LEG)
    assert pos.net_qty == -75
    assert pos.avg_sell_price == cycle2_sell_price, (
        f"avg_sell_price should be {cycle2_sell_price} (current cycle only), got {pos.avg_sell_price}"
    )


def test_get_positions_fully_closed_cycle_returns_net_zero(store: PaperStore) -> None:
    """A leg that was opened and fully closed has net_qty=0 — no open position."""
    # Open and close a full cycle
    store.record_trade(_sell_trade(trade_date=date(2026, 5, 1)))
    store.record_trade(_buy_trade(trade_date=date(2026, 5, 8)))

    positions = store.get_positions(_STRATEGY)
    pos = next((p for p in positions if p.leg_role == _LEG), None)
    assert pos is not None
    assert pos.net_qty == 0


def test_proxy_delta_breach_count_methods(store: PaperStore) -> None:
    # Get count for non-existent strategy
    assert store.get_proxy_delta_breach_count("paper_nonexistent") == 0

    # Set count to 1
    store.set_proxy_delta_breach_count("paper_nonexistent", 1)
    assert store.get_proxy_delta_breach_count("paper_nonexistent") == 1

    # Update count to 2
    store.set_proxy_delta_breach_count("paper_nonexistent", 2)
    assert store.get_proxy_delta_breach_count("paper_nonexistent") == 2

    # Reset count to 0
    store.set_proxy_delta_breach_count("paper_nonexistent", 0)
    assert store.get_proxy_delta_breach_count("paper_nonexistent") == 0
