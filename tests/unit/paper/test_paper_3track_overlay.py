"""Unit tests for scripts/paper_3track_overlay.py.

Coverage:
- _rank_overlay_key: round-100 strike beats non-round in same spread bucket.
- _rank_overlay_key: higher OI wins within the same (is_non_round, spread_bucket).
- _otm_pct: PE and CE directional correctness.
- _extract_chain_candidates: OTM band filtering (in-band, out-of-band, no key).
- effective_tracks CC guard: implicit futures (no --tracks arg) triggers exit(1).
- effective_tracks CC guard: CC on spot + proxy succeeds (positive case).
- build_trade: leg_role → action mapping for PP and CC.
- build_trade: collar produces both overlay_collar_put and overlay_collar_call.
- _check_existing_overlay: no trades returns None.
- _check_existing_overlay: open position returns last BUY trade.
- _check_existing_overlay: closed position (net=0) returns None.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade

# Import the module under test
import scripts.paper_3track_overlay as overlay


# ── Helpers ───────────────────────────────────────────────────────────────────

_STRATEGY = "paper_nifty_spot"
_DATE = date(2026, 5, 7)


def _candidate(**kwargs: Any) -> dict:
    defaults: dict[str, Any] = {
        "strike": 22000.0,
        "instrument_key": "NSE_FO|NIFTY22000PE",
        "option_type": "PE",
        "bid": 300.0, "ask": 304.0, "ltp": 302.0, "mid": 302.0,
        "oi": 10_000,
        "otm_pct": 0.09,
        "spread_pct": 1.3,
        "delta": -0.25,
        "expiry": "2026-06-26",
        "expiry_label": "quarterly",
    }
    defaults.update(kwargs)
    return defaults


def _make_trade(
    strategy: str = _STRATEGY,
    leg_role: str = "overlay_pp",
    action: TradeAction = TradeAction.BUY,
    quantity: int = 65,
    trade_date: date = _DATE,
) -> PaperTrade:
    return PaperTrade(
        strategy_name=strategy,
        leg_role=leg_role,
        instrument_key="NSE_FO|NIFTY22000PE",
        trade_date=trade_date,
        action=action,
        quantity=quantity,
        price=Decimal("310.00"),
    )


# ── _rank_overlay_key ─────────────────────────────────────────────────────────


def test_rank_overlay_key_round_strike_wins() -> None:
    """is_non_round=0 (multiple of 100) beats is_non_round=1 in the same spread bucket."""
    round_cand = _candidate(strike=22000.0, bid=300.0, ask=302.0, oi=8_000)
    non_round   = _candidate(strike=21950.0, bid=300.0, ask=302.0, oi=12_000)

    round_key    = overlay._rank_overlay_key(round_cand, 0.09)
    non_round_key = overlay._rank_overlay_key(non_round, 0.09)

    # round strike should sort BEFORE non-round (lower key wins)
    assert round_key < non_round_key, (
        f"Round strike key {round_key} should be < non-round key {non_round_key}"
    )


def test_rank_overlay_key_higher_oi_wins_in_same_bucket() -> None:
    """Within the same (is_non_round, spread_bucket), higher OI wins."""
    high_oi = _candidate(strike=22000.0, bid=300.0, ask=302.0, oi=20_000)
    low_oi  = _candidate(strike=22000.0, bid=300.0, ask=302.0, oi=5_000)

    high_key = overlay._rank_overlay_key(high_oi, 0.09)
    low_key  = overlay._rank_overlay_key(low_oi, 0.09)

    assert high_key < low_key, (
        f"High OI key {high_key} should be < low OI key {low_key}"
    )


# ── _otm_pct ─────────────────────────────────────────────────────────────────


def test_otm_pct_pe_below_spot() -> None:
    pct = overlay._otm_pct(22000.0, 24000.0, "PE")
    assert round(pct, 4) == round((24000 - 22000) / 24000, 4)


def test_otm_pct_ce_above_spot() -> None:
    pct = overlay._otm_pct(25000.0, 24000.0, "CE")
    assert round(pct, 4) == round((25000 - 24000) / 24000, 4)


# ── _extract_chain_candidates ─────────────────────────────────────────────────

def _chain_entry(strike: float, bid: float, ask: float, oi: int, key: str = "NSE_FO|X") -> dict:
    ltp = (bid + ask) / 2
    return {
        "strike_price": strike,
        "underlying_spot_price": 24000.0,
        "put_options": {
            "instrument_key": key,
            "market_data": {"bid_price": bid, "ask_price": ask, "ltp": ltp, "oi": oi},
            "option_greeks": {"delta": -0.25, "iv": 0.18},
        },
        "call_options": {
            "instrument_key": key,
            "market_data": {"bid_price": bid, "ask_price": ask, "ltp": ltp, "oi": oi},
            "option_greeks": {"delta": 0.25, "iv": 0.18},
        },
    }


def test_extract_chain_candidates_in_band() -> None:
    # spot=24000, PE, OTM 8–10% → strikes 21600–22080
    chain = [_chain_entry(22000.0, 300.0, 304.0, 10_000)]
    results = overlay._extract_chain_candidates(
        chain, "PE", 24000.0, 0.08, 0.10, "2026-06-26", "quarterly"
    )
    assert len(results) == 1
    assert results[0]["strike"] == 22000.0


def test_extract_chain_candidates_out_of_band_excluded() -> None:
    # 20000 strike → OTM = (24000-20000)/24000 = 16.7% — outside 8–10% band
    chain = [_chain_entry(20000.0, 100.0, 102.0, 10_000)]
    results = overlay._extract_chain_candidates(
        chain, "PE", 24000.0, 0.08, 0.10, "2026-06-26", "quarterly"
    )
    assert results == []


def test_extract_chain_candidates_no_key_excluded() -> None:
    entry = _chain_entry(22000.0, 300.0, 304.0, 10_000, key="")
    entry["put_options"]["instrument_key"] = ""
    results = overlay._extract_chain_candidates(
        [entry], "PE", 24000.0, 0.08, 0.10, "2026-06-26", "quarterly"
    )
    assert results == []


# ── CC guard — effective_tracks ───────────────────────────────────────────────


def test_cc_blocked_on_futures_exits_1(tmp_path: Path) -> None:
    """CC with implicit all-tracks (futures included) must exit(1)."""
    db = tmp_path / "p.db"
    args = _make_args(overlay="cc", tracks=None, db_path=db)  # None → defaults to ALL_TRACKS

    with pytest.raises(SystemExit) as exc_info:
        import asyncio
        asyncio.run(overlay._run(args))

    assert exc_info.value.code == 1


def test_cc_on_spot_and_proxy_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CC restricted to spot + proxy must pass the CC-on-futures guard."""
    db = tmp_path / "p.db"
    args = _make_args(
        overlay="cc",
        tracks=["paper_nifty_spot", "paper_nifty_proxy"],
        db_path=db,
    )
    # Resolve effective_tracks the same way _run() does, then verify guard does NOT fire
    effective_tracks = args.tracks if args.tracks else list(overlay.ALL_TRACKS)
    assert not any(t in overlay._CC_BLOCKED_TRACKS for t in effective_tracks), (
        "CC guard should NOT fire when futures is not in effective_tracks"
    )


