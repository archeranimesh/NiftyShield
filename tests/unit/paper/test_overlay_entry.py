"""Tests for paper_3track_overlay_entry and find_overlay_strikes pure functions."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from scripts.lookup.find_overlay_strikes import (
    compute_target_strike,
    evaluate_expiry,
    find_chain_entry,
)
from scripts.strategies.three_track.paper_3track_overlay_entry import (
    _NIFTY_LOT_SIZE_FALLBACK,
    OverlayConfig,
    _alert_bootstrap_failure,
    _resolve_lot_size,
    build_overlay_trades,
    load_overlay_config,
)
from src.models.portfolio import TradeAction

# ── helpers ────────────────────────────────────────────────────────────────────


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "overlay_entry.yaml"
    p.write_text(yaml.dump(data))
    return p


def _valid_pp_raw() -> dict:
    return {
        "overlay": {
            "type": "pp",
            "date": "2026-05-07",
            "cycle": 1,
            "lot_size": 65,
            "expiry": "2026-06-26",
            "expiry_type": "quarterly",
            "dte_at_entry": 50,
            "put_strike": 21800.0,
            "put_instrument_key": "NSE_FO|NIFTY21800PE26JUN2026",
            "put_price": 285.50,
            "put_spread_pct": 1.8,
            "put_oi": 12500,
            "call_strike": 0,
            "call_instrument_key": "",
            "call_price": 0.0,
            "call_spread_pct": None,
            "call_oi": 0,
        }
    }


def _valid_cc_raw() -> dict:
    raw = _valid_pp_raw()
    raw["overlay"]["type"] = "cc"
    raw["overlay"]["call_strike"] = 25000.0
    raw["overlay"]["call_instrument_key"] = "NSE_FO|NIFTY25000CE26JUN2026"
    raw["overlay"]["call_price"] = 210.00
    raw["overlay"]["call_spread_pct"] = 2.1
    raw["overlay"]["call_oi"] = 8900
    return raw


def _valid_collar_raw() -> dict:
    raw = _valid_cc_raw()
    raw["overlay"]["type"] = "collar"
    raw["overlay"]["put_strike"] = 21800.0
    raw["overlay"]["put_instrument_key"] = "NSE_FO|NIFTY21800PE26JUN2026"
    raw["overlay"]["put_price"] = 285.50
    raw["overlay"]["put_spread_pct"] = 1.8
    raw["overlay"]["put_oi"] = 12500
    return raw


def _make_overlay_config(**overrides) -> OverlayConfig:
    base = dict(
        overlay_type="pp",
        entry_date=date(2026, 5, 7),
        cycle=1,
        lot_size=65,
        expiry="2026-06-26",
        expiry_type="quarterly",
        dte_at_entry=50,
        put_strike=21800.0,
        put_instrument_key="NSE_FO|NIFTY21800PE26JUN2026",
        put_price=Decimal("285.50"),
        put_spread_pct=1.8,
        put_oi=12500,
        call_strike=25000.0,
        call_instrument_key="NSE_FO|NIFTY25000CE26JUN2026",
        call_price=Decimal("210.00"),
        call_spread_pct=2.1,
        call_oi=8900,
    )
    base.update(overrides)
    return OverlayConfig(**base)


# ── compute_target_strike ──────────────────────────────────────────────────────


def test_compute_target_strike_put_rounds_to_nearest_50():
    # 24000 × (1 - 0.09) = 21840 → nearest 50 = 21850
    result = compute_target_strike(24000.0, 9.0, "PE")
    assert result == 21850.0


def test_compute_target_strike_call_rounds_to_nearest_50():
    # 24000 × (1 + 0.04) = 24960 → nearest 50 = 24950
    result = compute_target_strike(24000.0, 4.0, "CE")
    assert result == 24950.0


def test_compute_target_strike_put_exact():
    # 20000 × 0.90 = 18000 → exactly 18000
    result = compute_target_strike(20000.0, 10.0, "PE")
    assert result == 18000.0


# ── find_chain_entry ──────────────────────────────────────────────────────────


def _make_chain(strike: float, side: str, bid: float, ask: float, oi: int = 1000) -> list[dict]:
    raw_key = "call_options" if side == "CE" else "put_options"
    return [
        {
            "strike_price": strike,
            raw_key: {
                "instrument_key": f"NSE_FO|TEST{strike:.0f}{side}",
                "market_data": {
                    "ltp": (bid + ask) / 2,
                    "bid_price": bid,
                    "ask_price": ask,
                    "oi": oi,
                },
                "option_greeks": {"delta": 0.3, "iv": 15.0},
            },
        }
    ]


def test_find_chain_entry_returns_closest_strike():
    chain = _make_chain(21800.0, "PE", 280.0, 290.0) + _make_chain(22000.0, "PE", 200.0, 210.0)
    result = find_chain_entry(chain, "PE", 21850.0)  # closer to 21800
    assert result is not None
    assert result["strike"] == 21800.0
    assert result["instrument_key"] == "NSE_FO|TEST21800PE"


def test_find_chain_entry_computes_spread_pct():
    chain = _make_chain(21800.0, "PE", 285.0, 290.0)  # spread=5, mid=287.5
    result = find_chain_entry(chain, "PE", 21800.0)
    assert result is not None
    expected_spread = round(5.0 / 287.5 * 100, 2)
    assert result["spread_pct"] == pytest.approx(expected_spread, rel=1e-3)


def test_find_chain_entry_no_instrument_key_skipped():
    chain = [{"strike_price": 21800.0, "put_options": {"market_data": {}, "option_greeks": {}}}]
    result = find_chain_entry(chain, "PE", 21800.0)
    assert result is None


def test_find_chain_entry_computes_mid():
    chain = _make_chain(25000.0, "CE", 200.0, 220.0)
    result = find_chain_entry(chain, "CE", 25000.0)
    assert result["mid"] == pytest.approx(210.0)


# ── evaluate_expiry ───────────────────────────────────────────────────────────


def test_evaluate_expiry_passes_gate():
    chain = _make_chain(21800.0, "PE", 285.0, 287.0)  # spread~0.7% → passes
    ev = evaluate_expiry(chain, "2026-06-26", "pp", 21800.0, 25000.0, date(2026, 5, 7))
    assert ev.passes_gate is True
    assert ev.dte == (date(2026, 6, 26) - date(2026, 5, 7)).days


def test_evaluate_expiry_fails_gate():
    chain = _make_chain(21800.0, "PE", 270.0, 300.0)  # spread~10.5% → fails
    ev = evaluate_expiry(chain, "2026-05-29", "pp", 21800.0, 25000.0, date(2026, 5, 7))
    assert ev.passes_gate is False


def test_evaluate_expiry_collar_uses_max_spread():
    # Put spread=1%, Call spread=4% → max=4% → fails gate
    put_chain = _make_chain(21800.0, "PE", 286.0, 289.0)  # spread~1%
    call_chain = _make_chain(25000.0, "CE", 200.0, 209.0)  # spread~4.4%
    chain = put_chain + call_chain
    ev = evaluate_expiry(chain, "2026-06-26", "collar", 21800.0, 25000.0, date(2026, 5, 7))
    assert ev.passes_gate is False
    assert ev.gate_spread == pytest.approx(max(ev.put["spread_pct"], ev.call["spread_pct"]))


def test_evaluate_expiry_collar_passes_when_both_legs_tight():
    put_chain = _make_chain(21800.0, "PE", 286.0, 289.0)  # spread~1%
    call_chain = _make_chain(25000.0, "CE", 205.0, 208.0)  # spread~1.5%
    chain = put_chain + call_chain
    ev = evaluate_expiry(chain, "2026-06-26", "collar", 21800.0, 25000.0, date(2026, 5, 7))
    assert ev.passes_gate is True


# ── load_overlay_config ───────────────────────────────────────────────────────


def test_load_overlay_config_pp_happy_path(tmp_path):
    path = _write_yaml(tmp_path, _valid_pp_raw())
    cfg = load_overlay_config(path)
    assert cfg.overlay_type == "pp"
    assert cfg.entry_date == date(2026, 5, 7)
    assert cfg.put_price == Decimal("285.5")
    assert cfg.put_instrument_key == "NSE_FO|NIFTY21800PE26JUN2026"
    assert cfg.cycle == 1


def test_load_overlay_config_collar_happy_path(tmp_path):
    path = _write_yaml(tmp_path, _valid_collar_raw())
    cfg = load_overlay_config(path)
    assert cfg.overlay_type == "collar"
    assert cfg.call_price == Decimal("210.0")
    assert cfg.call_instrument_key == "NSE_FO|NIFTY25000CE26JUN2026"


def test_load_overlay_config_invalid_type_raises(tmp_path):
    raw = _valid_pp_raw()
    raw["overlay"]["type"] = "straddle"
    path = _write_yaml(tmp_path, raw)
    with pytest.raises(ValueError, match="pp.*cc.*collar"):
        load_overlay_config(path)


def test_load_overlay_config_pp_zero_put_price_raises(tmp_path):
    raw = _valid_pp_raw()
    raw["overlay"]["put_price"] = 0.0
    path = _write_yaml(tmp_path, raw)
    with pytest.raises(ValueError, match="put_price"):
        load_overlay_config(path)


def test_load_overlay_config_cc_bad_call_key_raises(tmp_path):
    raw = _valid_cc_raw()
    raw["overlay"]["call_instrument_key"] = "INVALID|KEY"
    path = _write_yaml(tmp_path, raw)
    with pytest.raises(ValueError, match="NSE_FO"):
        load_overlay_config(path)


# ── build_overlay_trades ──────────────────────────────────────────────────────


def test_build_overlay_trades_pp_records_single_overlay_namespace():
    """Overlay legs are track-independent (S1r) — one leg, not one per track."""
    cfg = _make_overlay_config(overlay_type="pp")
    trades, warnings = build_overlay_trades(cfg)
    strategies = {ot.strategy for ot in trades}
    assert strategies == {"paper_nifty_overlay"}
    assert len(trades) == 1
    assert len(warnings) == 0


def test_build_overlay_trades_pp_all_buy():
    cfg = _make_overlay_config(overlay_type="pp")
    trades, _ = build_overlay_trades(cfg)
    assert all(ot.trade.action == TradeAction.BUY for ot in trades)


def test_build_overlay_trades_pp_leg_role():
    cfg = _make_overlay_config(overlay_type="pp")
    trades, _ = build_overlay_trades(cfg)
    assert all(ot.leg_role == "overlay_pp" for ot in trades)


def test_build_overlay_trades_cc_single_overlay_namespace():
    """Futures+standalone-CC block was track-ownership logic (S2r retired it) —
    overlay is track-independent, so there's no track to block anymore."""
    cfg = _make_overlay_config(overlay_type="cc")
    trades, warnings = build_overlay_trades(cfg)
    strategies = {ot.strategy for ot in trades}
    assert strategies == {"paper_nifty_overlay"}
    assert len(trades) == 1
    assert len(warnings) == 0


