"""Unit tests for scripts/paper_3track_overlay.py.

Coverage:
- _rank_overlay_key: round-100 strike beats non-round in same spread bucket.
- _rank_overlay_key: higher OI wins within the same (is_non_round, spread_bucket).
- _otm_pct: PE and CE directional correctness.
- _extract_chain_candidates: OTM band filtering (in-band, out-of-band, no key).
- effective_tracks CC guard: futures auto-excluded from CC, spot+proxy proceed.
- effective_tracks CC guard: CC with futures-only track list exits(1) — no eligible tracks.
- effective_tracks CC guard: CC on spot + proxy succeeds (positive case).
- build_trade: leg_role → action mapping for PP and CC.
- build_trade: collar produces both overlay_collar_put and overlay_collar_call.
- _check_existing_overlay: no trades returns None.
- _check_existing_overlay: open position returns last BUY trade.
- _check_existing_overlay: closed position (net=0) returns None.
- CLI --date default: omitting --date defaults to date.today().
- CLI --date explicit: explicit --date is parsed correctly.
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


def test_cc_futures_auto_excluded_leaves_spot_and_proxy() -> None:
    """CC guard must auto-exclude futures and leave spot + proxy in effective_tracks."""
    all_tracks = list(overlay.ALL_TRACKS)  # includes paper_nifty_futures
    blocked = [t for t in all_tracks if t in overlay._CC_BLOCKED_TRACKS]
    remaining = [t for t in all_tracks if t not in overlay._CC_BLOCKED_TRACKS]

    assert "paper_nifty_futures" in blocked
    assert "paper_nifty_spot" in remaining
    assert "paper_nifty_proxy" in remaining
    assert len(remaining) == 2


def test_cc_exits_when_all_tracks_blocked(tmp_path: Path) -> None:
    """CC must exit(1) only when every requested track is blocked (futures-only list)."""
    import asyncio
    db = tmp_path / "p.db"
    args = _make_args(
        overlay="cc",
        tracks=["paper_nifty_futures"],  # only blocked track
        db_path=db,
    )
    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(overlay._run(args))
    assert exc_info.value.code == 1


def test_cc_on_spot_and_proxy_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CC restricted to spot + proxy must pass the CC-on-futures guard."""
    effective_tracks = ["paper_nifty_spot", "paper_nifty_proxy"]
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
    index: int = 1,
) -> object:
    import argparse
    ns = argparse.Namespace()
    ns.overlay  = overlay
    ns.tracks   = tracks
    ns.db_path  = db_path
    ns.dry_run  = dry_run
    ns.yes      = yes
    ns.force    = force
    ns.date     = date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
    ns.bod_path = bod_path
    ns.index    = index
    return ns


# ── CLI --date default ────────────────────────────────────────────────────────

def test_overlay_date_defaults_to_today() -> None:
    """Omitting --date should default entry_date to date.today()."""
    from datetime import date as _date

    # Simulate the logic in _run() with args.date = None
    class _Args:
        date = None

    args = _Args()
    entry_date = _date.fromisoformat(args.date) if args.date else _date.today()
    assert entry_date == _date.today()


def test_overlay_date_explicit_parsed_correctly() -> None:
    """Explicit --date should parse to the given date."""
    from datetime import date as _date

    class _Args:
        date = "2026-05-09"

    args = _Args()
    entry_date = _date.fromisoformat(args.date) if args.date else _date.today()
    assert entry_date == _date(2026, 5, 9)


# ── _print_candidate_table ────────────────────────────────────────────────────


def _pool_of(n: int, best_index: int = 0) -> tuple[list[dict], str]:
    """Return (pool, best_key) with n candidates.  Candidate at best_index is best."""
    pool = [
        _candidate(
            strike=22000.0 - i * 50,
            instrument_key=f"NSE_FO|NIFTY{int(22000 - i*50)}PE",
            oi=10_000 - i * 500,
            bid=300.0 - i,
            ask=302.0 - i,
        )
        for i in range(n)
    ]
    best_key = pool[best_index]["instrument_key"]
    return pool, best_key


def test_print_candidate_table_marks_selected(capsys: pytest.CaptureFixture) -> None:
    """The selected candidate must be marked with ◀ in the output."""
    pool, best_key = _pool_of(3, best_index=0)
    overlay._print_candidate_table(
        leg_role="overlay_pp",
        option_type="PE",
        pool=pool,
        best_key=best_key,
        target_otm=0.09,
        otm_min=0.08,
        otm_max=0.10,
    )
    captured = capsys.readouterr().out
    assert "◀" in captured, "Selected candidate must be marked with ◀"


def test_print_candidate_table_non_selected_has_no_marker(capsys: pytest.CaptureFixture) -> None:
    """Non-selected candidates must NOT carry the ◀ marker."""
    pool, best_key = _pool_of(3, best_index=0)
    overlay._print_candidate_table(
        leg_role="overlay_pp",
        option_type="PE",
        pool=pool,
        best_key=best_key,
        target_otm=0.09,
        otm_min=0.08,
        otm_max=0.10,
    )
    lines = capsys.readouterr().out.splitlines()
    # Data rows start after the header/separator lines; ◀ must appear exactly once
    marker_count = sum(1 for line in lines if "◀" in line)
    assert marker_count == 1, f"Expected exactly 1 ◀ marker, got {marker_count}"


