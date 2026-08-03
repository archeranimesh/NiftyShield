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
 19  test_build_command_omits_default_strategy          default strategy NOT in command
 20  test_build_command_includes_strategy_when_nondefault  non-default strategy IS in command
 21  test_build_command_includes_no_dry_run             --no-dry-run appended
 22  test_build_command_uses_mid_price                  mid=(bid+ask)/2 as --price
 23  test_build_command_falls_back_to_ltp               no bid/ask → ltp as --price
 24  test_build_command_comment_includes_delta_and_iv   comment line has delta= iv=

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

_select_delta_candidates (CC1)
 31  test_cc_ladder_used_for_ce_option_type              CE → CC_DELTA_CANDIDATES
 32  test_csp_ladder_unchanged_for_pe_option_type        PE → DELTA_CANDIDATES (regression guard)
 33  test_selected_strike_respects_requested_delta_range CE auto-select picks from CC ladder, not CSP's

_reorder_cc_round500_first (CC4)
 34  test_round500_preferred_when_present                round-500 candidate moved to front, no fallback reason
 35  test_round500_fallback_to_round100_with_reason       no round-500 in gated set → round-100 first, reason set
 36  test_round500_internal_order_preserved               multiple round-500 rows keep their rank_strikes order
 37  test_round500_empty_input_returns_empty              [] → ([], None)
 38  test_round500_all_round500_no_fallback_reason         every gated row is round-500 → reason is None

_select_delta_candidates (PP1)
 39  test_pp_ladder_used_for_pe_option_type_with_overlay_flag   PE + --overlay-type pp → PP_DELTA_CANDIDATES
 40  test_csp_ladder_unchanged_for_pe_without_overlay_flag       bare PE (CSP's shape) untouched — regression guard
 41  test_pe_without_overlay_flag_does_not_silently_pick_pp_ladder  PE alone must never imply PP
 42  test_cc_overlay_type_is_a_noop_for_ce                        --overlay-type cc doesn't change CE's ladder

_resolve_action (PP1a)
 43  test_resolve_action_defaults_buy_for_pp_strategy            PP + action=None → "BUY"
 44  test_resolve_action_rejects_explicit_sell_for_pp_strategy   PP + action="SELL" → raises ValueError
 45  test_resolve_action_unchanged_for_non_pp_strategies          non-PP strategies keep SELL default / explicit override
 46  test_resolve_action_explicit_buy_for_pp_is_a_noop            PP + action="BUY" → "BUY" (no error)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure project root is on path for direct `pytest` invocations
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.lookup.find_strike_by_delta import (
    CC_DELTA_CANDIDATES,
    DELTA_CANDIDATES,
    PP_DELTA_CANDIDATES,
    _infer_leg,
    _reorder_cc_round500_first,
    _resolve_action,
    _safe_float,
    _select_delta_candidates,
    build_collar_cross_product,
    build_record_command,
    compute_net_collar_premium,
    filter_strikes_by_delta,
    format_collar_table,
    format_table,
    rank_strikes,
    run_collar_mode,
)
from src.paper.constants import STRATEGY_PP_OVERLAY

# ── Fixture loading ───────────────────────────────────────────────────────────

_FIXTURE_PATH = Path("tests/fixtures/responses/option_chain/nifty_chain_2026-04-07.json")


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
        "side",
        "strike",
        "delta",
        "iv",
        "ltp",
        "mid",
        "bid",
        "ask",
        "oi",
        "instrument_key",
    }
    rows = filter_strikes_by_delta(_load_chain(), "CE", 0.10, 0.90)
    for r in rows:
        assert required.issubset(r.keys()), f"Row missing keys: {required - r.keys()}"


def test_filter_instrument_keys_nonempty() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "BOTH", 0.10, 0.90)
    for r in rows:
        assert r["instrument_key"], f"Empty instrument_key at strike {r['strike']} side {r['side']}"


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
    assert "python -m scripts.record.record_paper_trade" in cmd


def test_build_command_contains_instrument_key() -> None:
    cmd = build_record_command(_SAMPLE_ROW, **_CMD_KWARGS)
    assert "NSE_FO|99999" in cmd


