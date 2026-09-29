from datetime import date
from decimal import Decimal

import pytest

from src.signals.models import (
    FIIData,
    MarketSnapshot,
    OILevel,
    OptionChainSummary,
    StrikePremium,
)
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
            premiums=[
                StrikePremium(strike=23950, call_ltp=Decimal("130.25"), put_ltp=Decimal("62.5")),
                StrikePremium(strike=24000, call_ltp=Decimal("102.0"), put_ltp=Decimal("88.75")),
                StrikePremium(strike=24050, call_ltp=Decimal("78.5"), put_ltp=Decimal("118.0")),
            ],
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


def test_build_prompt_premiums_line(snapshot: MarketSnapshot) -> None:
    prompt = build_prompt(snapshot, "gpt4o")
    user_content = prompt[1]["content"]
    assert "23950 CE:130.25 PE:62.5" in user_content
    assert "24000 CE:102.0 PE:88.75" in user_content
    assert "24050 CE:78.5 PE:118.0" in user_content
    assert "never null" in user_content


def test_build_prompt_premiums_zero_renders_as_na(snapshot: MarketSnapshot) -> None:
    """Decimal("0") means the leg was absent from the chain — must render N/A,
    never a bare 0 the model could mistake for a real zero-premium quote."""
    missing_leg_chain = OptionChainSummary(
        **{
            **snapshot.option_chain.model_dump(),
            "premiums": [
                StrikePremium(strike=24000, call_ltp=Decimal("0"), put_ltp=Decimal("88.75")),
            ],
        }
    )
    snap = snapshot.model_copy(update={"option_chain": missing_leg_chain})
    prompt = build_prompt(snap, "gpt4o")
    user_content = prompt[1]["content"]
    assert "24000 CE:N/A PE:88.75" in user_content
    assert "estimate from the nearest strike" in user_content


def test_build_prompt_unknown_provider(snapshot: MarketSnapshot) -> None:
    with pytest.raises(KeyError, match="Unknown signal provider: unknown"):
        build_prompt(snapshot, "unknown")


def test_build_prompt_gift_nifty_chg_sign(snapshot: MarketSnapshot) -> None:
    prompt = build_prompt(snapshot, "gpt4o")
    user_content = prompt[1]["content"]
    # (24100 - 23900)/23900 = 200/23900 = 0.8368%
    assert "+0.84%" in user_content