def test_build_overlay_trades_cc_is_sell():
    cfg = _make_overlay_config(overlay_type="cc")
    trades, _ = build_overlay_trades(cfg)
    assert all(ot.trade.action == TradeAction.SELL for ot in trades)


def test_build_overlay_trades_collar_records_two_legs():
    cfg = _make_overlay_config(overlay_type="collar")
    trades, warnings = build_overlay_trades(cfg)
    # Single overlay namespace × 2 legs (put + call) = 2, not 3 tracks × 2 = 6
    assert len(trades) == 2
    assert len(warnings) == 0


def test_build_overlay_trades_collar_single_overlay_namespace():
    cfg = _make_overlay_config(overlay_type="collar")
    trades, _ = build_overlay_trades(cfg)
    strategies = {ot.strategy for ot in trades}
    assert strategies == {"paper_nifty_overlay"}


def test_build_overlay_trades_collar_leg_roles():
    cfg = _make_overlay_config(overlay_type="collar")
    trades, _ = build_overlay_trades(cfg)
    roles = {ot.leg_role for ot in trades}
    assert roles == {"overlay_collar_put", "overlay_collar_call"}


def test_build_overlay_trades_collar_put_is_buy_call_is_sell():
    cfg = _make_overlay_config(overlay_type="collar")
    trades, _ = build_overlay_trades(cfg)
    for ot in trades:
        if ot.leg_role == "overlay_collar_put":
            assert ot.trade.action == TradeAction.BUY
        elif ot.leg_role == "overlay_collar_call":
            assert ot.trade.action == TradeAction.SELL