def test_build_command_omits_default_strategy() -> None:
    """Default strategy (paper_csp_nifty_v1) is not emitted — it's the record_paper_trade default."""
    cmd = build_record_command(_SAMPLE_ROW, **_CMD_KWARGS)
    assert "--strategy" not in cmd


def test_build_command_includes_strategy_when_nondefault() -> None:
    """Non-default strategy must appear in the generated command."""
    kwargs = {**_CMD_KWARGS, "strategy": "paper_other_v1"}
    cmd = build_record_command(_SAMPLE_ROW, **kwargs)
    assert "--strategy paper_other_v1" in cmd


def test_build_command_includes_no_dry_run() -> None:
    """Generated command always appends --no-dry-run so the paste writes to DB."""
    cmd = build_record_command(_SAMPLE_ROW, **_CMD_KWARGS)
    assert "--no-dry-run" in cmd


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


# ── rank_strikes ──────────────────────────────────────────────────────────────


def test_rank_strikes_empty_returns_empty() -> None:
    assert rank_strikes([]) == []


def test_rank_strikes_adds_rank_field_1_based() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "PE", 0.20, 0.40)
    ranked = rank_strikes(rows)
    assert len(ranked) == len(rows)
    assert ranked[0]["rank"] == 1
    assert ranked[1]["rank"] == 2


def test_rank_strikes_prefers_round_100_strikes() -> None:
    # 22250 PE (non-round) vs 22200 PE (round)
    # Both are in the chain. 22250 has higher OI and tighter spread in fixture,
    # but 22200 is a multiple of 100.
    rows = [
        {
            "strike": 22250.0,
            "bid": 100.0,
            "ask": 101.0,
            "oi": 1000,
            "instrument_key": "K1",
            "delta": -0.45,
        },
        {
            "strike": 22200.0,
            "bid": 100.0,
            "ask": 101.0,
            "oi": 500,
            "instrument_key": "K2",
            "delta": -0.40,
        },
    ]
    ranked = rank_strikes(rows)
    # 22200 (round) should be rank 1 despite lower OI
    assert ranked[0]["strike"] == 22200.0
    assert ranked[1]["strike"] == 22250.0


def test_rank_strikes_prefers_higher_oi() -> None:
    # Both round, both same spread bucket.
    rows = [
        {
            "strike": 22200.0,
            "bid": 100.0,
            "ask": 101.0,
            "oi": 500,
            "instrument_key": "K1",
            "delta": -0.40,
        },
        {
            "strike": 22300.0,
            "bid": 100.0,
            "ask": 101.0,
            "oi": 1000,
            "instrument_key": "K2",
            "delta": -0.42,
        },
    ]
    ranked = rank_strikes(rows)
    # 22300 should be rank 1 due to higher OI
    assert ranked[0]["strike"] == 22300.0
    assert ranked[1]["strike"] == 22200.0


# ── _select_delta_candidates (CC1) ─────────────────────────────────────────────


def test_cc_ladder_used_for_ce_option_type() -> None:
    assert _select_delta_candidates("CE") == CC_DELTA_CANDIDATES


def test_csp_ladder_unchanged_for_pe_option_type() -> None:
    """Regression guard: PE (and BOTH) path is untouched by CC1."""
    assert _select_delta_candidates("PE") == DELTA_CANDIDATES
    assert _select_delta_candidates("BOTH") == DELTA_CANDIDATES


def test_selected_strike_respects_requested_delta_range() -> None:
    """Auto-selecting against the CC ladder finds a strike near CC's target deltas
    (0.18/0.20/0.15), not CSP's (0.22/0.25/0.20) — end-to-end check that main()'s
    ladder switch (via _select_delta_candidates) actually changes which strike wins,
    mirroring the fallback loop in main().
    """
    rows = filter_strikes_by_delta(_load_chain(), "CE", 0.0, 1.0)
    ladder = _select_delta_candidates("CE")
    assert ladder == CC_DELTA_CANDIDATES
    assert ladder != DELTA_CANDIDATES

    selected = None
    for candidate in ladder:
        near = [r for r in rows if abs(abs(r["delta"]) - candidate) <= 0.02]
        if near:
            selected = rank_strikes(near)[0]
            break

    assert selected is not None, "No CE strike found near any CC ladder target delta"
    # Selected strike's delta must be near a CC ladder value, not a CSP-only value like 0.25
    assert any(abs(abs(selected["delta"]) - c) <= 0.02 for c in CC_DELTA_CANDIDATES)