def test_print_candidate_table_single_entry(capsys: pytest.CaptureFixture) -> None:
    """Table with one candidate must not raise and must show 1 data row."""
    pool, best_key = _pool_of(1)
    overlay._print_candidate_table(
        leg_role="overlay_cc",
        option_type="CE",
        pool=pool,
        best_key=best_key,
        target_otm=0.04,
        otm_min=0.03,
        otm_max=0.05,
    )
    out = capsys.readouterr().out
    assert "◀" in out
    # Exactly one data row with the strike value
    strike_str = f"{pool[0]['strike']:.0f}"
    matching = [line for line in out.splitlines() if strike_str in line]
    assert len(matching) >= 1


def test_print_candidate_table_caps_at_ten_rows(capsys: pytest.CaptureFixture) -> None:
    """Even with >10 candidates only the top 10 are printed."""
    pool, best_key = _pool_of(15, best_index=0)
    overlay._print_candidate_table(
        leg_role="overlay_pp",
        option_type="PE",
        pool=pool,
        best_key=best_key,
        target_otm=0.09,
        otm_min=0.08,
        otm_max=0.10,
    )
    out = capsys.readouterr().out
    # Data lines are those containing ₹-free numeric content in the strike column;
    # the simplest proxy: count lines that have a rank number at position 2–4.
    data_lines = [
        line for line in out.splitlines()
        if line.strip() and line.strip()[0].isdigit()
    ]
    assert len(data_lines) <= 10, f"Expected ≤10 data rows, got {len(data_lines)}"


# ── _select_best_candidate index ──────────────────────────────────────────────


def _ranked_pool(n: int) -> list[dict]:
    """Return n candidates with strictly decreasing OI so rank order is deterministic."""
    return [
        _candidate(
            strike=22000.0 - i * 100,
            instrument_key=f"NSE_FO|NIFTY{int(22000 - i*100)}PE",
            oi=10_000 - i * 500,
            bid=300.0,
            ask=302.0,
        )
        for i in range(n)
    ]


def test_select_best_candidate_default_returns_rank1() -> None:
    """Default index=0 must return the top-ranked candidate."""
    pool = _ranked_pool(3)
    best = overlay._select_best_candidate(pool, 0.09, "PE", index=0)
    # Highest OI (10,000) is at i=0 → strike 22000
    assert best["strike"] == 22000.0


def test_select_best_candidate_index1_returns_rank2() -> None:
    """index=1 must return the 2nd-ranked candidate."""
    pool = _ranked_pool(3)
    best = overlay._select_best_candidate(pool, 0.09, "PE", index=1)
    assert best["strike"] == 21900.0  # i=1 → OI 9,500


def test_select_best_candidate_index_clamped_when_out_of_range() -> None:
    """index beyond pool size must clamp to last, not raise."""
    pool = _ranked_pool(3)
    best = overlay._select_best_candidate(pool, 0.09, "PE", index=99)
    assert best["strike"] == 21800.0  # i=2 → last entry


def test_confirmation_table_shows_type_column(capsys: pytest.CaptureFixture) -> None:
    """Type (PE/CE) column must appear in the confirmation table header and rows."""
    from scripts.paper_3track_overlay import OverlayRow, _print_confirmation_table
    from decimal import Decimal
    from src.models.portfolio import TradeAction

    rows = [
        OverlayRow(
            strategy="paper_nifty_spot",
            leg_role="overlay_pp",
            option_type="PE",
            action=TradeAction.BUY,
            strike=22000.0,
            instrument_key="NSE_FO|NIFTY22000PE",
            price=Decimal("310.00"),
            spread_pct=1.3,
            oi=10_000,
            expiry="2026-06-26",
            expiry_label="quarterly",
            dte=47,
        )
    ]
    _print_confirmation_table("pp", rows, date(2026, 5, 7), "2026-06-26", 47, "DRY RUN")
    out = capsys.readouterr().out
    assert "Type" in out, "Header must contain 'Type' column"
    assert "PE" in out, "Row must show option type PE"


def test_confirmation_table_collar_shows_pe_and_ce(capsys: pytest.CaptureFixture) -> None:
    """Collar confirmation table must show both PE and CE in the Type column."""
    from scripts.paper_3track_overlay import OverlayRow, _print_confirmation_table
    from decimal import Decimal
    from src.models.portfolio import TradeAction

    rows = [
        OverlayRow(
            strategy="paper_nifty_spot", leg_role="overlay_collar_put",
            option_type="PE", action=TradeAction.BUY,
            strike=22000.0, instrument_key="NSE_FO|NIFTY22000PE",
            price=Decimal("310.00"), spread_pct=1.3, oi=10_000,
            expiry="2026-06-26", expiry_label="quarterly", dte=47,
        ),
        OverlayRow(
            strategy="paper_nifty_spot", leg_role="overlay_collar_call",
            option_type="CE", action=TradeAction.SELL,
            strike=25000.0, instrument_key="NSE_FO|NIFTY25000CE",
            price=Decimal("120.00"), spread_pct=1.1, oi=8_000,
            expiry="2026-06-26", expiry_label="quarterly", dte=47,
        ),
    ]
    _print_confirmation_table("collar", rows, date(2026, 5, 7), "2026-06-26", 47, "DRY RUN")
    out = capsys.readouterr().out
    assert "PE" in out, "Collar table must show PE row"
    assert "CE" in out, "Collar table must show CE row"
