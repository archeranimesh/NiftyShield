# tests/unit/paper/test_utils.py
from src.paper._utils import safe_float

def test_safe_float_numeric_string():
    assert safe_float("123.45") == 123.45

def test_safe_float_float():
    assert safe_float(123.45) == 123.45

def test_safe_float_none():
    assert safe_float(None) == 0.0
    assert safe_float(None, default=1.0) == 1.0

def test_safe_float_invalid_string():
    assert safe_float("abc") == 0.0
    assert safe_float("abc", default=-1.0) == -1.0

def test_safe_float_empty_string():
    assert safe_float("") == 0.0
