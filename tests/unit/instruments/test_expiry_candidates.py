import pytest
from datetime import date, timedelta
from src.instruments.lookup import InstrumentLookup

def test_expiry_candidates_happy_path():
    """BOD with monthly + quarterly + yearly returns all in correct CSP order."""
    today = date(2026, 5, 10)
    # monthly: 15-45 (2026-05-25 to 2026-06-24)
    # quarterly: 46-200 (2026-06-25 to 2026-11-26)
    # yearly: 201-420 (2026-11-27 to 2027-07-04)
    
    m_exp = (today + timedelta(days=30)).isoformat()
    q_exp = (today + timedelta(days=60)).isoformat()
    y_exp = (today + timedelta(days=250)).isoformat()
    
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
    today = date(2026, 5, 10)
    dte45 = (today + timedelta(days=45)).isoformat()
    dte46 = (today + timedelta(days=46)).isoformat()
    
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
    m_exp = (today + timedelta(days=30)).isoformat()
    y_exp = (today + timedelta(days=250)).isoformat()
    
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
    m_exp = (today + timedelta(days=30)).isoformat()
    q_exp = (today + timedelta(days=60)).isoformat()
    y_exp = (today + timedelta(days=250)).isoformat()
    
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
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "BANKNIFTY", "expiry": (today + timedelta(days=30)).isoformat()},
        {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY", "expiry": (today + timedelta(days=30)).isoformat()},
    ]
    lookup = InstrumentLookup(instruments)
    candidates = lookup.get_expiry_candidates("NIFTY", today)
    
    assert len(candidates) == 1
    assert candidates[0][1] == (today + timedelta(days=30)).isoformat()
