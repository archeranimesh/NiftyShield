"""YF-6: chain-source wiring of the three overlay bootstraps.

The default (monthly, Upstox) path is pinned first: it must keep calling
``UpstoxMarketClient.get_option_chain_sync`` and select the same contract.
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.strategies.three_track import paper_3track_overlay_entry as oe
from src.client.chain_rows import rows_fetch
from src.client.chain_source import ChainRouter, DhanChainSource, UpstoxChainSource
from src.client.contract_resolver import MasterContractResolver, UpstoxContractMaster
from src.client.dhan_market import parse_dhan_option_chain
from src.client.source_health import SourceHealth
from src.instruments.lookup import InstrumentLookup
from src.models.contract import SourceId
from src.strategy.overlay_tenor import OVERLAY_TENORS

FIX = Path(__file__).resolve().parents[2] / "fixtures"
BOD = FIX / "contract_resolver" / "upstox_bod_nifty_dec.json"
DEC_2026_MS = 1798568999000
TODAY = date(2026, 11, 3)
NIFTY = "NSE_INDEX|Nifty 50"
SPOT = 24000.0


def _bod_chain(expiry_ms: int, expiry: str) -> list[dict[str, Any]]:
    """Raw Upstox rows (with instrument_key) for one BOD expiry, synthetic quotes."""
    contracts: dict[float, dict[str, dict[str, Any]]] = {}
    for inst in json.loads(BOD.read_text()):
        if inst["expiry"] == expiry_ms:
            contracts.setdefault(inst["strike_price"], {})[inst["instrument_type"]] = inst
    rows = []
    for strike, sides in sorted(contracts.items()):
        row: dict[str, Any] = {
            "expiry": expiry,
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


def _vix_patches() -> list[Any]:
    series = MagicMock()
    series.empty = False
    series.__len__.return_value = 300
    series.iloc = [15.0, 15.0]
    return [
        patch.object(oe, "load_vix_series", return_value=series),
        patch.object(oe, "compute_ivr", return_value=0.30),
    ]


def _run(fn: Any, **kwargs: Any) -> tuple[Any, Any]:
    patches = _vix_patches()
    for p in patches:
        p.start()
    try:
        return fn(BOD, today=TODAY, **kwargs)
    finally:
        for p in patches:
            p.stop()


@pytest.fixture
def upstox_client() -> Any:
    raw = _bod_chain(DEC_2026_MS, "2026-12-29")
    with patch.object(oe, "UpstoxMarketClient") as cls:
        cls.return_value.get_option_chain_sync.return_value = raw
        yield cls


@pytest.mark.parametrize(
    ("fn", "attrs"),
    [
        (oe.auto_cc_bootstrap, {"call_instrument_key": "NSE_FO|71505"}),
        (oe.auto_pp_bootstrap, {"put_instrument_key": "NSE_FO|62506"}),
        (
            oe.auto_collar_bootstrap,
            {"call_instrument_key": "NSE_FO|71505", "put_instrument_key": "NSE_FO|62506"},
        ),
    ],
)
def test_monthly_default_still_upstox(fn: Any, attrs: dict[str, str], upstox_client: Any) -> None:
    cfg, _ = _run(fn)
    assert cfg is not None
    assert cfg.expiry == "2026-12-29" and cfg.expiry_type == "monthly"
    for attr, key in attrs.items():
        assert getattr(cfg, attr) == key
    client = upstox_client.return_value
    client.get_option_chain_sync.assert_called_once_with(NIFTY, "2026-12-29")
    upstox_client.assert_called_once_with(oe.settings.upstox_analytics_token)
    assert OVERLAY_TENORS["monthly"].routed_chain is False


# ── YF-6: yearly tenor routes through ChainSource ──────────────────────────────

YEARLY = OVERLAY_TENORS["yearly"]
YEARLY_TODAY = date(2026, 12, 30)  # resolves Dec 2027 (2027-12-28)


class _ZeroGreeksUpstox:
    async def get_option_chain(self, underlying: str, expiry: str) -> list[dict[str, Any]]:
        return json.loads((FIX / "yearly_overlays" / "chain_dec2027_zero_greeks.json").read_text())


class _DhanFixture:
    def __init__(self) -> None:
        self.calls = 0

    async def get_option_chain(self, underlying: str, expiry: date) -> Any:
        self.calls += 1
        raw = json.loads((FIX / "dhan_chain" / "dec2027.json").read_text())
        return parse_dhan_option_chain(raw, expiry)


async def _no_sleep(_: float) -> None:
    return None


def _routed_fetch(dhan: _DhanFixture) -> Any:
    resolver = MasterContractResolver(
        {SourceId.UPSTOX: UpstoxContractMaster(InstrumentLookup.from_file(BOD), ["NIFTY"])}
    )
    router = ChainRouter(
        [
            (SourceId.UPSTOX, UpstoxChainSource(_ZeroGreeksUpstox(), resolver)),  # type: ignore[arg-type]
            (SourceId.DHAN, DhanChainSource(dhan, resolver)),  # type: ignore[arg-type]
        ],
        health=SourceHealth(),
        sleep=_no_sleep,
    )
    return rows_fetch(router.get_chain)


def _run_yearly(fn: Any, fetch: Any) -> tuple[Any, Any]:
    patches = _vix_patches()
    for p in patches:
        p.start()
    try:
        return fn(BOD, today=YEARLY_TODAY, policy=YEARLY, chain_fetch=fetch)
    finally:
        for p in patches:
            p.stop()


def test_yearly_zero_greeks_uses_dhan() -> None:
    dhan = _DhanFixture()
    with patch.object(oe, "UpstoxMarketClient") as upstox_cls:
        cfg, _ = _run_yearly(oe.auto_pp_bootstrap, _routed_fetch(dhan))
    assert dhan.calls == 1
    upstox_cls.assert_not_called()  # no direct Upstox chain call on the yearly path
    assert cfg is not None
    assert cfg.expiry == "2027-12-28" and cfg.expiry_type == "yearly"
    assert cfg.put_instrument_key.startswith("NSE_FO|")  # Upstox ledger key, not a Dhan id
    assert cfg.put_strike == 22000.0  # Dhan delta -0.196 sits in the PP ladder band


def test_yearly_default_fetch_is_the_routed_one() -> None:
    rows = _bod_chain(DEC_2026_MS, "2026-12-29")
    fake = MagicMock(return_value=rows)
    with (
        patch.object(oe, "create_overlay_chain_fetch", return_value=fake) as factory,
        patch.object(oe, "UpstoxMarketClient") as upstox_cls,
    ):
        cfg, _ = _run_yearly(oe.auto_cc_bootstrap, None)
    factory.assert_called_once()
    fake.assert_called_once_with(NIFTY, "2027-12-28")
    upstox_cls.assert_not_called()
    assert cfg is None or cfg.expiry_type == "yearly"


@pytest.mark.parametrize(
    "fn", [oe.auto_cc_bootstrap, oe.auto_pp_bootstrap, oe.auto_collar_bootstrap]
)
def test_all_unresolved_aborts_bootstrap(fn: Any) -> None:
    """An adapter that resolves no key yields no rows: structural abort, no config."""
    cfg, _ = _run_yearly(fn, lambda underlying, expiry: [])
    assert cfg is None


@pytest.mark.parametrize(
    "fn", [oe.auto_cc_bootstrap, oe.auto_pp_bootstrap, oe.auto_collar_bootstrap]
)
def test_fetch_failure_aborts_bootstrap(fn: Any) -> None:
    def boom(underlying: str, expiry: str) -> list[dict[str, Any]]:
        raise TimeoutError("chain fetch timed out")

    cfg, _ = _run_yearly(fn, boom)
    assert cfg is None


def test_injected_fetch_beats_policy_default() -> None:
    rows = _bod_chain(DEC_2026_MS, "2026-12-29")
    cfg, _ = _run(oe.auto_cc_bootstrap, chain_fetch=lambda underlying, expiry: rows)
    assert cfg is not None and cfg.call_instrument_key == "NSE_FO|71505"