# ── _reorder_cc_round500_first (CC4) ───────────────────────────────────────────


def test_round500_preferred_when_present() -> None:
    """A round-500 candidate is moved to the front even if it ranks lower on OI."""
    gated = [
        {"strike": 24800.0, "oi": 5000, "instrument_key": "K_round100"},
        {"strike": 25000.0, "oi": 1000, "instrument_key": "K_round500"},
    ]
    reordered, reason = _reorder_cc_round500_first(gated)
    assert reordered[0]["instrument_key"] == "K_round500"
    assert reordered[1]["instrument_key"] == "K_round100"
    assert reason is None


def test_round500_fallback_to_round100_with_reason() -> None:
    """No round-500 candidate in the gated set → round-100 order preserved, reason set."""
    gated = [
        {"strike": 24800.0, "oi": 5000, "instrument_key": "K1"},
        {"strike": 24900.0, "oi": 3000, "instrument_key": "K2"},
    ]
    reordered, reason = _reorder_cc_round500_first(gated)
    assert reordered == gated
    assert reason == "no round-500 strike passed the liquidity gate in this delta window"


def test_round500_internal_order_preserved() -> None:
    """Multiple round-500 rows keep their incoming (rank_strikes) relative order."""
    gated = [
        {"strike": 25000.0, "oi": 100, "instrument_key": "K_first"},
        {"strike": 24500.0, "oi": 900, "instrument_key": "K_second"},
        {"strike": 24800.0, "oi": 5000, "instrument_key": "K_round100"},
    ]
    reordered, reason = _reorder_cc_round500_first(gated)
    assert [r["instrument_key"] for r in reordered] == ["K_first", "K_second", "K_round100"]
    assert reason is None


def test_round500_empty_input_returns_empty() -> None:
    assert _reorder_cc_round500_first([]) == ([], None)


def test_round500_all_round500_no_fallback_reason() -> None:
    """Every gated row is round-500 → no round-100 tier at all, reason still None."""
    gated = [
        {"strike": 25000.0, "oi": 1000, "instrument_key": "K1"},
        {"strike": 24500.0, "oi": 500, "instrument_key": "K2"},
    ]
    reordered, reason = _reorder_cc_round500_first(gated)
    assert len(reordered) == 2
    assert reason is None


# ── _select_delta_candidates (PP1) ─────────────────────────────────────────────


def test_pp_ladder_used_for_pe_option_type_with_overlay_flag() -> None:
    assert _select_delta_candidates("PE", overlay_type="pp") == PP_DELTA_CANDIDATES


def test_csp_ladder_unchanged_for_pe_without_overlay_flag() -> None:
    """Regression guard: bare --option-type PE (CSP's existing invocation shape) is untouched."""
    assert _select_delta_candidates("PE") == DELTA_CANDIDATES
    assert _select_delta_candidates("PE", overlay_type=None) == DELTA_CANDIDATES


def test_pe_without_overlay_flag_does_not_silently_pick_pp_ladder() -> None:
    """Explicit guard against the ambiguity PP1 exists to resolve: PE alone must never
    imply PP, only the explicit --overlay-type pp opt-in does.
    """
    assert _select_delta_candidates("PE") != PP_DELTA_CANDIDATES
    assert _select_delta_candidates("PE", overlay_type="cc") == DELTA_CANDIDATES


# ── _resolve_action (PP1a) ──────────────────────────────────────────────────────


def test_resolve_action_defaults_buy_for_pp_strategy() -> None:
    assert _resolve_action(STRATEGY_PP_OVERLAY, None) == "BUY"


def test_resolve_action_rejects_explicit_sell_for_pp_strategy() -> None:
    with pytest.raises(ValueError, match="SELL"):
        _resolve_action(STRATEGY_PP_OVERLAY, "SELL")


def test_resolve_action_unchanged_for_non_pp_strategies() -> None:
    """Regression guard: non-PP strategies keep the existing SELL default when
    action=None, and still accept an explicit BUY/SELL override.
    """
    assert _resolve_action("paper_csp_nifty_v1", None) == "SELL"
    assert _resolve_action("paper_csp_nifty_v1", "SELL") == "SELL"
    assert _resolve_action("paper_csp_nifty_v1", "BUY") == "BUY"
    assert _resolve_action("paper_nifty_overlay", None) == "SELL"


