from src.signals.models import MarketSnapshot

NIFTY_STRIKE_STEP = 50

SUFFIXES = {
    "grok": (
        'Search X/Twitter right now for: "Nifty", "Bank Nifty", "NSE" '
        "posted in the last 2 hours. "
        "Weigh retail and institutional sentiment. Factor it into your direction call."
    ),
    "gemini": (
        "Search for: overnight S&P 500, Nasdaq, Nikkei 225, and crude oil levels. "
        "Factor global market direction into your call."
    ),
    "gpt4o": (
        "Analyse the structured data above only. Do not search the web. "
        "Pay particular attention to FII positioning and OI concentration as "
        "resistance/support proxies."
    ),
}


def build_prompt(snapshot: MarketSnapshot, provider_name: str) -> list[dict[str, str]]:
    """Build the system and user prompts for the signal provider."""
    if provider_name not in SUFFIXES:
        raise KeyError(f"Unknown signal provider: {provider_name}")

    provider_suffix = SUFFIXES[provider_name]

    gift_nifty_chg = (snapshot.gift_nifty - snapshot.prev_close) / snapshot.prev_close * 100
    atm_minus_1 = snapshot.option_chain.atm_strike - NIFTY_STRIKE_STEP
    atm_plus_1 = snapshot.option_chain.atm_strike + NIFTY_STRIKE_STEP

    top_call_oi_text = " | ".join(
        f"{level.strike} OI:{level.oi:,} Δ{level.oi_change:+,}"
        for level in snapshot.option_chain.top_call_oi
    )
    top_put_oi_text = " | ".join(
        f"{level.strike} OI:{level.oi:,} Δ{level.oi_change:+,}"
        for level in snapshot.option_chain.top_put_oi
    )

    system_prompt = (
        "You are a quantitative analyst for Indian derivatives markets.\n"
        "Respond ONLY in valid JSON. No markdown, no explanation outside JSON."
    )

    user_prompt = f"""Today is {snapshot.trade_date}. Monthly expiry: {snapshot.monthly_expiry}.

## Market Snapshot
- Nifty spot: {snapshot.nifty_spot}  |  Prev close: {snapshot.prev_close}
- Prev session: H {snapshot.prev_high} / L {snapshot.prev_low}
- Gift Nifty: {snapshot.gift_nifty}  |  Change implied: {gift_nifty_chg:+.2f}%
- India VIX: {snapshot.india_vix} ({snapshot.vix_5d_trend} over 5 days)
- USD/INR: {snapshot.usd_inr}

## Option Chain (as of 09:10 AM)
- ATM strike: {snapshot.option_chain.atm_strike}  |  ATM IV: {snapshot.option_chain.atm_iv:.1f}%
- IV skew (OTM call – OTM put): {snapshot.option_chain.iv_skew:+.2f}%  (positive = calls rich)
- PCR total: {snapshot.option_chain.pcr_total:.2f}  |  PCR ATM: {snapshot.option_chain.pcr_atm:.2f}
- Top CALL OI: {top_call_oi_text}
- Top PUT  OI: {top_put_oi_text}

## FII Positioning (yesterday)
- Index futures net: ₹{snapshot.fii.net_futures_cr:,.0f} cr  (positive = long)
- Index options net: ₹{snapshot.fii.net_options_cr:,.0f} cr

{provider_suffix}

## Required JSON output
{{
  "direction": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": 1–5,
  "recommended_strike": <integer — ATM or one strike above/below ATM only>,
  "entry_premium_low": <number>,
  "entry_premium_high": <number>,
  "key_reason": "<one sentence>",
  "key_risk": "<one sentence>"
}}

ATM strike is {snapshot.option_chain.atm_strike}. Permitted strikes: {atm_minus_1}, {snapshot.option_chain.atm_strike}, {atm_plus_1}.
Any other strike will be rejected and your response discarded.
If uncertain, use {snapshot.option_chain.atm_strike}.
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt.strip()},
    ]
