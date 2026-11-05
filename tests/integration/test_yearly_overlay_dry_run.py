"""YV-2: end-to-end dry run of the yearly overlay entrypoints (offline, default run).

Each test drives ``main()`` of ``paper_3track_overlay_entry`` with
``--expiry-type yearly --dry-run`` against the YF-2 BOD fixture, an injected
chain fetch (no broker client, no network), a frozen clock and a temp SQLite DB.
"""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import src.market_calendar.holidays as holidays
from scripts.strategies.three_track import paper_3track_overlay_entry as oe
from src.paper.store import PaperStore

FIX = Path(__file__).resolve().parents[1] / "fixtures"
BOD = FIX / "contract_resolver" / "upstox_bod_nifty_dec.json"
ZERO_GREEKS = FIX / "yearly_overlays" / "chain_dec2027_zero_greeks.json"
DEC_2026_MS = 1798568999000
DEC_2026 = "2026-12-29"
DEC_2027 = "2027-12-28"
SPOT = 24000.0
NIFTY = "NSE_INDEX|Nifty 50"

ChainFetch = Callable[[str, str], list[dict[str, Any]]]


def _dec_2026_chain() -> list[dict[str, Any]]:
    """Raw Upstox rows for the Dec 2026 BOD expiry with synthetic quotes and deltas."""
    contracts: dict[float, dict[str, dict[str, Any]]] = {}
    for inst in json.loads(BOD.read_text()):
        if inst["expiry"] == DEC_2026_MS:
            contracts.setdefault(inst["strike_price"], {})[inst["instrument_type"]] = inst
    rows = []
    for strike, sides in sorted(contracts.items()):
        row: dict[str, Any] = {
            "expiry": DEC_2026,
            "strike_price": strike,
            "underlying_spot_price": SPOT,
        }
        for side, field in (("CE", "call_options"), ("PE", "put_options")):
            if side not in sides:
                continue
            itm = (SPOT - strike) if side == "CE" else (strike - SPOT)
            delta = 1 / (1 + math.exp(-itm / 1500.0))
            row[field] = {
                "instrument_key": sides[side]["instrument_key"],
                "market_data": {
                    "ltp": 100.0,
                    "bid_price": 99.5,
                    "ask_price": 100.5,
                    "oi": 5000,
                    "volume": 10,
                },
                "option_greeks": {
                    "delta": delta if side == "CE" else -delta,
                    "gamma": 0.001,
                    "theta": -1.0,
                    "vega": 5.0,
                    "iv": 15.0,
                },
            }
        rows.append(row)
    return rows


@pytest.fixture
def freeze(monkeypatch: pytest.MonkeyPatch) -> Callable[[date], None]:
    """Return ``freeze(day)``: pin the overlay clock and strip Telegram env vars."""
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(var, raising=False)

    def _freeze(day: date) -> None:
        monkeypatch.setattr(holidays, "market_today", lambda: day)
        monkeypatch.setattr(oe, "market_today", lambda: day)

    return _freeze


@pytest.fixture
def run_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, freeze: Callable[[date], None]
) -> Iterator[Callable[..., tuple[Path, Any]]]:
    """Return ``run(flag, day, rows)`` that invokes ``main()`` and returns (db_path, fetch mock)."""
    series = MagicMock()
    series.empty = False
    series.__len__.return_value = 300
    series.iloc = [15.0, 15.0]
    monkeypatch.setattr(oe, "load_vix_series", lambda _dir: series)
    monkeypatch.setattr(oe, "compute_ivr", lambda *_a, **_k: 0.30)
    monkeypatch.setattr(oe, "setup_logging", lambda: None)
    monkeypatch.setattr(oe, "build_notifier", lambda: None)
    db_path = tmp_path / "paper.sqlite"
    PaperStore(db_path)  # production DB always has the schema; --auto-pp reads it pre-store

    def run(flag: str, day: date, rows: list[dict[str, Any]], *extra: str) -> tuple[Path, Any]:
        freeze(day)
        fetch = MagicMock(return_value=rows)
        argv = ["overlay_entry", flag, "--expiry-type", "yearly", "--dry-run", *extra]
        argv += ["--bod-path", str(BOD), "--db-path", str(db_path)]
        with (
            patch.object(sys, "argv", argv),
            patch.object(oe, "create_overlay_chain_fetch", return_value=fetch),
        ):
            oe.main()
        return db_path, fetch

    yield run


def _row_counts(db_path: Path) -> dict[str, int]:
    """Row count of every user table in the DB."""
    with sqlite3.connect(db_path) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}


def test_yearly_cc_dry_run_selects_december(run_main, capsys) -> None:
    """--auto-cc yearly resolves the December expiry and previews one short call."""
    _, fetch = run_main("--auto-cc", date(2026, 10, 6), _dec_2026_chain())
    out = capsys.readouterr().out
    fetch.assert_called_once_with(NIFTY, DEC_2026)
    assert f"Expiry: {DEC_2026} (yearly" in out
    assert "overlay_cc" in out and "paper_nifty_overlay_yearly_cc" in out


def test_yearly_pp_dry_run_selects_december(run_main, capsys) -> None:
    """--auto-pp yearly resolves the December expiry and previews one long put."""
    _, fetch = run_main("--auto-pp", date(2026, 10, 6), _dec_2026_chain())
    out = capsys.readouterr().out
    fetch.assert_called_once_with(NIFTY, DEC_2026)
    assert f"Expiry: {DEC_2026} (yearly" in out
    assert "overlay_pp" in out


def test_yearly_collar_dry_run_pair_same_expiry(run_main, capsys) -> None:
    """--auto-collar yearly previews both legs, both on the single December expiry."""
    _, fetch = run_main("--auto-collar", date(2026, 10, 6), _dec_2026_chain())
    out = capsys.readouterr().out
    fetch.assert_called_once_with(NIFTY, DEC_2026)
    assert out.count(f"Expiry: {DEC_2026} (yearly") == 1
    assert "overlay_collar_put" in out and "overlay_collar_call" in out


@pytest.mark.parametrize("flag", ["--auto-cc", "--auto-pp", "--auto-collar"])
def test_zero_greeks_chain_opens_no_leg(run_main, capsys, flag: str) -> None:
    """An all-zero-delta chain aborts with exit 1 and never opens a leg."""
    rows = json.loads(ZERO_GREEKS.read_text())
    with pytest.raises(SystemExit) as exc:
        run_main(flag, date(2026, 12, 30), rows)
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "bootstrap failed" in captured.err
    assert "overlay_" not in captured.out


@pytest.mark.parametrize("flag", ["--auto-cc", "--auto-pp", "--auto-collar"])
def test_dry_run_writes_nothing(run_main, flag: str) -> None:
    """A successful dry run leaves every table of the temp DB empty."""
    db_path, _ = run_main(flag, date(2026, 10, 6), _dec_2026_chain())
    counts = _row_counts(db_path)
    assert counts["paper_trades"] == 0
    assert sum(counts.values()) == 0, counts


def test_entry_below_floor_rolls_to_next_december(run_main, capsys) -> None:
    """Entry floor is 20 DTE: on 2026-12-15 (14 DTE to Dec 2026) the book picks Dec 2027."""
    _, fetch = run_main("--auto-cc", date(2026, 12, 15), _dec_2026_chain())
    fetch.assert_called_once_with(NIFTY, DEC_2027)
    assert f"Expiry: {DEC_2027} (yearly" in capsys.readouterr().out