def test_build_overlay_trades_notes_contain_cycle_and_expiry():
    cfg = _make_overlay_config(overlay_type="pp", cycle=2, expiry="2026-09-25")
    trades, _ = build_overlay_trades(cfg)
    for ot in trades:
        assert "Cycle 2" in ot.trade.notes
        assert "2026-09-25" in ot.trade.notes


# ── main idempotency guards ───────────────────────────────────────────────────


def test_open_position_prevention(tmp_path, capsys):
    """Test that open overlay_cc position on STRATEGY_SPOT prevents new CC entry."""
    from unittest.mock import MagicMock, patch

    from scripts.strategies.three_track.paper_3track_overlay_entry import main
    from src.paper.constants import STRATEGY_SPOT

    config_path = _write_yaml(tmp_path, _valid_cc_raw())
    db_path = tmp_path / "dummy.sqlite"

    test_args = [
        "paper_3track_overlay_entry.py",
        "--config",
        str(config_path),
        "--db-path",
        str(db_path),
        "--dry-run",
    ]

    with (
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore"
        ) as mock_store_cls,
        patch("sys.argv", test_args),
    ):
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store

        def mock_get_positions(strategy_name):
            if strategy_name == STRATEGY_SPOT:
                m = MagicMock(leg_role="overlay_cc")
                m.net_qty = -1
                return [m]
            return []

        mock_store.get_positions.side_effect = mock_get_positions

        with pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 0
        captured = capsys.readouterr()
        assert "paper_3track_overlay_entry.duplicate_position" in captured.out


def test_entry_proceeds_when_no_open_position(tmp_path, capsys):
    """Test positive path: entry proceeds when no overlay_cc exists on STRATEGY_SPOT."""
    from unittest.mock import MagicMock, patch

    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    config_path = _write_yaml(tmp_path, _valid_cc_raw())
    db_path = tmp_path / "dummy.sqlite"

    test_args = [
        "paper_3track_overlay_entry.py",
        "--config",
        str(config_path),
        "--db-path",
        str(db_path),
        "--dry-run",
    ]

    with (
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore"
        ) as mock_store_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry._query_open_call_role"
        ) as mock_query,
        patch("sys.argv", test_args),
    ):
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.get_positions.return_value = []
        mock_query.return_value = None

        main()

        captured = capsys.readouterr()
        assert "paper_3track_overlay_entry.duplicate_position" not in captured.out


def test_existing_query_open_call_roles_guard_unchanged(tmp_path, capsys):
    """Test regression guard: _query_open_call_role check still works and skips overlay_collar_call."""
    from unittest.mock import MagicMock, patch

    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    config_path = _write_yaml(tmp_path, _valid_cc_raw())
    db_path = tmp_path / "dummy.sqlite"

    test_args = [
        "paper_3track_overlay_entry.py",
        "--config",
        str(config_path),
        "--db-path",
        str(db_path),
        "--dry-run",
    ]

    with (
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore"
        ) as mock_store_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry._query_open_call_role"
        ) as mock_query,
        patch("sys.argv", test_args),
    ):
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.get_positions.return_value = []
        mock_query.return_value = "overlay_collar_call"

        with pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 1


def test_reentry_gates_applied_to_bootstrap_entry(tmp_path, capsys):
    """DTE/IVR gates must block a fresh bootstrap entry."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-cc",
        "--dry-run",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.InstrumentLookup"
        ) as mock_lookup_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.load_vix_series"
        ) as mock_load,
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.compute_ivr") as mock_ivr,
    ):
        mock_lookup = MagicMock()
        mock_lookup_cls.from_file.return_value = mock_lookup
        mock_lookup.get_expiry_candidates.return_value = [("monthly", "2026-08-27")]

        mock_series = MagicMock()
        mock_series.empty = False
        mock_series.__len__.return_value = 252
        mock_series.iloc = [-15.0, 15.0]  # Just need [-1] to work
        mock_load.return_value = mock_series

        # Mock IVR < 0.25 (blocked)
        mock_ivr.return_value = 0.20

        with pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "auto-CC bootstrap failed" in captured.err


def test_auto_cc_no_dry_run_no_longer_blocked(tmp_path, capsys):
    """regression guard: --auto-cc without --dry-run (this script's existing live
    default — it only ever defined a plain --dry-run store_true flag, never a
    --no-dry-run counterpart) proceeds to bootstrap now that CC1/CC2/EC-5 have
    landed (2026-08-02) — must not resurrect the old hard block."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-cc",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_cc_bootstrap"
        ) as mock_bootstrap,
    ):
        # Bootstrap gates (DTE/IVR/liquidity) are exercised separately by
        # test_reentry_gates_applied_to_bootstrap_entry; here we only assert the
        # old unconditional --no-dry-run block is gone, so force bootstrap to
        # fail past it cleanly rather than re-testing gate internals.
        mock_bootstrap.return_value = (None, None)

        with pytest.raises(SystemExit) as excinfo:
            main()

        captured = capsys.readouterr()
        assert "temporarily blocked" not in captured.err
        assert excinfo.value.code == 1
        assert "auto-CC bootstrap failed" in captured.err


