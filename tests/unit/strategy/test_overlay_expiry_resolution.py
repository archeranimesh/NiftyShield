"""YF-4: pure overlay expiry resolver + clock/tenor injection into the bootstraps."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.strategies.three_track import paper_3track_overlay_entry as oe
from src.instruments.lookup import InstrumentLookup
from src.strategy.overlay_tenor import OVERLAY_TENORS, resolve_overlay_expiry

BOD = Path(__file__).parent.parent.parent / "fixtures" / "contract_resolver"
BOD = BOD / "upstox_bod_nifty_dec.json"
MONTHLY = OVERLAY_TENORS["monthly"]
YEARLY = OVERLAY_TENORS["yearly"]


def _tuesdays(start: date, end: date) -> list[date]:
    d = start + timedelta(days=(1 - start.weekday()) % 7)
    out = []
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


def _lookup(expiries: list[date]) -> InstrumentLookup:
    ms = lambda d: int(  # noqa: E731
        datetime(d.year, d.month, d.day, 10, tzinfo=timezone.utc).timestamp() * 1000
    )
    return InstrumentLookup(
        [
            {
                "segment": "NSE_FO",
                "instrument_type": "CE",
                "underlying_symbol": "NIFTY",
                "expiry": ms(d),
                "instrument_key": f"NSE_FO|{d.isoformat()}",
            }
            for d in expiries
        ]
    )


def _legacy_monthly(lookup: InstrumentLookup, today: date) -> str | None:
    """Verbatim pre-YF-4 resolution block (get candidates, find label, DTE >= 14)."""
    exps = lookup.get_expiry_candidates(underlying="NIFTY", today=today, preference=["monthly"])
    found = next((e for label, e in exps if label == "monthly"), None)
    if not found or (date.fromisoformat(found) - today).days < 14:
        return None
    return found


WEEKLIES = _lookup(_tuesdays(date(2026, 9, 1), date(2027, 12, 31)))


def test_monthly_default_unchanged() -> None:
    # Golden values pinned from the pre-refactor behaviour.
    assert resolve_overlay_expiry(WEEKLIES, date(2026, 10, 6), MONTHLY) == "2026-10-27"
    assert resolve_overlay_expiry(WEEKLIES, date(2026, 10, 14), MONTHLY) == "2026-11-24"
    assert resolve_overlay_expiry(WEEKLIES, date(2026, 12, 15), MONTHLY) == "2026-12-29"


def test_monthly_matches_legacy_block_every_day() -> None:
    day = date(2026, 9, 1)
    while day < date(2027, 11, 1):
        assert resolve_overlay_expiry(WEEKLIES, day, MONTHLY) == _legacy_monthly(WEEKLIES, day), day
        day += timedelta(days=1)


def test_yearly_resolves_dec2026_on_2026_10_06() -> None:
    lookup = InstrumentLookup.from_file(BOD)
    assert resolve_overlay_expiry(lookup, date(2026, 10, 6), YEARLY) == "2026-12-29"


def test_yearly_resolves_dec2027_on_2026_12_30() -> None:
    lookup = InstrumentLookup.from_file(BOD)
    assert resolve_overlay_expiry(lookup, date(2026, 12, 30), YEARLY) == "2027-12-28"


def test_yearly_moves_to_dec2027_at_roll_dte_and_blocks_entry_below_floor() -> None:
    both = _lookup([date(2026, 12, 29), date(2027, 12, 28)])
    # DTE 21 -> Dec 2026; DTE 16..20 -> Dec 2026 but under the 20 DTE entry floor; DTE 15 -> Dec 2027.
    assert resolve_overlay_expiry(both, date(2026, 12, 8), YEARLY) == "2026-12-29"
    assert resolve_overlay_expiry(both, date(2026, 12, 13), YEARLY) is None
    assert resolve_overlay_expiry(both, date(2026, 12, 14), YEARLY) == "2027-12-28"


def test_no_candidate_returns_none() -> None:
    assert resolve_overlay_expiry(_lookup([]), date(2026, 10, 6), MONTHLY) is None
    assert resolve_overlay_expiry(_lookup([date(2026, 10, 6)]), date(2026, 10, 6), YEARLY) is None


def test_no_candidate_bootstrap_aborts_structurally() -> None:
    for fn in (oe.auto_cc_bootstrap, oe.auto_pp_bootstrap, oe.auto_collar_bootstrap):
        with patch.object(oe.InstrumentLookup, "from_file", return_value=_lookup([])):
            assert fn(Path("x.json"), today=date(2026, 10, 6)) == (None, None)


def test_bootstrap_defaults_clock_to_market_today() -> None:
    lookup = MagicMock()
    lookup.get_expiry_candidates.return_value = []
    with (
        patch.object(oe.InstrumentLookup, "from_file", return_value=lookup),
        patch.object(oe, "market_today", return_value=date(2026, 10, 6)) as clock,
    ):
        assert oe.auto_cc_bootstrap(Path("x.json")) == (None, None)
    clock.assert_called_once()
    assert lookup.get_expiry_candidates.call_args.kwargs["today"] == date(2026, 10, 6)


def test_bootstrap_uses_injected_policy_bucket() -> None:
    lookup = MagicMock()
    lookup.get_expiry_candidates.return_value = []
    with patch.object(oe.InstrumentLookup, "from_file", return_value=lookup):
        oe.auto_pp_bootstrap(Path("x.json"), today=date(2026, 10, 6), policy=YEARLY)
    assert lookup.get_expiry_candidates.call_args.kwargs["preference"] == ["yearly"]


def test_open_pp_dte_takes_injected_today(tmp_path: Path) -> None:
    import sqlite3

    from src.paper.constants import STRATEGY_OVERLAY

    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE paper_trades (strategy_name TEXT, leg_role TEXT, instrument_key TEXT,"
        " action TEXT, quantity INTEGER)"
    )
    conn.execute(
        "INSERT INTO paper_trades VALUES (?, 'overlay_pp', 'NSE_FO|NIFTY29DEC2026PE', 'BUY', 65)",
        (STRATEGY_OVERLAY,),
    )
    conn.commit()
    conn.close()
    assert oe._open_pp_dte(db, tmp_path / "x", today=date(2026, 12, 24)) == 5
