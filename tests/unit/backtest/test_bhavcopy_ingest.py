import pytest
from datetime import date
from decimal import Decimal
import zipfile
import tempfile
from pathlib import Path
from src.backtest.bhavcopy_ingest import parse_option_symbol, parse_bhavcopy, BhavRecord

def test_parse_option_symbol_monthly():
    res = parse_option_symbol("NIFTY26APR24000PE")
    assert res["strike"] == Decimal("24000")
    assert res["option_type"] == "PE"

def test_parse_option_symbol_zero_padded():
    res = parse_option_symbol("NIFTY26APR08000CE")
    assert res["strike"] == Decimal("8000")
    assert res["option_type"] == "CE"

def test_parse_option_symbol_weekly():
    res = parse_option_symbol("NIFTY2641724000PE")
    assert res["strike"] == Decimal("24000")
    assert res["option_type"] == "PE"
    assert res["expiry"] == date(2026, 4, 17)

def test_parse_option_symbol_unknown_raises():
    with pytest.raises(ValueError):
        parse_option_symbol("NIFTYGARBAGE")

@pytest.fixture
def bhavcopy_zip(tmp_path):
    csv_path = Path("tests/fixtures/responses/bhavcopy/synthetic_bhavcopy.csv")
    zip_path = tmp_path / "bhavcopy.csv.zip"
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.write(csv_path, arcname="bhavcopy.csv")
    return zip_path

def test_parse_bhavcopy_filters_to_nifty(bhavcopy_zip):
    records = parse_bhavcopy(bhavcopy_zip, underlying="NIFTY")
    
    # 1 OPTIDX CE, 1 OPTIDX PE, 1 FUTIDX. 
    # Missing: BANKNIFTY, RELIANCE, corrupted CE strike 0.
    assert len(records) == 3
    for r in records:
        assert r.underlying == "NIFTY"
        assert r.instrument in ("OPTIDX", "FUTIDX")

def test_parse_bhavcopy_decimal_fields(bhavcopy_zip):
    records = parse_bhavcopy(bhavcopy_zip, underlying="NIFTY")
    for r in records:
        assert isinstance(r.open, Decimal)
        assert isinstance(r.high, Decimal)
        assert isinstance(r.low, Decimal)
        assert isinstance(r.close, Decimal)
        assert isinstance(r.settle_price, Decimal)

def test_parse_bhavcopy_empty_on_no_match(bhavcopy_zip):
    records = parse_bhavcopy(bhavcopy_zip, underlying="SENSEX")
    assert len(records) == 0

def test_parse_bhavcopy_corrupt_zip(tmp_path):
    corrupt_zip = tmp_path / "corrupt.zip"
    corrupt_zip.write_bytes(b"not a zip file")
    with pytest.raises(zipfile.BadZipFile):
        parse_bhavcopy(corrupt_zip)
