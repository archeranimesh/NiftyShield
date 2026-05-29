# src/paper/_utils.py
from typing import Any


def safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert a value to float.
    
    Returns:
        float: The converted value if successful, else `default`.
        - Numeric strings and numbers are converted.
        - None or non-numeric strings return `default`.
    """
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