def test_resolve_action_explicit_buy_for_pp_is_a_noop() -> None:
    assert _resolve_action(STRATEGY_PP_OVERLAY, "BUY") == "BUY"


# ── Collar1: two-leg delta-targeted collar search ──────────────────────────────

_CALL_ROW: dict = {
    "side": "CE",
    "strike": 22600.0,
    "delta": 0.18,
    "iv": 12.0,
    "ltp": 40.0,
    "mid": 42.0,
    "bid": 41.0,
    "ask": 43.0,
    "oi": 50000,
    "instrument_key": "NSE_FO|CALL1",
}

_PUT_ROW: dict = {
    "side": "PE",
    "strike": 21900.0,
    "delta": -0.20,
    "iv": 15.0,
    "ltp": 55.0,
    "mid": 50.0,
    "bid": 49.0,
    "ask": 51.0,
    "oi": 60000,
    "instrument_key": "NSE_FO|PUT1",
}


def test_net_collar_premium_computed_correctly() -> None:
    # call credit 42.0 - put debit 50.0 = -8.0 (net debit)
    assert compute_net_collar_premium(_CALL_ROW, _PUT_ROW) == -8.0
    # net-credit case: call mid raised above put mid
    rich_call = {**_CALL_ROW, "mid": 60.0}
    assert compute_net_collar_premium(rich_call, _PUT_ROW) == 10.0


def test_collar_mode_runs_both_ce_and_pe_searches(monkeypatch: pytest.MonkeyPatch) -> None:
    """--overlay-type collar invokes both the CC ladder and the PP ladder, not just one."""
    seen_option_types: list[str] = []

    def fake_find_candidates(raw_data_by_expiry, expiries, option_type, ladder):
        seen_option_types.append(option_type)
        return [_CALL_ROW] if option_type == "CE" else [_PUT_ROW]

    import scripts.lookup.find_strike_by_delta as mod

    monkeypatch.setattr(mod, "_find_candidates_for_ladder", fake_find_candidates)
    combos = run_collar_mode({"2026-05-29": _load_chain()}, [("monthly", "2026-05-29")])
    assert set(seen_option_types) == {"CE", "PE"}
    assert len(combos) == 1
    assert combos[0]["call"] == _CALL_ROW
    assert combos[0]["put"] == _PUT_ROW


def test_collar_mode_does_not_auto_select_a_single_combo() -> None:
    """Cross-product reports every pairing — regression guard against inventing a
    third auto-select heuristic no one asked for."""
    call_candidates = [{**_CALL_ROW, "target_delta": 0.18}, {**_CALL_ROW, "target_delta": 0.20}]
    put_candidates = [{**_PUT_ROW, "target_delta": 0.20}, {**_PUT_ROW, "target_delta": 0.25}]
    combos = build_collar_cross_product(call_candidates, put_candidates)
    assert len(combos) == 4  # full 2x2 cross-product, no single pick
    table = format_collar_table(combos)
    assert table.count("NET PREMIUM") == 1  # header appears once, not per-row
    # header + separator + one row per combo
    assert len(table.splitlines()) == 2 + len(combos)


def test_collar_mode_requires_cc1_pp1_ladders_present() -> None:
    """Collar mode raises a clear error if either ladder is missing/empty — guards
    the hard CC1/PP1 dependency rather than silently running one-sided."""
    with pytest.raises(RuntimeError, match="CC1"):
        run_collar_mode({}, [], cc_ladder=[], pp_ladder=PP_DELTA_CANDIDATES)
    with pytest.raises(RuntimeError, match="PP1"):
        run_collar_mode({}, [], cc_ladder=CC_DELTA_CANDIDATES, pp_ladder=[])


def test_cc_overlay_type_is_a_noop_for_ce() -> None:
    """--overlay-type cc is a no-op — --option-type CE already resolves to the CC ladder
    on its own, so passing the flag must not change the outcome.
    """
    assert _select_delta_candidates("CE", overlay_type="cc") == CC_DELTA_CANDIDATES
    assert _select_delta_candidates("CE", overlay_type="cc") == _select_delta_candidates("CE")