def test_auto_cc_no_dry_run_writes_trade_on_bootstrap_success(tmp_path, capsys):
    """Full success path: --auto-cc without --dry-run, bootstrap succeeds, must
    actually reach PaperStore.record_trade — not just fail to hit the old block."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    cfg = load_overlay_config(_write_yaml(tmp_path, _valid_cc_raw()))
    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-cc",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_cc_bootstrap"
        ) as mock_bootstrap,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore"
        ) as mock_store_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry._query_open_call_role"
        ) as mock_query,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier",
            return_value=None,
        ),
    ):
        mock_bootstrap.return_value = (cfg, None)
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.get_positions.return_value = []
        mock_query.return_value = None

        main()

        mock_store.record_trade.assert_called_once()
        captured = capsys.readouterr()
        assert "RECORDED TO DB" in captured.out


def test_auto_cc_gate_violation_persisted(tmp_path, capsys):
    """A logged IVR gate violation from auto_cc_bootstrap is persisted via
    PaperStore.record_gate_violation — same log-only-gates contract PP
    already has (2026-08-07: extended from --auto-pp-only to also cover
    --auto-cc/--auto-collar, paper-trading phase, no real capital at risk)."""
    from datetime import datetime, timezone

    from scripts.strategies.three_track.paper_3track_overlay_entry import main
    from src.paper.constants import STRATEGY_CC_OVERLAY
    from src.paper.models import GateViolation

    cfg = load_overlay_config(_write_yaml(tmp_path, _valid_cc_raw()))
    violation = GateViolation(
        gate_name="ivr_cc_reentry",
        threshold="0.25",
        actual="0.1393",
        strategy_name=STRATEGY_CC_OVERLAY,
        logged_at=datetime.now(timezone.utc),
    )

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-cc",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_cc_bootstrap"
        ) as mock_bootstrap,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore"
        ) as mock_store_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry._query_open_call_role"
        ) as mock_query,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier",
            return_value=None,
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.UpstoxMarketClient"
        ) as mock_client_cls,
    ):
        # RH-4 collateral-capacity gate (2026-08-06) is advisory-only and out of
        # scope for this test — force its missing-LTP skip path so it never
        # reaches check_collateral_capacity/record_gate_violation with the empty
        # mock_store positions below (which would otherwise read as a real
        # breach and record a second, unrelated GateViolation, doubling the
        # call count this test is asserting on).
        mock_client_cls.return_value.get_ltp_sync.return_value = {}
        mock_bootstrap.return_value = (cfg, violation)
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.get_positions.return_value = []
        mock_store.record_trade.return_value = True
        mock_query.return_value = None

        main()

        mock_store.record_gate_violation.assert_called_once_with(violation)
        captured = capsys.readouterr()
        assert "RECORDED TO DB" in captured.out


def test_notification_failure_does_not_block_entry(tmp_path, capsys):
    """non-fatal Telegram contract"""
    import yaml

    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    cfg_file = tmp_path / "overlay_entry.yaml"
    cfg_file.write_text(
        yaml.dump(
            {
                "overlay": {
                    "type": "cc",
                    "date": "2026-07-29",
                    "cycle": 1,
                    "lot_size": 75,
                    "expiry": "2026-08-27",
                    "call_strike": 25000,
                    "call_instrument_key": "NSE_FO|NIFTY27AUG26CE",
                    "call_price": "100.5",
                }
            }
        )
    )

    test_args = [
        "paper_3track_overlay_entry.py",
        "--config",
        str(cfg_file),
        "--db-path",
        str(tmp_path / "test.sqlite"),
        # we do NOT pass --dry-run because we want to test the notification block
    ]

    with (
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore"
        ) as mock_store_cls,
        patch("sys.argv", test_args),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier"
        ) as mock_build_notifier,
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.asyncio.run") as mock_run,
    ):
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.get_positions.return_value = []
        mock_store.record_trade.return_value = True

        mock_notifier = MagicMock()
        mock_build_notifier.return_value = mock_notifier
        mock_notifier.send.side_effect = Exception("Telegram API down")

        mock_run.side_effect = Exception("Telegram API down")

        # This should NOT raise SystemExit because the exception is caught
        main()

        # Verification that we got past it
        mock_store.record_trade.assert_called_once()
        captured = capsys.readouterr()
        assert "RECORDED TO DB" in captured.out


def test_entry_success(tmp_path, capsys):
    """Verify the full automated CC entry flow."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-cc",
        "--dry-run",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.InstrumentLookup"
        ) as mock_lookup_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.load_vix_series"
        ) as mock_load,
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.compute_ivr") as mock_ivr,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.UpstoxMarketClient"
        ) as mock_client_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry._select_delta_candidates"
        ) as mock_candidates,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.filter_strikes_by_delta"
        ) as mock_filter,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.rank_strikes"
        ) as mock_rank,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry._apply_liquidity_gate"
        ) as mock_gate,
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.date") as mock_date,
    ):
        from datetime import date

        mock_date.today.return_value = date(2026, 8, 1)
        mock_date.fromisoformat.side_effect = date.fromisoformat

        mock_lookup = MagicMock()
        mock_lookup_cls.from_file.return_value = mock_lookup
        mock_lookup.get_expiry_candidates.return_value = [("monthly", "2026-08-27")]

        mock_series = MagicMock()
        mock_series.empty = False
        mock_series.__len__.return_value = 252
        mock_series.iloc = [-15.0, 15.0]
        mock_load.return_value = mock_series

        mock_ivr.return_value = 0.30  # > 0.25 (passed)

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_option_chain_sync.return_value = [{"some": "data"}]

        mock_candidates.return_value = [0.18, 0.20, 0.15]
        mock_filter.return_value = [{"strike": 25000}]
        mock_rank.return_value = [{"strike": 25000}]

        mock_gate.return_value = [
            {
                "strike": 25000,
                "instrument_key": "NSE_FO|NIFTY27AUG26CE",
                "mid": 100.0,
                "ltp": 99.0,
                "gate_spread": 1.5,
                "oi": 1000,
            }
        ]

        main()

        captured = capsys.readouterr()
        assert "100.00" in captured.out


