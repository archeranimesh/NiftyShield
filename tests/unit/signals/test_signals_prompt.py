from datetime import date
from decimal import Decimal

import pytest

from src.signals.models import FIIData, MarketSnapshot, OILevel, OptionChainSummary
from src.signals.prompt import build_prompt


@pytest.fixture
def snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        trade_date=date(2026, 9, 7),
        nifty_spot=Decimal("24000.50"),
        prev_close=Decimal("23900.00"),
        prev_high=Decimal("24050.00"),
        prev_low=Decimal("23850.00"),
        gift_nifty=Decimal("24100.00"),  # implies + change
        india_vix=Decimal("15.5"),
        vix_5d_trend="rising",
        usd_inr=Decimal("83.50"),
        monthly_expiry=date(2026, 9, 24),
        option_chain=OptionChainSummary(
            atm_strike=24000,
            atm_iv=Decimal("16.0"),
            iv_skew=Decimal("-0.5"),
            pcr_total=Decimal("0.85"),
            pcr_atm=Decimal("0.90"),
            top_call_oi=[OILevel(strike=24100, oi=100000, oi_change=5000)],
            top_put_oi=[OILevel(strike=23900, oi=150000, oi_change=-2000)],
        ),
        fii=FIIData(
            fii_cash_net_cr=Decimal("1500.5"),
            dii_cash_net_cr=Decimal("-500.0"),
        ),
    )


def test_build_prompt_gpt4o_suffix(snapshot: MarketSnapshot) -> None:
    prompt = build_prompt(snapshot, "gpt4o")
    user_content = prompt[1]["content"]
    assert "Analyse the structured data" in user_content
    assert prompt[0]["role"] == "system"


def test_build_prompt_grok_suffix(snapshot: MarketSnapshot) -> None:
    prompt = build_prompt(snapshot, "grok")
    user_content = prompt[1]["content"]
    assert "Search X/Twitter" in user_content


def test_build_prompt_gemini_suffix(snapshot: MarketSnapshot) -> None:
    prompt = build_prompt(snapshot, "gemini")
    user_content = prompt[1]["content"]
    assert "Search for: overnight" in user_content


def test_build_prompt_contains_atm_strike(snapshot: MarketSnapshot) -> None:
    prompt = build_prompt(snapshot, "gpt4o")
    user_content = prompt[1]["content"]
    assert "ATM strike is 24000." in user_content
    assert "Permitted strikes: 23950, 24000, 24050." in user_content


def test_build_prompt_oi_formatting(snapshot: MarketSnapshot) -> None:
    prompt = build_prompt(snapshot, "gpt4o")
    user_content = prompt[1]["content"]
    assert "24100 OI:100,000 Δ+5,000" in user_content
    assert "23900 OI:150,000 Δ-2,000" in user_content


def test_build_prompt_unknown_provider(snapshot: MarketSnapshot) -> None:
    with pytest.raises(KeyError, match="Unknown signal provider: unknown"):
        build_prompt(snapshot, "unknown")


def test_build_prompt_gift_nifty_chg_sign(snapshot: MarketSnapshot) -> None:
    prompt = build_prompt(snapshot, "gpt4o")
    user_content = prompt[1]["content"]
    # (24100 - 23900)/23900 = 200/23900 = 0.8368%
    assert "+0.84%" in user_content