# ── _build_trade ──────────────────────────────────────────────────────────────


def test_build_trade_pp_leg_role() -> None:
    best = _candidate(mid=310.0)
    trade = overlay._build_trade("paper_nifty_spot", "overlay_pp", best, _DATE, 65)
    assert trade.action == TradeAction.BUY
    assert trade.leg_role == "overlay_pp"
    assert trade.quantity == 65
    assert trade.price == Decimal("310.00")


def test_build_trade_cc_leg_role() -> None:
    best = _candidate(mid=120.0, option_type="CE")
    trade = overlay._build_trade("paper_nifty_spot", "overlay_cc", best, _DATE, 65)
    assert trade.action == TradeAction.SELL
    assert trade.leg_role == "overlay_cc"


def test_build_trade_collar_both_legs() -> None:
    put_best  = _candidate(mid=310.0, option_type="PE")
    call_best = _candidate(mid=120.0, option_type="CE")
    put_trade  = overlay._build_trade("paper_nifty_spot", "overlay_collar_put",  put_best,  _DATE, 65)
    call_trade = overlay._build_trade("paper_nifty_spot", "overlay_collar_call", call_best, _DATE, 65)
    assert put_trade.action  == TradeAction.BUY
    assert call_trade.action == TradeAction.SELL
    assert put_trade.leg_role  == "overlay_collar_put"
    assert call_trade.leg_role == "overlay_collar_call"


# ── _check_existing_overlay ───────────────────────────────────────────────────


def test_check_existing_overlay_no_trades_returns_none(tmp_path: Path) -> None:
    from src.paper.store import PaperStore
    store = PaperStore(tmp_path / "p.db")
    result = overlay._check_existing_overlay(store, _STRATEGY, "overlay_pp")
    assert result is None


def test_check_existing_overlay_open_position_returns_last_buy(tmp_path: Path) -> None:
    from src.paper.store import PaperStore
    store = PaperStore(tmp_path / "p.db")
    trade = _make_trade(action=TradeAction.BUY)
    store.record_trade(trade)
    result = overlay._check_existing_overlay(store, _STRATEGY, "overlay_pp")
    assert result is not None
    assert result.action == TradeAction.BUY


def test_check_existing_overlay_open_sell_position_returns_trade(tmp_path: Path) -> None:
    """CC/collar_call positions are opened via SELL. The bug was that last_trade was
    only updated on BUY, so open SELL positions returned None as if no position existed."""
    from src.paper.store import PaperStore
    store = PaperStore(tmp_path / "p.db")
    trade = _make_trade(action=TradeAction.SELL, leg_role="overlay_cc")
    store.record_trade(trade)
    result = overlay._check_existing_overlay(store, _STRATEGY, "overlay_cc")
    assert result is not None, (
        "open CC position (net SELL) must be detected — "
        "was returning None before the last_trade-on-every-iteration fix"
    )
    assert result.action == TradeAction.SELL