# ── PP3: automated PP entry (auto_pp_bootstrap + --auto-pp) ────────────────────


def test_entry_skipped_when_open_pp_position_exists(tmp_path, capsys):
    """DTE > roll threshold on the open put -> no-op, exit 0, bootstrap never called."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-pp",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry._open_pp_dte") as mock_dte,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_pp_bootstrap"
        ) as mock_bootstrap,
    ):
        mock_dte.return_value = 20  # fresh put already covers

        with pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 0
        mock_bootstrap.assert_not_called()
        captured = capsys.readouterr()
        assert "SKIPPED" in captured.err
        assert "DTE=20" in captured.err


def test_entry_proceeds_when_no_open_pp_position(tmp_path, capsys):
    """No open put at all (bootstrap case) -> bootstrap runs, trade recorded."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    cfg = load_overlay_config(_write_yaml(tmp_path, _valid_pp_raw()))

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-pp",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry._open_pp_dte") as mock_dte,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_pp_bootstrap"
        ) as mock_bootstrap,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore"
        ) as mock_store_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier",
            return_value=None,
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.UpstoxMarketClient"
        ) as mock_client_cls,
    ):
        # RH-4 collateral-capacity gate (2026-08-06) is advisory-only and out of scope
        # for this test — force its missing-LTP skip path so it never reaches
        # check_collateral_capacity/record_gate_violation with the empty mock_store
        # positions below (which would otherwise read as a real breach).
        mock_client_cls.return_value.get_ltp_sync.return_value = {}
        mock_dte.return_value = None  # nothing open
        mock_bootstrap.return_value = (cfg, None)
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.get_positions.return_value = []
        mock_store.record_trade.return_value = True

        main()

        mock_store.record_trade.assert_called_once()
        mock_store.record_gate_violation.assert_not_called()
        captured = capsys.readouterr()
        assert "RECORDED TO DB" in captured.out


def test_entry_proceeds_on_routine_roll_with_old_put_still_open(tmp_path, capsys):
    """DTE <= roll threshold -> proceeds even though the outgoing put is still
    open under the same leg_role (no-gap requirement — briefly holds two puts).
    Confirms the generic S6 one-time-bootstrap gate is correctly bypassed for
    this path (PP3, 2026-08-03) rather than incorrectly re-blocking it."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main
    from src.paper.models import PaperPosition

    cfg = load_overlay_config(_write_yaml(tmp_path, _valid_pp_raw()))

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-pp",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry._open_pp_dte") as mock_dte,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_pp_bootstrap"
        ) as mock_bootstrap,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore"
        ) as mock_store_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier",
            return_value=None,
        ),
    ):
        mock_dte.return_value = 3  # routine roll trigger
        mock_bootstrap.return_value = (cfg, None)
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        # Outgoing put still open under overlay_pp — would trip the generic
        # S6 bootstrap gate (_has_open_overlay_leg) if not bypassed.
        mock_store.get_positions.return_value = [
            PaperPosition(
                strategy_name="paper_nifty_overlay",
                leg_role="overlay_pp",
                net_qty=65,
                avg_cost=Decimal("80"),
                avg_sell_price=Decimal("0"),
                instrument_key="NSE_FO|NIFTY05AUG2026PE",
            )
        ]
        mock_store.record_trade.return_value = True

        main()

        mock_store.record_trade.assert_called_once()
        captured = capsys.readouterr()
        assert "RECORDED TO DB" in captured.out


def test_auto_pp_bootstrap_failure_exits_1(tmp_path, capsys):
    """Structural bootstrap failure (BOD/DTE/IVR/chain/strike) aborts hard."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-pp",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry._open_pp_dte") as mock_dte,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_pp_bootstrap"
        ) as mock_bootstrap,
    ):
        mock_dte.return_value = None
        mock_bootstrap.return_value = (None, None)

        with pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "auto-PP bootstrap failed" in captured.err


def test_auto_pp_gate_violation_persisted(tmp_path, capsys):
    """A logged IVR gate violation from auto_pp_bootstrap is persisted via
    PaperStore.record_gate_violation — the log-only-gates contract (PP3,
    reusing IC's resolve_ivr/GateViolation pattern)."""
    from datetime import datetime, timezone

    from scripts.strategies.three_track.paper_3track_overlay_entry import main
    from src.paper.constants import STRATEGY_PP_OVERLAY
    from src.paper.models import GateViolation

    cfg = load_overlay_config(_write_yaml(tmp_path, _valid_pp_raw()))
    violation = GateViolation(
        gate_name="ivr_pp_reentry",
        threshold="0.6",
        actual="0.7123",
        strategy_name=STRATEGY_PP_OVERLAY,
        logged_at=datetime.now(timezone.utc),
    )

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-pp",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry._open_pp_dte") as mock_dte,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_pp_bootstrap"
        ) as mock_bootstrap,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore"
        ) as mock_store_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier",
            return_value=None,
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.UpstoxMarketClient"
        ) as mock_client_cls,
    ):
        # RH-4 collateral-capacity gate (2026-08-06) is advisory-only and out of scope
        # for this test — force its missing-LTP skip path so the only
        # record_gate_violation call is the one under test (the IVR violation from
        # auto_pp_bootstrap), not a spurious breach from the empty mock_store positions.
        mock_client_cls.return_value.get_ltp_sync.return_value = {}
        mock_dte.return_value = None
        mock_bootstrap.return_value = (cfg, violation)
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.get_positions.return_value = []
        mock_store.record_trade.return_value = True

        main()

        mock_store.record_gate_violation.assert_called_once_with(violation)
        captured = capsys.readouterr()
        assert "RECORDED TO DB" in captured.out


