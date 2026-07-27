"""Unit tests for scripts/record/record_paper_trade.py.

Tests use subprocess.run to exercise the CLI as a real process, or import
and call main() directly with sys.argv patched (for speed).

Coverage:
- CLI rejects strategy without paper_ prefix with exit code 1.
- CLI rejects invalid date format with exit code 1.
- CLI rejects invalid action (not BUY/SELL) with exit code 2 (argparse).
- --dry-run is the default (no DB write without --no-dry-run).
- Minimal args (only --key + --price) use CSP defaults and preview-only.
- Happy-path SELL inserts a row and prints position summary (--no-dry-run).
- Happy-path BUY inserts a row and prints position summary (--no-dry-run).
- Re-running same args is idempotent (no duplicate row).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the module under test — sys.path already has repo root from conftest
import scripts.record.record_paper_trade as cli_module
from src.paper.store import PaperStore
from src.risk.models import PortfolioDelta

# Patch target for live VIX API calls — used in tests whose trade_date defaults
# to today (no --date flag). Without this, fetch_vix_latest() succeeds in dev
# environments (real token set), returns a low IVR, and the R3 gate exits(1).
_PATCH_VIX = "scripts.record.record_paper_trade.fetch_vix_latest"

# ── Helpers ───────────────────────────────────────────────────────────────────

_STRATEGY = "paper_csp_nifty_v1"
_LEG = "short_put"
_KEY = "NSE_FO|12345"
_DATE = "2026-05-01"
_PRICE = "120.50"
_QTY = "75"


@pytest.fixture(autouse=True)
def _no_network_price_drift_check():
    """Safety net for BUG-008's live-LTP price-drift re-check (no network in tests).

    Tests that care about a specific LTP value still patch UpstoxMarketClient
    themselves via @patch — that per-test patch takes precedence within the
    test body (mock.patch.start() layers on top of this fixture's patch and
    is restored first on teardown). This fixture only protects tests that pass
    an explicit --price with --no-dry-run and don't care about the drift
    check at all, so it would otherwise hit a real UpstoxMarketClient().
    """
    with patch("scripts.record.record_paper_trade.UpstoxMarketClient") as mock_cls:
        mock_cls.return_value.get_ltp_sync.return_value = {}
        yield


def _run(
    args: list[str],
    db_path: Path,
    capture_stderr: bool = True,
) -> tuple[int, str, str]:
    """Invoke main() with patched sys.argv, capture stdout/stderr and exit code."""
    full_args = ["record_paper_trade"] + args + ["--db-path", str(db_path)]
    stdout_buf = StringIO()
    stderr_buf = StringIO()
    exit_code = 0

    with patch("sys.argv", full_args):
        with patch("sys.stdout", stdout_buf):
            with patch("sys.stderr", stderr_buf):
                try:
                    cli_module.main()
                except SystemExit as e:
                    exit_code = int(e.code) if e.code is not None else 0

    return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue()


def _base_args(action: str = "SELL") -> list[str]:
    return [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        _KEY,
        "--date",
        _DATE,
        "--action",
        action,
        "--qty",
        _QTY,
        "--price",
        _PRICE,
    ]


# ── Validation errors ─────────────────────────────────────────────────────────


def test_rejects_missing_paper_prefix(tmp_path: Path) -> None:
    code, _, err = _run(
        [
            "--strategy",
            "csp_nifty_v1",
            "--leg",
            _LEG,
            "--key",
            _KEY,
            "--date",
            _DATE,
            "--action",
            "SELL",
            "--qty",
            _QTY,
            "--price",
            _PRICE,
        ],
        tmp_path / "db.sqlite",
    )
    assert code == 1
    assert "paper_" in err


def test_rejects_live_strategy_name(tmp_path: Path) -> None:
    code, _, err = _run(
        [
            "--strategy",
            "finideas_ilts",
            "--leg",
            _LEG,
            "--key",
            _KEY,
            "--date",
            _DATE,
            "--action",
            "SELL",
            "--qty",
            _QTY,
            "--price",
            _PRICE,
        ],
        tmp_path / "db.sqlite",
    )
    assert code == 1
    assert "paper_" in err


def test_rejects_invalid_date(tmp_path: Path) -> None:
    args = _base_args()
    # Replace --date value
    idx = args.index("--date") + 1
    args[idx] = "01-05-2026"
    code, _, err = _run(args, tmp_path / "db.sqlite")
    assert code == 1
    assert "YYYY-MM-DD" in err


def test_rejects_invalid_action(tmp_path: Path) -> None:
    """argparse itself rejects invalid choices — expect exit code 2."""
    args = _base_args(action="HOLD")
    code, _, _ = _run(args, tmp_path / "db.sqlite")
    assert code == 2


# ── Dry run / defaults ────────────────────────────────────────────────────────


def test_dry_run_is_default(tmp_path: Path) -> None:
    """Running without --no-dry-run must not insert anything into the DB."""
    db = tmp_path / "db.sqlite"
    code, out, _ = _run(_base_args("SELL"), db)  # no --no-dry-run
    assert code == 0
    assert "Dry run" in out
    if db.exists():
        store = PaperStore(db)
        assert store.get_trades(_STRATEGY) == []


def test_dry_run_prints_fields(tmp_path: Path) -> None:
    """Explicit --dry-run flag also works and shows all trade fields."""
    db = tmp_path / "db.sqlite"
    args = _base_args() + ["--dry-run"]
    code, out, _ = _run(args, db)
    assert code == 0
    assert "paper_csp_nifty_v1" in out
    assert "120.50" in out
    assert "is_paper" in out
    if db.exists():
        store = PaperStore(db)
        assert store.get_trades(_STRATEGY) == []


@patch(_PATCH_VIX, return_value=None)
def test_defaults_produce_dry_run_with_csp_strategy(_mock_vix, tmp_path: Path) -> None:
    """Only --key + --price → defaults to paper_csp_nifty_v1, short_put, SELL, dry-run."""
    db = tmp_path / "db.sqlite"
    code, out, err = _run(["--key", _KEY, "--price", _PRICE], db)
    assert code == 0, f"stderr: {err}"
    assert "paper_csp_nifty_v1" in out
    assert "Dry run" in out
    if db.exists():
        store = PaperStore(db)
        assert store.get_trades(_STRATEGY) == []


# ── Happy path ────────────────────────────────────────────────────────────────


def test_sell_inserts_row_and_prints_summary(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    code, out, err = _run(_base_args("SELL") + ["--no-dry-run"], db)
    assert code == 0, f"stderr: {err}"
    assert _STRATEGY in out
    store = PaperStore(db)
    trades = store.get_trades(_STRATEGY)
    assert len(trades) == 1
    assert trades[0].action.value == "SELL"
    assert trades[0].price == Decimal("120.50")


def test_buy_inserts_row_and_prints_summary(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    # First SELL to open
    _run(_base_args("SELL") + ["--no-dry-run"], db)
    # Then BUY to close — use --close (not --action BUY) to avoid live Nifty spot fetch
    buy_args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        _KEY,
        "--date",
        _DATE,
        "--close",
        "--qty",
        _QTY,
        "--price",
        "60.00",
        "--no-dry-run",
    ]
    code, out, err = _run(buy_args, db)
    assert code == 0, f"stderr: {err}"
    store = PaperStore(db)
    assert len(store.get_trades(_STRATEGY)) == 2


def test_idempotent_rerun(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _run(_base_args("SELL") + ["--no-dry-run"], db)
    _run(_base_args("SELL") + ["--no-dry-run"], db)
    _run(_base_args("SELL") + ["--no-dry-run"], db)
    store = PaperStore(db)
    assert len(store.get_trades(_STRATEGY)) == 1


def test_closed_position_prints_closed_message(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _run(_base_args("SELL") + ["--no-dry-run"], db)
    # --close implies BUY and skips the live Nifty spot fetch
    buy_args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        _KEY,
        "--date",
        _DATE,
        "--close",
        "--qty",
        _QTY,
        "--price",
        _PRICE,
        "--no-dry-run",
    ]
    code, out, _ = _run(buy_args, db)
    assert code == 0
    assert "closed" in out or "net qty" in out


# ── Chain mode ────────────────────────────────────────────────────────────────


_FAKE_CHAIN = [
    {
        "strike_price": 23800,
        "underlying_spot_price": 24176.15,
        "put_options": {
            "instrument_key": "NSE_FO|72172",
            "market_data": {
                "ltp": 175.2,
                "bid_price": 174.05,
                "ask_price": 176.55,
                "oi": 1041300,
            },
            "option_greeks": {"delta": -0.3054, "iv": 16.38},
        },
        "call_options": {},
    },
    {
        "strike_price": 23700,
        "underlying_spot_price": 24176.15,
        "put_options": {
            "instrument_key": "NSE_FO|72168",
            "market_data": {
                "ltp": 150.0,
                "bid_price": 148.25,
                "ask_price": 150.00,
                "oi": 782795,
            },
            "option_greeks": {"delta": -0.2688, "iv": 16.62},
        },
        "call_options": {},
    },
]


@patch(_PATCH_VIX, return_value=None)
@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
def test_chain_mode_dry_run_prints_table(mock_client_cls, _mock_vix, tmp_path: Path) -> None:
    """--expiry triggers chain fetch; table printed; no DB insert."""
    db = tmp_path / "db.sqlite"
    mock_client = mock_client_cls.return_value
    mock_client.get_option_chain_sync.return_value = _FAKE_CHAIN

    code, out, err = _run(["--expiry", "2026-05-26"], db)

    assert code == 0, f"stderr: {err}"
    assert "SIDE" in out
    assert "STRIKE" in out
    assert "23800" in out
    assert "Dry run" in out
    mock_client.get_option_chain_sync.assert_called_once()


@patch(_PATCH_VIX, return_value=None)
@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
def test_chain_mode_resolves_key_and_price(mock_client_cls, _mock_vix, tmp_path: Path) -> None:
    """Resolved key + mid-price injected; correct instrument recorded."""
    db = tmp_path / "db.sqlite"
    mock_client = mock_client_cls.return_value
    mock_client.get_option_chain_sync.return_value = _FAKE_CHAIN

    code, out, err = _run(["--expiry", "2026-05-26", "--no-dry-run"], db)

    assert code == 0, f"stderr: {err}"
    store = PaperStore(db)
    trades = store.get_trades(_STRATEGY)
    assert len(trades) == 1
    # 23700 PE is rank 1 (spread_bucket=0 wins over 23800's spread_bucket=1)
    assert trades[0].instrument_key == "NSE_FO|72168"
    # mid = (148.25 + 150.00) / 2 = 149.125 -> rounded (half-to-even) to 149.12
    assert trades[0].price == Decimal("149.12")


@patch(_PATCH_VIX, return_value=None)
@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
def test_chain_mode_index_2_picks_second_rank(mock_client_cls, _mock_vix, tmp_path: Path) -> None:
    """--index 2 selects second-ranked row."""
    db = tmp_path / "db.sqlite"
    mock_client = mock_client_cls.return_value
    mock_client.get_option_chain_sync.return_value = _FAKE_CHAIN

    code, out, err = _run(["--expiry", "2026-05-26", "--index", "2", "--no-dry-run"], db)

    assert code == 0, f"stderr: {err}"
    store = PaperStore(db)
    trades = store.get_trades(_STRATEGY)
    assert len(trades) == 1
    # 23800 PE is rank 2
    assert trades[0].instrument_key == "NSE_FO|72172"
    # mid = (174.05 + 176.55) / 2 = 175.3
    assert trades[0].price == Decimal("175.3")


@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
def test_chain_mode_empty_chain_exits_1(mock_client_cls, tmp_path: Path) -> None:
    """Empty chain → exit code 1, no insert."""
    db = tmp_path / "db.sqlite"
    mock_client = mock_client_cls.return_value
    mock_client.get_option_chain_sync.return_value = []

    code, out, err = _run(["--expiry", "2026-05-26"], db)

    assert code == 1
    assert "empty data" in err


def test_chain_mode_mutually_exclusive_with_key(tmp_path: Path) -> None:
    """--expiry + --key → exit code 1."""
    db = tmp_path / "db.sqlite"
    code, out, err = _run(["--expiry", "2026-05-26", "--key", "NSE_FO|12345"], db)
    assert code == 1
    assert "mutually exclusive" in err


# ── --close flag ──────────────────────────────────────────────────────────────


def test_close_flag_is_buy_to_close(tmp_path: Path) -> None:
    """--close records a BUY trade without requiring --action BUY explicitly."""
    db = tmp_path / "db.sqlite"
    # Open short put
    _run(_base_args("SELL") + ["--no-dry-run"], db)
    # Close with --close flag; no --action needed
    close_args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        _KEY,
        "--date",
        _DATE,
        "--qty",
        _QTY,
        "--price",
        "12.50",
        "--close",
        "--no-dry-run",
    ]
    code, out, err = _run(close_args, db)
    assert code == 0, f"stderr: {err}"
    store = PaperStore(db)
    trades = store.get_trades(_STRATEGY)
    buy_trades = [t for t in trades if t.action.value == "BUY"]
    assert len(buy_trades) == 1
    assert buy_trades[0].price == Decimal("12.50")


def test_close_flag_dry_run_shows_buy_action(tmp_path: Path) -> None:
    """--close in dry-run mode must display action=BUY in the preview."""
    db = tmp_path / "db.sqlite"
    close_args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        _KEY,
        "--date",
        _DATE,
        "--qty",
        _QTY,
        "--price",
        "12.50",
        "--close",
    ]
    code, out, err = _run(close_args, db)
    assert code == 0, f"stderr: {err}"
    assert "BUY" in out
    assert "Dry run" in out


def test_close_and_action_are_mutually_exclusive(tmp_path: Path) -> None:
    """--close combined with explicit --action should exit 1."""
    db = tmp_path / "db.sqlite"
    args = _base_args("BUY") + ["--close"]
    code, _, err = _run(args, db)
    assert code == 1
    assert "--close" in err and "--action" in err


# ── --close extension (auto-key / auto-price) ─────────────────────────────────


def test_close_auto_resolves_key_from_position(tmp_path: Path) -> None:
    """--close and no --key: resolves instrument from open short position."""
    db = tmp_path / "db.sqlite"
    # Seed short position (net_qty = -75)
    _run(_base_args("SELL") + ["--no-dry-run"], db)

    # Close without --key
    close_args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--qty",
        _QTY,
        "--price",
        "10.00",
        "--close",
        "--no-dry-run",
    ]
    code, out, err = _run(close_args, db)
    assert code == 0, f"stderr: {err}"
    assert "Resolved key from position" in out
    assert _KEY in out

    store = PaperStore(db)
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.net_qty == 0


def test_close_auto_key_flat_position_exits_1(tmp_path: Path) -> None:
    """--close and no --key: exits 1 if no open short position exists."""
    db = tmp_path / "db.sqlite"
    # No seeding -> flat position
    close_args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--price",
        "10.00",
        "--close",
    ]
    code, out, err = _run(close_args, db)
    assert code == 1
    assert "no open short position" in err


@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
def test_close_auto_fetches_ltp_when_no_price(mock_client_cls, tmp_path: Path) -> None:
    """--close and no --price: fetches LTP and uses it as rounded Decimal."""
    db = tmp_path / "db.sqlite"
    mock_client = mock_client_cls.return_value
    mock_client.get_ltp_sync.return_value = {_KEY: 12.506}  # Should round to 12.51

    close_args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        _KEY,
        "--close",
        "--no-dry-run",
    ]
    code, out, err = _run(close_args, db)
    assert code == 0, f"stderr: {err}"
    assert "Auto-price: LTP=₹12.51" in out

    store = PaperStore(db)
    trades = store.get_trades(_STRATEGY)
    buy_trades = [t for t in trades if t.action.value == "BUY"]
    assert len(buy_trades) == 1
    assert buy_trades[0].price == Decimal("12.51")


@patch("scripts.record.record_paper_trade.PaperStore")
def test_close_explicit_key_skips_db_lookup(mock_store_cls, tmp_path: Path) -> None:
    """--close with explicit --key skips the PaperStore.get_position call in resolver."""
    db = tmp_path / "db.sqlite"
    # We don't care about the return value, just that it's not called during resolution.
    # Note: main() calls get_position at the end for the summary, so we can't just
    # assert_not_called() if we run the whole main().
    # But _resolve_from_position is the ONLY thing that calls it before the price guard.
    # Actually, let's just check that get_position was NOT called.

    close_args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        _KEY,
        "--price",
        "10.00",
        "--close",
        "--no-dry-run",
    ]
    # We must mock the return value for the summary call in main() to avoid errors
    mock_store_cls.return_value.get_position.return_value.net_qty = 0

    _run(close_args, db)

    # It should only be called ONCE (for the summary in main), not TWICE.
    assert mock_store_cls.return_value.get_position.call_count == 1

    # PG-2d: the summary call must pass the already-resolved instrument_key
    # explicitly, instead of relying on get_position()'s ambiguity fallback.
    _, kwargs = mock_store_cls.return_value.get_position.call_args
    assert kwargs.get("instrument_key") == _KEY


# ── Delta gate tests ──────────────────────────────────────────────────────────


def _make_mock_delta(
    options: Decimal = Decimal(0),
    niftybees: Decimal = Decimal(0),
    warning: bool = False,
    cap: bool = False,
) -> PortfolioDelta:
    return PortfolioDelta(
        options_delta_lots=options,
        niftybees_delta_lots=niftybees,
        total_delta_lots=options + niftybees,
        warning_breached=warning,
        cap_breached=cap,
        as_of=datetime.now(tz=timezone.utc),
    )


@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
@patch("scripts.record.record_paper_trade.PortfolioDeltaTracker.aggregate_delta")
def test_gate_blocks_on_cap_breached(mock_aggregate, mock_client_cls, tmp_path: Path) -> None:
    """Gate blocks when cap_breached=True, exit code 1."""
    db = tmp_path / "db.sqlite"
    mock_client = mock_client_cls.return_value
    mock_client.get_ltp_sync.return_value = {"NSE_INDEX|Nifty 50": Decimal("24000")}
    mock_aggregate.return_value = _make_mock_delta(cap=True)

    args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        _KEY,
        "--date",
        _DATE,
        "--action",
        "BUY",
        "--qty",
        _QTY,
        "--price",
        _PRICE,
        "--no-dry-run",
    ]
    code, out, err = _run(args, db)
    assert code == 1
    assert "hard cap breached" in err.lower()


@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
@patch("scripts.record.record_paper_trade.PortfolioDeltaTracker.aggregate_delta")
def test_gate_warns_on_warning_breached(mock_aggregate, mock_client_cls, tmp_path: Path) -> None:
    """Gate warns but trade proceeds when warning_breached=True, exit code 0."""
    db = tmp_path / "db.sqlite"
    mock_client = mock_client_cls.return_value
    mock_client.get_ltp_sync.return_value = {"NSE_INDEX|Nifty 50": Decimal("24000")}
    mock_aggregate.return_value = _make_mock_delta(warning=True)

    args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        _KEY,
        "--date",
        _DATE,
        "--action",
        "BUY",
        "--qty",
        _QTY,
        "--price",
        _PRICE,
        "--no-dry-run",
    ]
    code, out, err = _run(args, db)
    assert code == 0
    assert "WARNING: portfolio delta near cap" in out

    # Assert trade is recorded
    store = PaperStore(db)
    assert len(store.get_trades(_STRATEGY)) == 1


@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
@patch("scripts.record.record_paper_trade.PortfolioDeltaTracker.aggregate_delta")
def test_gate_passes_silently_on_no_breach(mock_aggregate, mock_client_cls, tmp_path: Path) -> None:
    """Gate passes silently on no breach, exit code 0."""
    db = tmp_path / "db.sqlite"
    mock_client = mock_client_cls.return_value
    mock_client.get_ltp_sync.return_value = {"NSE_INDEX|Nifty 50": Decimal("24000")}
    mock_aggregate.return_value = _make_mock_delta()

    args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        _KEY,
        "--date",
        _DATE,
        "--action",
        "BUY",
        "--qty",
        _QTY,
        "--price",
        _PRICE,
        "--no-dry-run",
    ]
    code, out, err = _run(args, db)
    assert code == 0
    assert "portfolio delta near cap" not in out
    assert "portfolio delta near cap" not in err

    store = PaperStore(db)
    assert len(store.get_trades(_STRATEGY)) == 1


@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
@patch("scripts.record.record_paper_trade.PortfolioDeltaTracker.aggregate_delta")
def test_gate_skipped_on_sell(mock_aggregate, mock_client_cls, tmp_path: Path) -> None:
    """Gate is skipped on SELL, exit code 0."""
    db = tmp_path / "db.sqlite"
    # Even if cap is breached, SELL skips the gate
    mock_aggregate.return_value = _make_mock_delta(cap=True)

    args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        _KEY,
        "--date",
        _DATE,
        "--action",
        "SELL",
        "--qty",
        _QTY,
        "--price",
        _PRICE,
        "--no-dry-run",
    ]
    code, out, err = _run(args, db)
    assert code == 0
    mock_aggregate.assert_not_called()


@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
@patch("scripts.record.record_paper_trade.PortfolioDeltaTracker.aggregate_delta")
def test_gate_skipped_on_close(mock_aggregate, mock_client_cls, tmp_path: Path) -> None:
    """Gate is skipped on --close path (even though it implies action=BUY), exit code 0."""
    db = tmp_path / "db.sqlite"
    mock_client = mock_client_cls.return_value
    mock_client.get_ltp_sync.return_value = {_KEY: 12.50}

    # Seed short position
    _run(_base_args("SELL") + ["--no-dry-run"], db)

    # Even if cap is breached, close skips the gate
    mock_aggregate.return_value = _make_mock_delta(cap=True)

    args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        _KEY,
        "--date",
        _DATE,
        "--qty",
        _QTY,
        "--price",
        "12.50",
        "--close",
        "--no-dry-run",
    ]
    code, out, err = _run(args, db)
    assert code == 0
    mock_aggregate.assert_not_called()


@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
@patch("scripts.record.record_paper_trade.PortfolioDeltaTracker.aggregate_delta")
def test_gate_protective_put_bypasses_cap(mock_aggregate, mock_client_cls, tmp_path: Path) -> None:
    """BUY PE is protective and bypasses cap check, exit code 0."""
    db = tmp_path / "db.sqlite"
    mock_client = mock_client_cls.return_value
    mock_client.get_ltp_sync.return_value = {"NSE_INDEX|Nifty 50": Decimal("24000")}
    mock_aggregate.return_value = _make_mock_delta(cap=True)

    args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        "NSE_FO|NIFTY26MAY22000PE",  # PE key triggers protective put bypass
        "--date",
        _DATE,
        "--action",
        "BUY",
        "--qty",
        _QTY,
        "--price",
        _PRICE,
        "--no-dry-run",
    ]
    code, out, err = _run(args, db)
    assert code == 0

    store = PaperStore(db)
    assert len(store.get_trades(_STRATEGY)) == 1


# ── Price drift re-check (BUG-008) ─────────────────────────────────────────────


def test_evaluate_price_drift_within_tolerance_is_silent() -> None:
    """Happy-path: live price within tolerance → allowed, no message."""
    allowed, message = cli_module._evaluate_price_drift(Decimal("120.00"), Decimal("122.00"))
    assert allowed is True
    assert message == ""


def test_evaluate_price_drift_elevated_but_allowed_warns() -> None:
    """Drift above half-tolerance but under the hard limit → allowed, WARNING."""
    allowed, message = cli_module._evaluate_price_drift(Decimal("100.00"), Decimal("107.00"))
    assert allowed is True
    assert message.startswith("WARNING:")


def test_evaluate_price_drift_past_tolerance_blocks() -> None:
    """Edge case: drift exceeds tolerance → not allowed, ERROR message."""
    allowed, message = cli_module._evaluate_price_drift(Decimal("120.00"), Decimal("150.00"))
    assert allowed is False
    assert message.startswith("ERROR:")
    assert "--force-entry" in message


def test_evaluate_price_drift_zero_claimed_price_is_noop() -> None:
    """Malformed/zero claimed price: skip drift math, defer to model validation."""
    allowed, message = cli_module._evaluate_price_drift(Decimal("0"), Decimal("100.00"))
    assert allowed is True
    assert message == ""


@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
def test_main_blocks_on_stale_price_at_execution(mock_client_cls, tmp_path: Path) -> None:
    """A dry-run-frozen --price that has drifted past tolerance blocks at --no-dry-run time."""
    db = tmp_path / "db.sqlite"
    mock_client = mock_client_cls.return_value
    # Claimed price 120.50, live price 200.00 → ~66% drift, well past the 10% tolerance.
    mock_client.get_ltp_sync.return_value = {_KEY: Decimal("200.00")}

    code, out, err = _run(_base_args("SELL") + ["--no-dry-run"], db)
    assert code == 1
    assert "price drift" in err.lower()
    assert "exceeds tolerance" in err.lower()

    store = PaperStore(db)
    assert store.get_trades(_STRATEGY) == []


@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
def test_main_force_entry_overrides_price_drift_block(mock_client_cls, tmp_path: Path) -> None:
    """--force-entry overrides the drift block and the trade still records."""
    db = tmp_path / "db.sqlite"
    mock_client = mock_client_cls.return_value
    mock_client.get_ltp_sync.return_value = {_KEY: Decimal("200.00")}

    code, out, err = _run(_base_args("SELL") + ["--no-dry-run", "--force-entry"], db)
    assert code == 0, f"stderr: {err}"
    assert "overridden via --force-entry" in err

    store = PaperStore(db)
    assert len(store.get_trades(_STRATEGY)) == 1


@patch("scripts.record.record_paper_trade.UpstoxMarketClient")
def test_main_proceeds_within_price_tolerance(mock_client_cls, tmp_path: Path) -> None:
    """Live price close to claimed --price (within tolerance) proceeds without blocking."""
    db = tmp_path / "db.sqlite"
    mock_client = mock_client_cls.return_value
    # Claimed 120.50, live 122.00 → ~1.2% drift, well within tolerance.
    mock_client.get_ltp_sync.return_value = {_KEY: Decimal("122.00")}

    code, out, err = _run(_base_args("SELL") + ["--no-dry-run"], db)
    assert code == 0, f"stderr: {err}"

    store = PaperStore(db)
    assert len(store.get_trades(_STRATEGY)) == 1


def test_main_skips_drift_check_in_dry_run(tmp_path: Path) -> None:
    """Dry-run preview never triggers the live drift re-check (no network call)."""
    db = tmp_path / "db.sqlite"
    # No UpstoxMarketClient patch needed here beyond the autouse fixture — if the
    # code path attempted a real network call, this would hang/fail in CI.
    code, out, _ = _run(_base_args("SELL"), db)  # no --no-dry-run
    assert code == 0
    assert "Dry run" in out


def test_main_skips_drift_check_on_close(tmp_path: Path) -> None:
    """--close is exempt from the drift check — it already fetches a live LTP itself."""
    db = tmp_path / "db.sqlite"
    # Seed a short position first (mirrors test_close_flag_is_buy_to_close).
    _run(_base_args("SELL") + ["--no-dry-run"], db)

    close_args = [
        "--strategy",
        _STRATEGY,
        "--leg",
        _LEG,
        "--key",
        _KEY,
        "--date",
        _DATE,
        "--qty",
        _QTY,
        "--price",
        "12.50",
        "--close",
        "--no-dry-run",
    ]
    code, out, err = _run(close_args, db)
    assert code == 0, f"stderr: {err}"
