"""Offline unit tests for scripts/find_strike_by_delta.py.

All tests use the existing nifty_chain_2026-04-07.json fixture — no network calls.
Fixture characteristics:
  - 129 strikes, underlying_spot=22266.25, expiry=2026-04-07
  - ATM 22250 CE: delta=0.525, iv=27.4
  - ATM 22250 PE: delta=-0.4755, iv=28.68

Test table
----------
filter_strikes_by_delta
  1  test_filter_ce_delta_range_returns_nonempty        CE [0.20,0.40] → non-empty
  2  test_filter_pe_delta_range_returns_nonempty        PE [0.20,0.40] → non-empty
  3  test_filter_ce_all_deltas_within_range             every CE row: |delta| in range
  4  test_filter_pe_all_deltas_within_range             every PE row: |delta| in range
  5  test_filter_ce_all_sides_are_ce                    BOTH filtered to CE only
  6  test_filter_pe_all_sides_are_pe                    BOTH filtered to PE only
  7  test_filter_both_returns_ce_and_pe                 BOTH → CE and PE present
  8  test_filter_sorted_by_abs_delta_descending         rows ordered by |delta| desc
  9  test_filter_empty_chain_returns_empty              [] → []
 10  test_filter_no_match_returns_empty                 impossible range → []
 11  test_filter_row_has_required_fields                each row has all 10 keys
 12  test_filter_instrument_keys_nonempty               no blank instrument_key

format_table
 13  test_format_table_contains_header_columns          SIDE/STRIKE/DELTA/IV%/KEY present
 14  test_format_table_empty_rows_returns_message       [] → "No strikes found"
 15  test_format_table_includes_spot_and_expiry         spot + expiry in header
 16  test_format_table_ce_rows_show_plus_delta          CE delta has leading "+"

build_record_command
 17  test_build_command_starts_with_record_paper_trade  command prefix correct
 18  test_build_command_contains_instrument_key         key in command
 19  test_build_command_contains_strategy               strategy name in command
 20  test_build_command_uses_mid_price                  mid=(bid+ask)/2 as --price
 21  test_build_command_falls_back_to_ltp               no bid/ask → ltp as --price
 22  test_build_command_comment_includes_delta_and_iv   comment line has delta= iv=

_infer_leg
 23  test_infer_leg_pe_sell                             PE+SELL → "short_put"
 24  test_infer_leg_ce_sell                             CE+SELL → "short_call"
 25  test_infer_leg_pe_buy                              PE+BUY  → "long_put"
 26  test_infer_leg_ce_buy                              CE+BUY  → "long_call"
 27  test_infer_leg_unknown_returns_generic             XX+SELL → "leg"

_safe_float
 28  test_safe_float_none_returns_default               None → 0.0
 29  test_safe_float_valid_string                       "3.14" → 3.14
 30  test_safe_float_invalid_returns_custom_default     "N/A" → custom default
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure project root is on path for direct `pytest` invocations
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.find_strike_by_delta import (
    _infer_leg,
    _safe_float,
    build_record_command,
    filter_strikes_by_delta,
    format_table,
)

# ── Fixture loading ───────────────────────────────────────────────────────────

_FIXTURE_PATH = Path(
    "tests/fixtures/responses/option_chain/nifty_chain_2026-04-07.json"
)


def _load_chain() -> list[dict]:
    """Load the raw strikes list from the recorded Upstox fixture."""
    with _FIXTURE_PATH.open() as fh:
        return json.load(fh)["response"]["data"]


# ── filter_strikes_by_delta ───────────────────────────────────────────────────


def test_filter_ce_delta_range_returns_nonempty() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "CE", 0.20, 0.40)
    assert len(rows) > 0


def test_filter_pe_delta_range_returns_nonempty() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "PE", 0.20, 0.40)
    assert len(rows) > 0


def test_filter_ce_all_deltas_within_range() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "CE", 0.20, 0.40)
    for r in rows:
        assert 0.20 <= abs(r["delta"]) <= 0.40, (
            f"CE strike {r['strike']}: delta={r['delta']} outside [0.20, 0.40]"
        )


def test_filter_pe_all_deltas_within_range() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "PE", 0.20, 0.40)
    for r in rows:
        assert 0.20 <= abs(r["delta"]) <= 0.40, (
            f"PE strike {r['strike']}: delta={r['delta']} outside [0.20, 0.40]"
        )


def test_filter_ce_all_sides_are_ce() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "CE", 0.10, 0.90)
    assert all(r["side"] == "CE" for r in rows)


def test_filter_pe_all_sides_are_pe() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "PE", 0.10, 0.90)
    assert all(r["side"] == "PE" for r in rows)


def test_filter_both_returns_ce_and_pe() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "BOTH", 0.20, 0.40)
    sides = {r["side"] for r in rows}
    assert "CE" in sides
    assert "PE" in sides


def test_filter_sorted_by_abs_delta_descending() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "BOTH", 0.10, 0.90)
    abs_deltas = [abs(r["delta"]) for r in rows]
    assert abs_deltas == sorted(abs_deltas, reverse=True)


def test_filter_empty_chain_returns_empty() -> None:
    assert filter_strikes_by_delta([], "BOTH", 0.20, 0.40) == []


def test_filter_no_match_returns_empty() -> None:
    # Vanilla delta is bounded by [-1, 1]; [1.01, 1.50] is mathematically impossible
    rows = filter_strikes_by_delta(_load_chain(), "BOTH", 1.01, 1.50)
    assert rows == []


def test_filter_row_has_required_fields() -> None:
    required = {
        "side", "strike", "delta", "iv", "ltp", "mid",
        "bid", "ask", "oi", "instrument_key",
    }
    rows = filter_strikes_by_delta(_load_chain(), "CE", 0.10, 0.90)
    for r in rows:
        assert required.issubset(r.keys()), (
            f"Row missing keys: {required - r.keys()}"
        )


def test_filter_instrument_keys_nonempty() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "BOTH", 0.10, 0.90)
    for r in rows:
        assert r["instrument_key"], (
            f"Empty instrument_key at strike {r['strike']} side {r['side']}"
        )


# ── format_table ──────────────────────────────────────────────────────────────


def test_format_table_contains_header_columns() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "CE", 0.20, 0.40)
    table = format_table(rows)
    for col in ("SIDE", "STRIKE", "DELTA", "IV%", "LTP", "KEY"):
        assert col in table, f"Column '{col}' missing from table"


def test_format_table_empty_rows_returns_message() -> None:
    result = format_table([])
    assert "No strikes found" in result


def test_format_table_includes_spot_and_expiry() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "CE", 0.20, 0.40)
    table = format_table(rows, underlying_spot=22266.25, expiry="2026-04-07")
    assert "22,266.25" in table
    assert "2026-04-07" in table


def test_format_table_ce_rows_show_plus_delta() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "CE", 0.20, 0.40)
    table = format_table(rows)
    # CE deltas are positive; the formatter prefixes them with "+"
    assert "+" in table


# ── build_record_command ──────────────────────────────────────────────────────

_SAMPLE_ROW: dict = {
    "side": "PE",
    "strike": 22000.0,
    "delta": -0.2512,
    "iv": 14.32,
    "ltp": 88.50,
    "mid": 88.25,
    "bid": 88.00,
    "ask": 88.50,
    "oi": 124500,
    "instrument_key": "NSE_FO|99999",
}

_CMD_KWARGS: dict = dict(
    strategy="paper_csp_nifty_v1",
    leg="short_put",
    action="SELL",
    qty=75,
    trade_date="2026-05-03",
)


def test_build_command_starts_with_record_paper_trade() -> None:
    cmd = build_record_command(_SAMPLE_ROW, **_CMD_KWARGS)
    assert "python scripts/record_paper_trade.py" in cmd


def test_build_command_contains_instrument_key() -> None:
    cmd = build_record_command(_SAMPLE_ROW, **_CMD_KWARGS)
    assert "NSE_FO|99999" in cmd


def test_build_command_contains_strategy() -> None:
    cmd = build_record_command(_SAMPLE_ROW, **_CMD_KWARGS)
    assert "paper_csp_nifty_v1" in cmd


def test_build_command_uses_mid_price() -> None:
    # mid=88.25, bid=88.00, ask=88.50 → (88.00+88.50)/2 = 88.25
    cmd = build_record_command(_SAMPLE_ROW, **_CMD_KWARGS)
    assert "--price 88.25" in cmd


def test_build_command_falls_back_to_ltp() -> None:
    row = {**_SAMPLE_ROW, "bid": 0.0, "ask": 0.0, "mid": 0.0}
    cmd = build_record_command(row, **_CMD_KWARGS)
    # ltp=88.50; round(88.50, 2) = 88.5 as float → f"{88.5}" = "88.5"
    assert "--price 88.5" in cmd or "--price 88.50" in cmd


def test_build_command_comment_includes_delta_and_iv() -> None:
    cmd = build_record_command(_SAMPLE_ROW, **_CMD_KWARGS)
    assert "delta=" in cmd
    assert "iv=" in cmd


# ── _infer_leg ────────────────────────────────────────────────────────────────


def test_infer_leg_pe_sell() -> None:
    assert _infer_leg("PE", "SELL") == "short_put"


def test_infer_leg_ce_sell() -> None:
    assert _infer_leg("CE", "SELL") == "short_call"


def test_infer_leg_pe_buy() -> None:
    assert _infer_leg("PE", "BUY") == "long_put"


def test_infer_leg_ce_buy() -> None:
    assert _infer_leg("CE", "BUY") == "long_call"


def test_infer_leg_unknown_returns_generic() -> None:
    assert _infer_leg("XX", "SELL") == "leg"


# ── _safe_float ───────────────────────────────────────────────────────────────


def test_safe_float_none_returns_default() -> None:
    assert _safe_float(None) == 0.0


def test_safe_float_valid_string() -> None:
    assert _safe_float("3.14") == pytest.approx(3.14)


def test_safe_float_invalid_returns_custom_default() -> None:
    assert _safe_float("N/A", default=-1.0) == -1.0
