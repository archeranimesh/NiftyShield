from datetime import date, timedelta

from src.instruments.lookup import InstrumentLookup


def test_expiry_candidates_happy_path():
    """BOD with monthly + quarterly + yearly returns all in correct CSP order."""
    today = date(2026, 5, 10)
    # monthly: 15-45 (2026-05-25 to 2026-06-24) -> May 28, 2026 (DTE 18)
    # quarterly: 46-200 (2026-06-25 to 2026-11-26) -> June 25, 2026 (DTE 46, month 6)
    # yearly: 201-420 (2026-11-27 to 2027-07-04) -> Dec 31, 2026 (DTE 235, month 12)

    m_exp = "2026-05-28"
    q_exp = "2026-06-25"
    y_exp = "2026-12-31"

    instruments = [
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": m_exp,
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "CE",
            "underlying_symbol": "NIFTY",
            "expiry": q_exp,
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": y_exp,
        },
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)

    assert candidates == [("monthly", m_exp), ("quarterly", q_exp), ("yearly", y_exp)]


def test_expiry_candidates_dte_gate():
    """Expiries with DTE < 15 are excluded."""
    today = date(2026, 5, 10)
    too_close = (today + timedelta(days=14)).isoformat()
    just_right = (today + timedelta(days=15)).isoformat()

    instruments = [
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": too_close,
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": just_right,
        },
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)

    assert len(candidates) == 1
    assert candidates[0] == ("monthly", just_right)


def test_expiry_candidates_dte_boundary():
    """DTE=45 is monthly, DTE=46 is quarterly."""
    # Test DTE=45 is monthly:
    # Let today be April 13, 2026. May 28, 2026 (last Thursday of May) is DTE 45.
    today_m = date(2026, 4, 13)
    m_exp = "2026-05-28"
    lookup_m = InstrumentLookup(
        [
            {
                "segment": "NSE_FO",
                "instrument_type": "PE",
                "underlying_symbol": "NIFTY",
                "expiry": m_exp,
            }
        ]
    )
    candidates_m = lookup_m.get_expiry_candidates("NIFTY", today_m)
    assert candidates_m == [("monthly", m_exp)]

    # Test DTE=46 is quarterly:
    # Let today be May 10, 2026. June 25, 2026 (last Thursday of June) is DTE 46.
    today_q = date(2026, 5, 10)
    q_exp = "2026-06-25"
    lookup_q = InstrumentLookup(
        [
            {
                "segment": "NSE_FO",
                "instrument_type": "PE",
                "underlying_symbol": "NIFTY",
                "expiry": q_exp,
            }
        ]
    )
    candidates_q = lookup_q.get_expiry_candidates("NIFTY", today_q)
    assert candidates_q == [("quarterly", q_exp)]


def test_expiry_candidates_missing_category():
    """Missing category (e.g. quarterly) does not crash and returns others."""
    today = date(2026, 5, 10)
    m_exp = "2026-05-28"
    y_exp = "2026-12-31"

    instruments = [
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": m_exp,
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": y_exp,
        },
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)

    assert candidates == [("monthly", m_exp), ("yearly", y_exp)]


def test_expiry_candidates_custom_preference():
    """Custom preference order is respected."""
    today = date(2026, 5, 10)
    m_exp = "2026-05-28"
    q_exp = "2026-06-25"
    y_exp = "2026-12-31"

    instruments = [
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": m_exp,
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": q_exp,
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": y_exp,
        },
    ]
    lookup = InstrumentLookup(instruments)

    # Test 3-track style preference: quarterly -> yearly -> monthly
    pref = ["quarterly", "yearly", "monthly"]
    candidates = lookup.get_expiry_candidates("NIFTY", today, preference=pref)

    assert candidates == [("quarterly", q_exp), ("yearly", y_exp), ("monthly", m_exp)]


def test_expiry_candidates_no_network_mock_bod():
    """Verify it uses provided instruments and no network calls (implicitly tested by no mock)."""
    today = date(2026, 5, 10)
    # Different underlying should be ignored
    instruments = [
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "BANKNIFTY",
            "expiry": "2026-05-28",
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-05-28",
        },
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)

    assert len(candidates) == 1
    assert candidates[0] == ("monthly", "2026-05-28")


def test_weekly_nearest_tuesday():
    """Two Tuesdays and one non-Tuesday in DTE≤14; preference=["weekly"] picks the nearer Tuesday."""
    # June 25, 2026 = Thursday
    today = date(2026, 6, 25)
    instruments = [
        # Tuesday DTE 5 — nearest Tuesday
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-06-30",
        },
        # Tuesday DTE 12
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-07-07",
        },
        # Sunday DTE 3 — not Tuesday, must be ignored
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-06-28",
        },
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today, preference=["weekly"])
    assert candidates == [("weekly", "2026-06-30")]


