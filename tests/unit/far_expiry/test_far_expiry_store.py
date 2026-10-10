import datetime
from decimal import Decimal

import pytest

from src.far_expiry.store import (
    FarExpiryStore,
    chain_to_liquidity_rows,
)
from src.models.options import OptionChain, OptionChainStrike, OptionLeg


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test_store.db"
    return FarExpiryStore(db_path)


def _make_leg(
    bid="1.0",
    ask="2.0",
    ltp="1.5",
    oi=100,
    volume=50,
    delta="0.5",
    gamma="0.01",
    theta="-0.02",
    vega="0.03",
    iv="15.0",
):
    return OptionLeg(
        strike=Decimal("10000"),
        ltp=Decimal(ltp),
        bid=Decimal(bid),
        ask=Decimal(ask),
        oi=oi,
        volume=volume,
        delta=Decimal(delta) if delta is not None else None,
        gamma=Decimal(gamma) if gamma is not None else None,
        theta=Decimal(theta) if theta is not None else None,
        vega=Decimal(vega) if vega is not None else None,
        iv=Decimal(iv) if iv is not None else None,
    )


def test_record_then_read_round_trip(store):
    dt = datetime.date(2026, 10, 10)
    cap = datetime.datetime(2026, 10, 10, 10, 0, tzinfo=datetime.timezone.utc)
    expiry = datetime.date(2026, 12, 31)

    ce_leg = _make_leg(delta="0.5")
    pe_leg = _make_leg(delta="-0.5")
    strike = Decimal("10000")

    chain = OptionChain(
        underlying_spot=Decimal("10000"),
        expiry=expiry,
        strikes={strike: OptionChainStrike(ce=ce_leg, pe=pe_leg)},
    )

    store.record_chain(dt, cap, "NIFTY", "dhan", chain)

    rows = store.read_chain_snapshots(dt, dt, expiry, "dhan")
    assert len(rows) == 2
    ce_row = [r for r in rows if r.option_type == "CE"][0]

    assert ce_row.snapshot_date == dt
    assert ce_row.captured_at == cap
    assert ce_row.underlying == "NIFTY"
    assert ce_row.expiry == expiry
    assert ce_row.strike == strike
    assert ce_row.source == "dhan"
    assert ce_row.underlying_spot == Decimal("10000")
    assert ce_row.ltp == Decimal("1.5")
    assert ce_row.bid == Decimal("1.0")
    assert ce_row.ask == Decimal("2.0")
    assert ce_row.oi == 100
    assert ce_row.volume == 50
    assert ce_row.delta == Decimal("0.5")


def test_record_twice_is_idempotent(store):
    dt = datetime.date(2026, 10, 10)
    cap = datetime.datetime(2026, 10, 10, 10, 0, tzinfo=datetime.timezone.utc)
    expiry = datetime.date(2026, 12, 31)

    chain = OptionChain(
        underlying_spot=Decimal("10000"),
        expiry=expiry,
        strikes={Decimal("10000"): OptionChainStrike(ce=_make_leg())},
    )

    store.record_chain(dt, cap, "NIFTY", "dhan", chain)
    store.record_chain(dt, cap, "NIFTY", "dhan", chain)

    rows = store.read_chain_snapshots(dt, dt, expiry, "dhan")
    assert len(rows) == 1


def test_zero_delta_rows_flagged(store):
    chain = OptionChain(
        underlying_spot=Decimal("10000"),
        expiry=datetime.date(2026, 12, 31),
        strikes={Decimal("10000"): OptionChainStrike(ce=_make_leg(delta="0"))},
    )

    liq = chain_to_liquidity_rows(chain)[0]
    assert liq.is_zero_delta is True


def test_one_sided_quote_flagged_not_quoted(store):
    chain = OptionChain(
        underlying_spot=Decimal("10000"),
        expiry=datetime.date(2026, 12, 31),
        strikes={Decimal("10000"): OptionChainStrike(ce=_make_leg(bid="1.0", ask="0.0"))},
    )

    liq = chain_to_liquidity_rows(chain)[0]
    assert liq.is_one_sided is True
    assert liq.is_quoted is False
    assert liq.mid is None
    assert liq.spread_pct_mid is None


def test_none_greek_stays_null(store):
    dt = datetime.date(2026, 10, 10)
    cap = datetime.datetime(2026, 10, 10, 10, 0, tzinfo=datetime.timezone.utc)
    expiry = datetime.date(2026, 12, 31)

    chain = OptionChain(
        underlying_spot=Decimal("10000"),
        expiry=expiry,
        strikes={
            Decimal("10000"): OptionChainStrike(
                ce=_make_leg(delta=None, gamma=None, theta=None, vega=None, iv=None)
            )
        },
    )

    store.record_chain(dt, cap, "NIFTY", "dhan", chain)

    rows = store.read_chain_snapshots(dt, dt, expiry, "dhan")
    assert len(rows) == 1
    assert rows[0].delta is None
    assert rows[0].gamma is None
    assert rows[0].theta is None
    assert rows[0].vega is None
    assert rows[0].iv is None

    # Verify in DB it's actually NULL
    import sqlite3

    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        db_row = conn.execute("SELECT delta, iv FROM far_expiry_chain_snapshots").fetchone()
        assert db_row["delta"] is None
        assert db_row["iv"] is None


def test_zero_mid_handled(store):
    chain = OptionChain(
        underlying_spot=Decimal("10000"),
        expiry=datetime.date(2026, 12, 31),
        strikes={Decimal("10000"): OptionChainStrike(ce=_make_leg(bid="0.0", ask="0.0"))},
    )

    liq = chain_to_liquidity_rows(chain)[0]
    assert liq.is_quoted is False
    assert liq.is_one_sided is False
    assert liq.mid is None
    assert liq.spread_pct_mid is None


def test_crossed_book_flagged(store):
    chain = OptionChain(
        underlying_spot=Decimal("10000"),
        expiry=datetime.date(2026, 12, 31),
        strikes={Decimal("10000"): OptionChainStrike(ce=_make_leg(bid="2.0", ask="1.0"))},
    )

    liq = chain_to_liquidity_rows(chain)[0]
    assert liq.is_quoted is True
    assert liq.is_crossed_book is True
    assert liq.mid == Decimal("1.5")
    assert liq.spread_pct_mid == Decimal("-0.6666666666666666666666666667")  # roughly -2/3