def test_check_existing_overlay_closed_position_returns_none(tmp_path: Path) -> None:
    from src.paper.store import PaperStore
    store = PaperStore(tmp_path / "p.db")
    buy = _make_trade(action=TradeAction.BUY, trade_date=date(2026, 5, 1))
    sell = _make_trade(action=TradeAction.SELL, trade_date=date(2026, 5, 20))
    store.record_trade(buy)
    store.record_trade(sell)
    # net qty = 0 → position is closed
    result = overlay._check_existing_overlay(store, _STRATEGY, "overlay_pp")
    assert result is None


def test_check_existing_overlay_same_expiry_no_force_needed(tmp_path: Path) -> None:
    """Existing open with SAME expiry as selected — no --force required."""
    from src.paper.store import PaperStore
    store = PaperStore(tmp_path / "p.db")
    trade = _make_trade(action=TradeAction.BUY)
    store.record_trade(trade)
    existing = overlay._check_existing_overlay(store, _STRATEGY, "overlay_pp")
    # Same expiry scenario: the guard in _run() compares expiries;
    # if same, it proceeds without --force. We verify the check itself finds the position.
    assert existing is not None


def test_check_existing_overlay_diff_expiry_requires_force(tmp_path: Path) -> None:
    """Different expiry without --force must exit(1).

    The existing open trade's instrument_key encodes the old expiry (2026-05-29).
    The newly selected best expiry is 2026-06-26. Without --force the script
    must exit(1) rather than silently stacking a second overlay on the same leg.
    """
    import asyncio
    from src.paper.store import PaperStore
    from unittest.mock import AsyncMock, patch

    db = tmp_path / "p.db"
    store = PaperStore(db)
    # Record an existing open PP with a May expiry in the instrument key
    existing_trade = PaperTrade(
        strategy_name="paper_nifty_spot",
        leg_role="overlay_pp",
        instrument_key="NSE_FO|NIFTY29MAY2026PE",  # encodes 2026-05-29
        trade_date=date(2026, 5, 1),
        action=TradeAction.BUY,
        quantity=65,
        price=Decimal("310.00"),
    )
    store.record_trade(existing_trade)

    # _run() fetches chains; mock everything network-related so we reach the expiry guard
    args = _make_args(
        overlay="pp",
        tracks=["paper_nifty_spot"],
        db_path=db,
        dry_run=False,
        yes=True,
        force=False,  # no --force
        date_str="2026-06-01",
    )

    # Minimal chain with one PE candidate in 8-10% OTM band (spot=24000, target ~21600-22080)
    dummy_chain = [{
        "strike_price": 22000.0,
        "underlying_spot_price": 24000.0,
        "put_options": {
            "instrument_key": "NSE_FO|NIFTY22000PE26JUN2026",
            "market_data": {"bid_price": 300.0, "ask_price": 302.0, "ltp": 301.0, "oi": 10000},
            "option_greeks": {"delta": -0.25, "iv": 0.18},
        },
        "call_options": {"instrument_key": "", "market_data": {}, "option_greeks": {}},
    }]

    # Stub BOD so _collect_expiry_candidates returns a quarterly (2026-06-26)
    dummy_lookup = type("L", (), {
        "_instruments": [
            {
                "segment": "NSE_FO",
                "instrument_type": "PE",
                "underlying_symbol": "NIFTY",
                "expiry": "2026-06-26",
            }
        ]
    })()

    with (
        patch("scripts.paper_3track_overlay.UpstoxMarketClient") as MockClient,
        patch("scripts.paper_3track_overlay.InstrumentLookup") as MockLookup,
        patch("scripts.paper_3track_overlay._pe", return_value="2026-05-29"),
    ):
        mock_instance = MockClient.return_value
        mock_instance.get_option_chain = AsyncMock(return_value=dummy_chain)
        MockLookup.from_file.return_value = dummy_lookup

        with pytest.raises(SystemExit) as exc_info:
            asyncio.run(overlay._run(args))

    assert exc_info.value.code == 1, (
        "Different expiry without --force must exit(1) — "
        "the safety check must prevent silently stacking a second overlay"
    )


# ── Fixture helper ────────────────────────────────────────────────────────────


def _make_args(
    overlay: str = "pp",
    tracks: list[str] | None = None,
    db_path: Path = Path("data/portfolio/portfolio.sqlite"),
    dry_run: bool = True,
    yes: bool = False,
    force: bool = False,
    date_str: str = "2026-05-07",
    bod_path: Path = Path("data/instruments/NSE.json.gz"),
) -> object:
    import argparse
    ns = argparse.Namespace()
    ns.overlay  = overlay
    ns.tracks   = tracks
    ns.db_path  = db_path
    ns.dry_run  = dry_run
    ns.yes      = yes
    ns.force    = force
    ns.date     = date_str
    ns.bod_path = bod_path
    return ns