def test_weekly_not_in_default_preference():
    """Default preference ["monthly","quarterly","yearly"] does not include "weekly"."""
    today = date(2026, 6, 25)
    instruments = [
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-06-30",
        },
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)
    labels = [label for label, _ in candidates]
    assert "weekly" not in labels


def test_weekly_and_monthly_coexist():
    """Tuesday at DTE≤14 and last-of-month at DTE 15–45 both returned when preference includes both."""
    # June 10, 2026 = Wednesday
    today = date(2026, 6, 10)
    instruments = [
        # June 16 = Tuesday, DTE 6 → weekly
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-06-16",
        },
        # June 30 = Tuesday and last-of-month, DTE 20 → monthly (DTE > 14, not weekly)
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-06-30",
        },
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today, preference=["weekly", "monthly"])
    assert candidates == [("weekly", "2026-06-16"), ("monthly", "2026-06-30")]


def test_weekly_no_tuesday_in_window():
    """Only non-Tuesday expiries at DTE≤14; preference=["weekly"] returns empty list."""
    # June 25, 2026 = Thursday
    today = date(2026, 6, 25)
    instruments = [
        # July 2 = Thursday, DTE 7 — not Tuesday
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-07-02",
        },
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today, preference=["weekly"])
    assert candidates == []


def test_weekly_boundary_inclusive_14():
    """Tuesday at exactly DTE 14 is included in the weekly bucket."""
    # June 16, 2026 = Tuesday; June 30 = Tuesday, DTE 14
    today = date(2026, 6, 16)
    instruments = [
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-06-30",
        },
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today, preference=["weekly"])
    assert candidates == [("weekly", "2026-06-30")]


def test_weekly_boundary_exclusive_15():
    """Tuesday at DTE 15 is NOT in the weekly bucket (DTE > 14)."""
    # June 15, 2026 = Monday; June 30 = Tuesday, DTE 15
    today = date(2026, 6, 15)
    instruments = [
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-06-30",
        },
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today, preference=["weekly"])
    assert candidates == []


def test_expiry_candidates_ignores_weeklies():
    """Verify that weekly expiries (not the last of the month) are ignored, choosing only monthly."""
    today = date(2026, 5, 10)

    # May expiries:
    # 2026-05-14 (weekly, DTE 4 - too close anyway)
    # 2026-05-21 (weekly, DTE 11 - too close anyway)
    # 2026-05-28 (monthly, DTE 18 - last of May, so monthly candidate)
    # June expiries:
    # 2026-06-04 (weekly, DTE 25 - in monthly DTE band, but should be ignored because it is a weekly cadence)
    # 2026-06-11 (weekly, DTE 32 - in monthly DTE band, but should be ignored)
    # 2026-06-18 (weekly, DTE 39 - in monthly DTE band, but should be ignored)
    # 2026-06-25 (monthly, DTE 46 - last of June, quarterly month, so quarterly candidate)

    instruments = [
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-05-14",
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-05-21",
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-05-28",
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-06-04",
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-06-11",
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-06-18",
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-06-25",
        },
    ]

    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)

    # Even though 2026-06-04, 06-11, 06-18 have 15 <= DTE <= 45, they are weekly contracts
    # and should NOT be selected as the monthly candidate.
    # Instead, 2026-05-28 (DTE 18, last of May) is the monthly candidate.
    # 2026-06-25 (DTE 46, last of June) is the quarterly candidate.
    assert candidates == [("monthly", "2026-05-28"), ("quarterly", "2026-06-25")]


def test_get_next_contract_in_band_skips_weekly():
    """A same-strike weekly contract must be skipped in favor of the next monthly."""
    today = date(2026, 5, 10)
    # Current (expiring) contract, DTE < 1 so it's excluded from its own band search.
    expiring = "2026-05-11"
    weekly = "2026-05-14"  # same strike, DTE 4 -> would be `get_next_contract`'s pick
    monthly = "2026-05-28"  # same strike, DTE 18, last of May -> correct pick

    instruments = [
        {
            "instrument_key": "NSE_FO|NIFTY26MAY11W22000CE",
            "segment": "NSE_FO",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 22000.0,
            "expiry": expiring,
        },
        {
            "instrument_key": "NSE_FO|NIFTY26MAY14W22000CE",
            "segment": "NSE_FO",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 22000.0,
            "expiry": weekly,
        },
        {
            "instrument_key": "NSE_FO|NIFTY26MAY22000CE",
            "segment": "NSE_FO",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 22000.0,
            "expiry": monthly,
        },
    ]
    lookup = InstrumentLookup(instruments)

    next_inst = lookup.get_next_contract_in_band("NSE_FO|NIFTY26MAY11W22000CE", today)

    assert next_inst is not None
    assert next_inst["instrument_key"] == "NSE_FO|NIFTY26MAY22000CE"


