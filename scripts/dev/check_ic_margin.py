# scripts/dev/check_ic_margin.py
"""Scratch feasibility check: can we get live margin for open paper IC legs?

Pulls open legs for all five Iron Condor variants (V1 weekly/monthly/leaps/yearly,
V2 monthly) from paper_trades via PaperStore.get_positions, then calls Upstox's
Margin Calculator endpoint (POST /v2/charges/margin) with UPSTOX_ACCESS_TOKEN to see
whether it returns a valid required_margin figure for each strategy's basket.

This is a diagnostic script, not a production entrypoint — no BrokerClient
abstraction (get_margins() on UpstoxLiveClient is NotImplementedError; there is no
BrokerClient method for the order-margin-calculator endpoint at all yet). Run
manually, read the output, decide whether it's worth wiring a real protocol method.

Requires a same-day UPSTOX_ACCESS_TOKEN (`python -m src.auth.login`) — this is a
Daily OAuth-token-gated endpoint, same tier as portfolio/order APIs.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import aiohttp
import structlog
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import settings
from src.paper.constants import DEFAULT_DB_PATH
from src.paper.store import PaperStore
from src.strategy.ic_expiry_config_v2 import CONFIGS_V2
from src.utils.logging import setup_logging

load_dotenv()

_SCRIPT_NAME = "scripts.dev.check_ic_margin"
logger = structlog.get_logger(_SCRIPT_NAME)

MARGIN_URL = "https://api.upstox.com/v2/charges/margin"

IC_STRATEGY_NAMES = [
    "paper_ic_nifty_v1_weekly",
    "paper_ic_nifty_v1_monthly",
    "paper_ic_nifty_v1_leaps",
    "paper_ic_nifty_v1_yearly",
    *(cfg.strategy_name for cfg in CONFIGS_V2.values()),
]


async def fetch_margin(
    session: aiohttp.ClientSession, instruments: list[dict[str, object]]
) -> dict[str, object]:
    """Call Upstox margin calculator for a basket of instruments.

    Args:
        session: Shared aiohttp session.
        instruments: List of {instrument_key, quantity, transaction_type, product}.

    Returns:
        Parsed JSON response body.

    Raises:
        aiohttp.ClientResponseError: On non-2xx response.
    """
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {settings.upstox_access_token}",
        "Content-Type": "application/json",
    }
    async with session.post(
        MARGIN_URL,
        headers=headers,
        json={"instruments": instruments},
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        body = await resp.json()
        resp.raise_for_status()
        return body


async def main() -> None:
    setup_logging()

    if not settings.upstox_access_token:
        logger.error("no_access_token", hint="run: python -m src.auth.login")
        return

    store = PaperStore(DEFAULT_DB_PATH)

    async with aiohttp.ClientSession() as session:
        for strategy_name in IC_STRATEGY_NAMES:
            positions = [p for p in store.get_positions(strategy_name) if p.net_qty != 0]
            if not positions:
                logger.info("no_open_legs", strategy=strategy_name)
                continue

            instruments = [
                {
                    "instrument_key": p.instrument_key,
                    "quantity": abs(p.net_qty),
                    "transaction_type": "SELL" if p.net_qty < 0 else "BUY",
                    "product": "D",
                }
                for p in positions
            ]

            try:
                result = await fetch_margin(session, instruments)
            except aiohttp.ClientResponseError as exc:
                logger.error(
                    "margin_call_failed",
                    strategy=strategy_name,
                    status=exc.status,
                    message=exc.message,
                )
                continue
            except Exception:
                logger.exception("margin_call_error", strategy=strategy_name)
                continue

            data = result.get("data", {})
            logger.info(
                "margin_ok",
                strategy=strategy_name,
                legs=len(instruments),
                required_margin=data.get("required_margin"),
                final_margin=data.get("final_margin"),
            )


if __name__ == "__main__":
    asyncio.run(main())
