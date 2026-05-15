"""Constants for the backtest module."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA_DIR = _ROOT / "data" / "offline" / "options_ohlcv"