def test_notification_failure_does_not_block_pp_entry(tmp_path, capsys):
    """non-fatal Telegram contract, --auto-pp path (mirrors CC's equivalent test)."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    cfg = load_overlay_config(_write_yaml(tmp_path, _valid_pp_raw()))

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-pp",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry._open_pp_dte") as mock_dte,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_pp_bootstrap"
        ) as mock_bootstrap,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore"
        ) as mock_store_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier"
        ) as mock_build_notifier,
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.asyncio.run") as mock_run,
    ):
        mock_dte.return_value = None
        mock_bootstrap.return_value = (cfg, None)
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.get_positions.return_value = []
        mock_store.record_trade.return_value = True

        mock_notifier = MagicMock()
        mock_build_notifier.return_value = mock_notifier
        mock_run.side_effect = Exception("Telegram API down")

        main()  # must not raise

        mock_store.record_trade.assert_called_once()
        captured = capsys.readouterr()
        assert "RECORDED TO DB" in captured.out


def test_open_pp_dte_returns_none_when_no_rows(tmp_path):
    """_open_pp_dte against an empty DB returns None (bootstrap case)."""
    import sqlite3

    from scripts.strategies.three_track.paper_3track_overlay_entry import _open_pp_dte

    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE paper_trades (
            strategy_name TEXT, leg_role TEXT, instrument_key TEXT,
            action TEXT, quantity INTEGER
        )
        """
    )
    conn.commit()
    conn.close()

    assert _open_pp_dte(db_path) is None


def test_open_pp_dte_computes_dte_from_open_row(tmp_path):
    """_open_pp_dte parses the embedded expiry and returns calendar DTE."""
    import sqlite3
    from datetime import timedelta

    from scripts.strategies.three_track.paper_3track_overlay_entry import _open_pp_dte
    from src.paper.constants import STRATEGY_OVERLAY

    expiry = date.today() + timedelta(days=3)
    key = f"NSE_FO|NIFTY{expiry.strftime('%d%b%Y').upper()}PE"

    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE paper_trades (
            strategy_name TEXT, leg_role TEXT, instrument_key TEXT,
            action TEXT, quantity INTEGER
        )
        """
    )
    conn.execute(
        "INSERT INTO paper_trades VALUES (?, 'overlay_pp', ?, 'BUY', 65)",
        (STRATEGY_OVERLAY, key),
    )
    conn.commit()
    conn.close()

    assert _open_pp_dte(db_path) == 3


# ── Collar3b: --auto-collar bootstrap ───────────────────────────────────────


def test_auto_collar_no_dry_run_no_longer_blocked(tmp_path, capsys):
    """Live-posture unblock (2026-08-04): --auto-collar without --dry-run
    proceeds to bootstrap now that Collar1/Collar2/Collar3a have all landed —
    no decision gate remains open (mirrors CC3's own unblock regression test)."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-collar",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_collar_bootstrap"
        ) as mock_bootstrap,
    ):
        # Bootstrap gates (DTE/IVR/ladder) are exercised separately by
        # test_auto_collar_bootstrap_failure_exits_1; here we only assert the
        # old --dry-run-only block is gone, so force bootstrap to fail past
        # it cleanly rather than re-testing gate internals.
        mock_bootstrap.return_value = (None, None)

        with pytest.raises(SystemExit) as excinfo:
            main()

        captured = capsys.readouterr()
        assert "requires --dry-run" not in captured.err
        assert excinfo.value.code == 1
        assert "auto-collar bootstrap failed" in captured.err


def test_auto_collar_no_dry_run_writes_trades_on_bootstrap_success(tmp_path, capsys):
    """Full success path: --auto-collar without --dry-run, bootstrap succeeds,
    must actually reach PaperStore.record_trades (collar writes both legs
    atomically via _record_collar_trades) — not just fail to hit the old block."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    cfg = load_overlay_config(_write_yaml(tmp_path, _valid_collar_raw()))
    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-collar",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_collar_bootstrap"
        ) as mock_bootstrap,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore"
        ) as mock_store_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry._query_open_call_role"
        ) as mock_query,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier",
            return_value=None,
        ),
    ):
        mock_bootstrap.return_value = (cfg, None)
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.get_positions.return_value = []
        mock_store.record_trades.return_value = ([], [])
        mock_query.return_value = None

        main()

        mock_store.record_trades.assert_called_once()
        trades = mock_store.record_trades.call_args[0][0]
        assert {t.leg_role for t in trades} == {"overlay_collar_put", "overlay_collar_call"}
        captured = capsys.readouterr()
        assert "RECORDED TO DB" in captured.out


def test_auto_collar_gate_violation_persisted(tmp_path, capsys):
    """A logged IVR gate violation from auto_collar_bootstrap is persisted via
    PaperStore.record_gate_violation — same log-only-gates contract PP/CC
    already have (2026-08-07 extension, paper-trading phase)."""
    from datetime import datetime, timezone

    from scripts.strategies.three_track.paper_3track_overlay_entry import main
    from src.paper.constants import STRATEGY_COLLAR_OVERLAY
    from src.paper.models import GateViolation

    cfg = load_overlay_config(_write_yaml(tmp_path, _valid_collar_raw()))
    violation = GateViolation(
        gate_name="ivr_collar_reentry",
        threshold="0.25",
        actual="0.1393",
        strategy_name=STRATEGY_COLLAR_OVERLAY,
        logged_at=datetime.now(timezone.utc),
    )

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-collar",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_collar_bootstrap"
        ) as mock_bootstrap,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore"
        ) as mock_store_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry._query_open_call_role"
        ) as mock_query,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier",
            return_value=None,
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.UpstoxMarketClient"
        ) as mock_client_cls,
    ):
        # RH-4 collateral-capacity gate (2026-08-06) is advisory-only and out of
        # scope for this test — force its missing-LTP skip path so it never
        # reaches check_collateral_capacity/record_gate_violation with the empty
        # mock_store positions below (which would otherwise read as a real
        # breach and record a second, unrelated GateViolation, doubling the
        # call count this test is asserting on).
        mock_client_cls.return_value.get_ltp_sync.return_value = {}
        mock_bootstrap.return_value = (cfg, violation)
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.get_positions.return_value = []
        mock_store.record_trades.return_value = ([], [])
        mock_query.return_value = None

        main()

        mock_store.record_gate_violation.assert_called_once_with(violation)
        captured = capsys.readouterr()
        assert "RECORDED TO DB" in captured.out


def test_auto_collar_bootstrap_no_open_position(tmp_path, capsys):
    """Happy path: both legs selected via mocked auto_collar_bootstrap, dry-run
    preview only — no trades written to the DB."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    cfg = load_overlay_config(_write_yaml(tmp_path, _valid_collar_raw()))
    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-collar",
        "--dry-run",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_collar_bootstrap"
        ) as mock_bootstrap,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore"
        ) as mock_store_cls,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry._query_open_call_role"
        ) as mock_query,
    ):
        mock_bootstrap.return_value = (cfg, None)
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.get_positions.return_value = []
        mock_query.return_value = None

        main()

        mock_store.record_trades.assert_not_called()
        mock_store.record_trade.assert_not_called()
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out


