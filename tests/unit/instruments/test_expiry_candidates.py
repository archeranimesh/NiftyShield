import pytest
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
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": m_exp},
        {"segment": "NSE_FO", "instrument_type": "CE", "underlying_symbol": "NIFTY", "expiry": q_exp},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": y_exp},
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)
    
    assert candidates == [
        ("monthly", m_exp),
        ("quarterly", q_exp),
        ("yearly", y_exp)
    ]

def test_expiry_candidates_dte_gate():
    """Expiries with DTE < 15 are excluded."""
    today = date(2026, 5, 10)
    too_close = (today + timedelta(days=14)).isoformat()
    just_right = (today + timedelta(days=15)).isoformat()
    
    instruments = [
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": too_close},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": just_right},
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)
    
    assert len(candidates) == 1
    assert candidates[0] == ("monthly", just_right)

def test_expiry_candidates_dte_boundary():
    """DTE=45 is monthly, DTE=46 is quarterly."""
    # Reference date: April 16, 2026.
    # dte45 = May 31, 2026 (DTE 45). Only May expiry, so is_monthly is True.
    # dte46 = June 1, 2026 (DTE 46). Only June expiry, so is_monthly/is_quarterly is True.
    today = date(2026, 4, 16)
    dte45 = "2026-05-31"
    dte46 = "2026-06-01"
    
    instruments = [
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": dte45},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": dte46},
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)
    
    # In default order: monthly, quarterly
    assert candidates == [
        ("monthly", dte45),
        ("quarterly", dte46)
    ]

def test_expiry_candidates_missing_category():
    """Missing category (e.g. quarterly) does not crash and returns others."""
    today = date(2026, 5, 10)
    m_exp = "2026-05-28"
    y_exp = "2026-12-31"
    
    instruments = [
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": m_exp},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": y_exp},
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)
    
    assert candidates == [
        ("monthly", m_exp),
        ("yearly", y_exp)
    ]

def test_expiry_candidates_custom_preference():
    """Custom preference order is respected."""
    today = date(2026, 5, 10)
    m_exp = "2026-05-28"
    q_exp = "2026-06-25"
    y_exp = "2026-12-31"
    
    instruments = [
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": m_exp},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": q_exp},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": y_exp},
    ]
    lookup = InstrumentLookup(instruments)
    
    # Test 3-track style preference: quarterly -> yearly -> monthly
    pref = ["quarterly", "yearly", "monthly"]
    candidates = lookup.get_expiry_candidates("NIFTY", today, preference=pref)
    
    assert candidates == [
        ("quarterly", q_exp),
        ("yearly", y_exp),
        ("monthly", m_exp)
    ]

def test_expiry_candidates_no_network_mock_bod():
    """Verify it uses provided instruments and no network calls (implicitly tested by no mock)."""
    today = date(2026, 5, 10)
    # Different underlying should be ignored
    instruments = [
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "BANKNIFTY", "expiry": "2026-05-28"},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": "2026-05-28"},
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)
    
    assert len(candidates) == 1
    assert candidates[0] == ("monthly", "2026-05-28")

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
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": "2026-05-14"},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": "2026-05-21"},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": "2026-05-28"},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": "2026-06-04"},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": "2026-06-11"},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": "2026-06-18"},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": "2026-06-25"},
    ]
    
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)
    
    # Even though 2026-06-04, 06-11, 06-18 have 15 <= DTE <= 45, they are weekly contracts
    # and should NOT be selected as the monthly candidate.
    # Instead, 2026-05-28 (DTE 18, last of May) is the monthly candidate.
    # 2026-06-25 (DTE 46, last of June) is the quarterly candidate.
    assert candidates == [
        ("monthly", "2026-05-28"),
        ("quarterly", "2026-06-25")
    ]