def test_get_next_contract_in_band_falls_back_to_quarterly():
    """When no monthly contract exists at the strike, fall back to the quarterly band."""
    today = date(2026, 5, 10)
    expiring = "2026-05-11"
    quarterly = "2026-06-25"  # same strike, last of June (quarterly month)

    instruments = [
        {
            "instrument_key": "NSE_FO|NIFTY26MAY11W22000CE",
            "segment": "NSE_FO",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 22000.0,
            "expiry": expiring,
        },
        {
            "instrument_key": "NSE_FO|NIFTY26JUN22000CE",
            "segment": "NSE_FO",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 22000.0,
            "expiry": quarterly,
        },
    ]
    lookup = InstrumentLookup(instruments)

    next_inst = lookup.get_next_contract_in_band("NSE_FO|NIFTY26MAY11W22000CE", today)

    assert next_inst is not None
    assert next_inst["instrument_key"] == "NSE_FO|NIFTY26JUN22000CE"


def test_get_next_contract_in_band_no_strike_match_returns_none():
    """No instrument at the required strike in any band -> None (BOD-stale warning path)."""
    today = date(2026, 5, 10)
    instruments = [
        {
            "instrument_key": "NSE_FO|NIFTY26MAY11W22000CE",
            "segment": "NSE_FO",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 22000.0,
            "expiry": "2026-05-11",
        },
        # Monthly band exists, but only at a different strike.
        {
            "instrument_key": "NSE_FO|NIFTY26MAY22200CE",
            "segment": "NSE_FO",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 22200.0,
            "expiry": "2026-05-28",
        },
    ]
    lookup = InstrumentLookup(instruments)

    assert lookup.get_next_contract_in_band("NSE_FO|NIFTY26MAY11W22000CE", today) is None


def test_get_next_contract_in_band_current_not_found():
    """Unknown instrument_key -> None."""
    lookup = InstrumentLookup([])
    assert lookup.get_next_contract_in_band("NSE_FO|INVALID", date(2026, 5, 10)) is None


def test_yearly_december_double_duty_as_quarterly():
    """A December expiry inside the quarterly DTE band (46-200) is
    quarterly's pick AND still yearly's pick, since yearly has no DTE
    floor and always takes the nearest live December. Regression test for
    the 2026-07-22 bug where quarterly's exclusive claim on the date
    starved yearly, forcing a rollover a full year out.
    """
    today = date(2026, 7, 22)
    dec_2026 = "2026-12-29"  # DTE 160 -> inside quarterly's 46-200 band
    jun_2027 = "2027-06-29"  # DTE 342 -> was the old (wrong) yearly pick before this fix

    instruments = [
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": dec_2026,
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": jun_2027,
        },
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)

    labels = dict(candidates)
    assert labels["quarterly"] == dec_2026
    assert labels["yearly"] == dec_2026


def test_yearly_stays_on_near_dated_december_no_floor():
    """yearly does not roll forward just because the nearest live December
    is close (e.g. inside its final quarter) — it stays on that December
    until it actually expires and drops out of the live instrument feed.
    Regression test for the 2026-07-22 over-correction that added an
    artificial DTE floor, which prematurely rolled to a far-dated December
    with too sparse a strike ladder to resolve entry legs against.
    """
    today = date(2026, 12, 1)
    dec_2026 = "2026-12-29"  # DTE ~28, deep inside its final quarter
    dec_2027 = "2027-12-28"  # DTE ~392, must NOT be picked while 2026-12-29 is still live

    instruments = [
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": dec_2026,
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": dec_2027,
        },
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)

    labels = dict(candidates)
    assert labels["yearly"] == dec_2026


def test_yearly_rolls_once_current_december_no_longer_live():
    """Once the current December contract is no longer present in the live
    instrument feed (settled/delisted), yearly naturally picks up the next
    live December with no extra rollover logic needed.
    """
    today = date(2027, 1, 5)
    # dec_2026 deliberately absent — it has settled and dropped off the feed.
    dec_2027 = "2027-12-28"

    instruments = [
        {
            "segment": "NSE_FO",
            "instrument_type": "PE",
            "underlying_symbol": "NIFTY",
            "expiry": dec_2027,
        },
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)

    labels = dict(candidates)
    assert labels["yearly"] == dec_2027


def test_get_next_contract_in_band_rejects_futures():
    """A FUT instrument_key is out of scope for this method -> None."""
    instruments = [
        {
            "instrument_key": "NSE_FO|NIFTY26MAYFUT",
            "segment": "NSE_FO",
            "underlying_symbol": "NIFTY",
            "instrument_type": "FUT",
            "expiry": "2026-05-28",
        },
    ]
    lookup = InstrumentLookup(instruments)
    assert lookup.get_next_contract_in_band("NSE_FO|NIFTY26MAYFUT", date(2026, 5, 10)) is None
