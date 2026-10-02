"""Tests for scripts/strategies/three_track/paper_expiry_settle.py (BUG-060, B060.2)."""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal

import pytest

from scripts.strategies.three_track.paper_expiry_settle import (
    notify_settlement,
    parse_contract_override,
)
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.strategy.expiry_settlement import (
    ContractSpec,
    ExpiredLeg,
    Settlement,
    SettlementFailure,
    SettlementReport,
)

EXPIRY = date(2026, 9, 29)


class _Notifier:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> bool:
        self.sent.append(text)
        return True


def test_parse_contract_override_happy_path():
    key, spec = parse_contract_override("NSE_FO|73994=25000:pe:2026-09-29")
    assert key == "NSE_FO|73994"
    assert spec == ContractSpec(Decimal("25000"), "PE", EXPIRY)


@pytest.mark.parametrize(
    "bad",
    [
        "NSE_FO|1=25000:PE",
        "NSE_FO|1=abc:PE:2026-09-29",
        "NSE_EQ|1=1:PE:2026-09-29",
        "x=1:FUT:2026-09-29",
    ],
)
def test_parse_contract_override_rejects_malformed(bad):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_contract_override(bad)


async def test_notify_warns_on_left_open_leg_escaped():
    notifier = _Notifier()
    report = SettlementReport(
        failures=[
            SettlementFailure(
                "paper_nifty_overlay", "overlay_collar_put", "NSE_FO|73994", "no NIFTY 50 close"
            )
        ]
    )
    await notify_settlement(notifier, report)  # type: ignore[arg-type]
    (msg,) = notifier.sent
    assert "`NSE_FO|73994`" in msg
    assert "Left OPEN" in msg
    assert "\\(BUG\\-060\\)" in msg


async def test_notify_lists_settled_leg():
    notifier = _Notifier()
    leg = ExpiredLeg(
        "paper_nifty_overlay",
        "overlay_pp",
        "NSE_FO|1",
        65,
        ContractSpec(Decimal("25000"), "PE", EXPIRY),
    )
    trade = PaperTrade(
        strategy_name="paper_nifty_overlay",
        leg_role="overlay_pp",
        instrument_key="NSE_FO|1",
        trade_date=EXPIRY,
        action=TradeAction.SELL,
        quantity=65,
        price=Decimal("784.65"),
    )
    report = SettlementReport(settled=[Settlement(leg, Decimal("24215.35"), trade)])
    await notify_settlement(notifier, report)  # type: ignore[arg-type]
    (msg,) = notifier.sent
    assert "25000 PE 29 SEP 26 SELL 65 @ ₹784\\.65" in msg


async def test_notify_noop_without_notifier_or_content():
    notifier = _Notifier()
    await notify_settlement(notifier, SettlementReport())  # type: ignore[arg-type]
    assert notifier.sent == []
    await notify_settlement(
        None, SettlementReport(failures=[SettlementFailure("a", "b", "c", "d")])
    )