def test_auto_collar_bootstrap_failure_exits_1(tmp_path, capsys):
    """Structural bootstrap failure (BOD/DTE/IVR/chain/ladder) aborts hard."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-collar",
        "--dry-run",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_collar_bootstrap"
        ) as mock_bootstrap,
    ):
        mock_bootstrap.return_value = (None, None)

        with pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "auto-collar bootstrap failed" in captured.err


def test_has_open_overlay_leg_recognizes_collar_primary_role(tmp_path):
    """The generic S6 one-time-bootstrap gate (_has_open_overlay_leg) already
    covers collar via _PRIMARY_LEG_ROLE["collar"] == "overlay_collar_put" —
    confirmed here with a real PaperStore rather than trusting the code read,
    since --auto-collar's own dry-run-only posture prevents exercising the
    live skip-message path end-to-end through main() yet."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import (
        _PRIMARY_LEG_ROLE,
        _has_open_overlay_leg,
    )
    from src.models.portfolio import TradeAction
    from src.paper.constants import STRATEGY_OVERLAY
    from src.paper.models import PaperTrade
    from src.paper.store import PaperStore

    assert _PRIMARY_LEG_ROLE["collar"] == "overlay_collar_put"

    store = PaperStore(tmp_path / "test.sqlite")
    assert _has_open_overlay_leg(store, "overlay_collar_put") is False

    store.record_trade(
        PaperTrade(
            strategy_name=STRATEGY_OVERLAY,
            leg_role="overlay_collar_put",
            instrument_key="NSE_FO|NIFTY23900PE",
            trade_date=date.today(),
            action=TradeAction.BUY,
            quantity=65,
            price=Decimal("38.0"),
        )
    )
    assert _has_open_overlay_leg(store, "overlay_collar_put") is True


# ── BUG-026: settings.vix_data_dir str/Path mismatch at the IVR gate ───────────
#
# auto_cc_bootstrap/auto_collar_bootstrap/auto_pp_bootstrap passed
# settings.vix_data_dir straight into load_vix_series(), which immediately
# calls .glob() on it. Every other test for these functions mocks
# load_vix_series() directly, so a str vs. Path defect in the real settings
# value never reached .glob() in the suite and the crash shipped silently on
# every cron run. These tests exercise the real load_vix_series() call
# (only InstrumentLookup/chain-fetch are mocked) against a real fixture VIX
# Parquet directory, so a regression back to settings.vix_data_dir: str
# fails here with AttributeError instead of only in prod logs.


def _write_vix_fixture(vix_dir: Path, rows: int = 252) -> None:
    """Write a real india_vix_*.parquet file load_vix_series can glob/read."""
    import pandas as pd

    vix_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range(end=date.today(), periods=rows, freq="B").date
    df = pd.DataFrame({"date": dates, "close": [15.0] * rows})
    df.to_parquet(vix_dir / "india_vix_fixture.parquet")


def test_auto_cc_bootstrap_reaches_chain_fetch_with_real_vix_dir(tmp_path, monkeypatch):
    """auto_cc_bootstrap must clear the real IVR gate (settings.vix_data_dir as
    an actual Path, load_vix_series not mocked) and reach the chain-fetch
    stage — the BUG-026 crash site is between these two, so getting past the
    IVR gate without AttributeError is the regression proof."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import (
        auto_cc_bootstrap,
    )

    vix_dir = tmp_path / "vix"
    _write_vix_fixture(vix_dir)
    monkeypatch.setattr(
        "scripts.strategies.three_track.paper_3track_overlay_entry.settings.vix_data_dir",
        vix_dir,
    )

    with patch(
        "scripts.strategies.three_track.paper_3track_overlay_entry.InstrumentLookup"
    ) as mock_lookup_cls:
        mock_lookup = MagicMock()
        mock_lookup_cls.from_file.return_value = mock_lookup
        mock_lookup.get_expiry_candidates.return_value = [("monthly", "2026-08-27")]

        # UpstoxMarketClient is never patched here — chain fetch fails on a
        # real (unconfigured) client, which is fine: we only need proof the
        # IVR gate (the BUG-026 crash site) was cleared without raising.
        cfg, gate_violation = auto_cc_bootstrap(tmp_path / "bod.json")

    assert cfg is None


def test_auto_pp_bootstrap_reaches_chain_fetch_with_real_vix_dir(tmp_path, monkeypatch):
    """Same regression proof as CC, for the PP bootstrap path."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import (
        auto_pp_bootstrap,
    )

    vix_dir = tmp_path / "vix"
    _write_vix_fixture(vix_dir)
    monkeypatch.setattr(
        "scripts.strategies.three_track.paper_3track_overlay_entry.settings.vix_data_dir",
        vix_dir,
    )

    with patch(
        "scripts.strategies.three_track.paper_3track_overlay_entry.InstrumentLookup"
    ) as mock_lookup_cls:
        mock_lookup = MagicMock()
        mock_lookup_cls.from_file.return_value = mock_lookup
        mock_lookup.get_expiry_candidates.return_value = [("monthly", "2026-08-27")]

        cfg, gate_violation = auto_pp_bootstrap(tmp_path / "bod.json")

    assert cfg is None


def test_auto_collar_bootstrap_reaches_chain_fetch_with_real_vix_dir(tmp_path, monkeypatch):
    """Same regression proof as CC, for the Collar bootstrap path."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import (
        auto_collar_bootstrap,
    )

    vix_dir = tmp_path / "vix"
    _write_vix_fixture(vix_dir)
    monkeypatch.setattr(
        "scripts.strategies.three_track.paper_3track_overlay_entry.settings.vix_data_dir",
        vix_dir,
    )

    with patch(
        "scripts.strategies.three_track.paper_3track_overlay_entry.InstrumentLookup"
    ) as mock_lookup_cls:
        mock_lookup = MagicMock()
        mock_lookup_cls.from_file.return_value = mock_lookup
        mock_lookup.get_expiry_candidates.return_value = [("monthly", "2026-08-27")]

        cfg, gate_violation = auto_collar_bootstrap(tmp_path / "bod.json")

    assert cfg is None


# ── _resolve_lot_size ─────────────────────────────────────────────────────


def test_resolve_lot_size_reads_from_bod_record():
    """Happy path: BOD record has a lot_size, it's used verbatim."""
    lookup = MagicMock()
    lookup.get_by_key.return_value = {"instrument_key": "NSE_FO|61622", "lot_size": 65}

    result = _resolve_lot_size(lookup, "NSE_FO|61622")

    assert result == 65
    lookup.get_by_key.assert_called_once_with("NSE_FO|61622")


def test_resolve_lot_size_falls_back_when_bod_record_missing():
    """Edge case: BOD lookup returns None (key not found) — use fallback, don't raise."""
    lookup = MagicMock()
    lookup.get_by_key.return_value = None

    result = _resolve_lot_size(lookup, "NSE_FO|does_not_exist")

    assert result == _NIFTY_LOT_SIZE_FALLBACK


def test_nifty_lot_size_fallback_is_65_not_stale_75():
    """Regression pin: the fallback must be the current Nifty lot size (65),
    not the stale value (75) that caused this bug in the first place."""
    assert _NIFTY_LOT_SIZE_FALLBACK == 65


def test_resolve_lot_size_falls_back_when_bod_lot_size_is_zero():
    """Edge case: BOD record exists but lot_size is 0 (malformed/partial data)
    — must not silently produce a zero-quantity trade."""
    lookup = MagicMock()
    lookup.get_by_key.return_value = {"instrument_key": "NSE_FO|61622", "lot_size": 0}

    result = _resolve_lot_size(lookup, "NSE_FO|61622")

    assert result == _NIFTY_LOT_SIZE_FALLBACK


# ── _alert_bootstrap_failure ─────────────────────────────────────────────────


def test_alert_bootstrap_failure_sends_telegram_message():
    """Happy path: a configured notifier receives a message naming the overlay
    and pointing at the right log file — this is the alert that was entirely
    missing before, which is why the 2026-08-11 auto_pp.no_monthly_expiry_found
    failure went unnoticed for days."""
    with (
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier"
        ) as mock_build_notifier,
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.asyncio.run") as mock_run,
    ):
        mock_notifier = MagicMock()
        mock_build_notifier.return_value = mock_notifier

        _alert_bootstrap_failure("PP", "logs/pp_entry.log")

        mock_run.assert_called_once()
        mock_notifier.send.assert_called_once()
        sent_msg = mock_notifier.send.call_args[0][0]
        assert "PP" in sent_msg
        assert "logs/pp_entry.log" in sent_msg
        assert "FAILED" in sent_msg


def test_alert_bootstrap_failure_no_notifier_configured_is_noop():
    """Edge case: no Telegram credentials configured (build_notifier returns
    None, the existing project-wide contract) — must not raise, must not
    attempt to send anything."""
    with (
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier",
            return_value=None,
        ),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.asyncio.run") as mock_run,
    ):
        _alert_bootstrap_failure("CC", "logs/cc_entry.log")

        mock_run.assert_not_called()


def test_alert_bootstrap_failure_send_exception_is_non_fatal():
    """Edge case: Telegram send itself raises — must be swallowed (logged
    WARNING) exactly like the existing success-path notifier, never allowed
    to mask or replace the underlying structural gate failure that triggered
    the alert in the first place."""
    with (
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier"
        ) as mock_build_notifier,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.asyncio.run",
            side_effect=Exception("Telegram API down"),
        ),
    ):
        mock_build_notifier.return_value = MagicMock()

        # Must not raise.
        _alert_bootstrap_failure("Collar", "logs/collar_entry.log")


def test_auto_pp_bootstrap_failure_triggers_telegram_alert(tmp_path, capsys):
    """Integration: the --auto-pp cfg-is-None branch in main() actually wires
    up _alert_bootstrap_failure, not just prints to stderr."""
    from scripts.strategies.three_track.paper_3track_overlay_entry import main

    test_args = [
        "paper_3track_overlay_entry.py",
        "--auto-pp",
        "--dry-run",
        "--db-path",
        str(tmp_path / "test.sqlite"),
    ]

    with (
        patch("sys.argv", test_args),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry._open_pp_dte") as mock_dte,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_pp_bootstrap"
        ) as mock_bootstrap,
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier"
        ) as mock_build_notifier,
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.asyncio.run") as mock_run,
    ):
        mock_dte.return_value = None
        mock_bootstrap.return_value = (None, None)
        mock_notifier = MagicMock()
        mock_build_notifier.return_value = mock_notifier

        with pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 1
        mock_run.assert_called_once()
        mock_notifier.send.assert_called_once()
        assert "PP" in mock_notifier.send.call_args[0][0]
        captured = capsys.readouterr()
        assert "auto-PP bootstrap failed" in captured.err
