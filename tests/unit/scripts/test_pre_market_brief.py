"""Unit tests for scripts/pre_market_brief.py.

Coverage (RO-2):
- _compute_unrealized_with_fallback: futures leg with no live LTP (missing or
  zero) falls back to the latest paper_leg_snapshots row instead of pricing
  at zero.
- _compute_unrealized_with_fallback: futures leg with a genuine live LTP of 0
  and no prior snapshot logs a warning and reports zero (documented edge
  case, not a crash).
- _compute_unrealized_with_fallback: non-futures (option) legs are priced
  from live LTP as before, unaffected by the futures fallback path.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from unittest.mock import AsyncMock, patch  # noqa: E402

from scripts.pre_market_brief import _compute_unrealized_with_fallback  # noqa: E402
from src.paper.models import PaperLegSnapshot, PaperPosition  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402

_STRATEGY = "paper_nifty_futures"
_FUT_LEG = "base_futures"
_FUT_KEY = "NSE_FO|99999"
_PE_LEG = "short_put"
_PE_KEY = "NSE_FO|12345"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_paper.db"


@pytest.fixture
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


class _StubBroker:
    """Minimal BrokerClient stand-in: returns only the prices it's told to."""

    def __init__(self, prices: dict[str, Decimal]) -> None:
        self._prices = prices

    async def get_ltp(self, instrument_keys: list[str]) -> dict[str, Decimal]:
        return {k: v for k, v in self._prices.items() if k in instrument_keys}


def _fut_position(net_qty: int = 65) -> PaperPosition:
    return PaperPosition(
        strategy_name=_STRATEGY,
        leg_role=_FUT_LEG,
        net_qty=net_qty,
        avg_cost=Decimal("24000"),
        avg_sell_price=Decimal("0"),
        instrument_key=_FUT_KEY,
        option_type="FUT",
    )


def _pe_position(net_qty: int = -75) -> PaperPosition:
    return PaperPosition(
        strategy_name=_STRATEGY,
        leg_role=_PE_LEG,
        net_qty=net_qty,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("120"),
        instrument_key=_PE_KEY,
        option_type="PE",
    )


@pytest.mark.asyncio
async def test_futures_leg_falls_back_to_prior_snapshot_when_ltp_missing(
    store: PaperStore,
) -> None:
    """Futures leg with no pre-open LTP uses yesterday's EOD unrealized P&L."""
    store.record_leg_snapshot(
        PaperLegSnapshot(
            strategy_name=_STRATEGY,
            leg_role=_FUT_LEG,
            snapshot_date=date(2026, 8, 6),
            unrealized_pnl=Decimal("3250.00"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("3250.00"),
            ltp=Decimal("24050"),
        )
    )
    broker = _StubBroker({})  # no pre-open LTP for the future at all
    unrealized = await _compute_unrealized_with_fallback(
        store, broker, _STRATEGY, [_fut_position()]
    )
    assert unrealized == Decimal("3250.00")


@pytest.mark.asyncio
async def test_futures_leg_falls_back_when_ltp_is_zero(store: PaperStore) -> None:
    """A zero LTP (not just a missing key) also triggers the snapshot fallback."""
    store.record_leg_snapshot(
        PaperLegSnapshot(
            strategy_name=_STRATEGY,
            leg_role=_FUT_LEG,
            snapshot_date=date(2026, 8, 6),
            unrealized_pnl=Decimal("-500.00"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("-500.00"),
        )
    )
    broker = _StubBroker({_FUT_KEY: Decimal("0")})
    unrealized = await _compute_unrealized_with_fallback(
        store, broker, _STRATEGY, [_fut_position()]
    )
    assert unrealized == Decimal("-500.00")


@pytest.mark.asyncio
async def test_futures_leg_no_snapshot_and_no_ltp_reports_zero(
    store: PaperStore,
) -> None:
    """Edge case: brand-new futures leg, no EOD snapshot exists yet — zero,
    not a fabricated notional loss, and does not raise."""
    broker = _StubBroker({})
    unrealized = await _compute_unrealized_with_fallback(
        store, broker, _STRATEGY, [_fut_position()]
    )
    assert unrealized == Decimal("0")


@pytest.mark.asyncio
async def test_non_futures_leg_uses_live_ltp_unaffected(store: PaperStore) -> None:
    """A short put with genuine pre-market LTP is priced normally — no fallback."""
    broker = _StubBroker({_PE_KEY: Decimal("80")})
    unrealized = await _compute_unrealized_with_fallback(store, broker, _STRATEGY, [_pe_position()])
    # Short leg: (avg_sell_price - ltp) * abs(net_qty) = (120 - 80) * 75
    assert unrealized == Decimal("3000")


@pytest.mark.asyncio
async def test_mixed_futures_and_option_legs_combine_correctly(
    store: PaperStore,
) -> None:
    """Futures leg falls back to snapshot while option leg still prices live,
    and the two sum correctly in one strategy's total."""
    store.record_leg_snapshot(
        PaperLegSnapshot(
            strategy_name=_STRATEGY,
            leg_role=_FUT_LEG,
            snapshot_date=date(2026, 8, 6),
            unrealized_pnl=Decimal("1000.00"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("1000.00"),
        )
    )
    broker = _StubBroker({_PE_KEY: Decimal("80")})  # no futures price pre-market
    unrealized = await _compute_unrealized_with_fallback(
        store, broker, _STRATEGY, [_fut_position(), _pe_position()]
    )
    assert unrealized == Decimal("1000.00") + Decimal("3000")


_CSP = "paper_csp_nifty_v1"


def _open_position(
    strategy_name: str = _CSP, leg_role: str = "short_put", net_qty: int = 1
) -> PaperPosition:
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("0"),
        instrument_key="123",
        option_type="CE",
    )


@pytest.mark.asyncio
async def test_main_escapes_markdown_in_telegram_message(tmp_path: Path) -> None:
    """Ensure dynamic values and static punctuation are properly escaped for MarkdownV2."""
    with (
        patch("scripts.pre_market_brief.settings.telegram_bot_token", "dummy"),
        patch("scripts.pre_market_brief.settings.telegram_chat_id", "dummy"),
        patch("scripts.pre_market_brief.settings.db_path", str(tmp_path / "test.db")),
        patch("scripts.pre_market_brief.settings.upstox_env", "test"),
        patch("scripts.pre_market_brief.create_client"),
        patch("scripts.pre_market_brief.get_current_ivr", return_value=0.532),
        patch("scripts.pre_market_brief.PaperStore") as mock_store_cls,
        patch(
            "scripts.pre_market_brief._compute_unrealized_with_fallback",
            return_value=Decimal("123.45"),
        ),
        patch(
            "scripts.pre_market_brief.TelegramGateway.send_plain_message", new_callable=AsyncMock
        ) as mock_send,
    ):
        mock_store = mock_store_cls.return_value
        mock_store.get_strategy_names.return_value = [_CSP]
        mock_store.get_positions.return_value = [_open_position()]
        mock_send.return_value = True

        from scripts.pre_market_brief import main

        await main()

        mock_send.assert_called_once()
        msg = mock_send.call_args[0][0]

        assert "CSP V1" in msg, "Strategy label should be shown, not the raw id"
        assert "+₹123.45" in msg, "Signed P&L renders literally inside the fenced table"
        assert r"53\.2\%" in msg or r"53\.2%" in msg, "IVR should be backslash escaped"
        assert "<b>" not in msg and "</b>" not in msg, "No HTML tags in the redesigned brief"
        assert "```" in msg, "Table must be fenced"


@pytest.mark.asyncio
async def test_brief_is_markdownv2_no_html(tmp_path: Path) -> None:
    """The redesigned brief never emits literal <b> HTML tags."""
    with (
        patch("scripts.pre_market_brief.settings.telegram_bot_token", "dummy"),
        patch("scripts.pre_market_brief.settings.telegram_chat_id", "dummy"),
        patch("scripts.pre_market_brief.settings.db_path", str(tmp_path / "test.db")),
        patch("scripts.pre_market_brief.settings.upstox_env", "test"),
        patch("scripts.pre_market_brief.create_client"),
        patch("scripts.pre_market_brief.get_current_ivr", return_value=None),
        patch("scripts.pre_market_brief.PaperStore") as mock_store_cls,
        patch(
            "scripts.pre_market_brief._compute_unrealized_with_fallback",
            return_value=Decimal("-50.00"),
        ),
        patch(
            "scripts.pre_market_brief.TelegramGateway.send_plain_message", new_callable=AsyncMock
        ) as mock_send,
    ):
        mock_store = mock_store_cls.return_value
        mock_store.get_strategy_names.return_value = [_CSP]
        mock_store.get_positions.return_value = [_open_position()]
        mock_send.return_value = True

        from scripts.pre_market_brief import main

        await main()

        msg = mock_send.call_args[0][0]
        assert "<b>" not in msg and "</b>" not in msg
        assert "☀️ *NiftyShield Pre\\-Market Brief*" in msg


@pytest.mark.asyncio
async def test_overlay_breaks_into_cc_collar_pp(tmp_path: Path) -> None:
    """paper_nifty_overlay renders as a parent row plus CC/Collar/PP sub-rows,
    the empty sub-group showing em-dashes."""
    with (
        patch("scripts.pre_market_brief.settings.telegram_bot_token", "dummy"),
        patch("scripts.pre_market_brief.settings.telegram_chat_id", "dummy"),
        patch("scripts.pre_market_brief.settings.db_path", str(tmp_path / "test.db")),
        patch("scripts.pre_market_brief.settings.upstox_env", "test"),
        patch("scripts.pre_market_brief.create_client"),
        patch("scripts.pre_market_brief.get_current_ivr", return_value=None),
        patch("scripts.pre_market_brief.PaperStore") as mock_store_cls,
        patch(
            "scripts.pre_market_brief._compute_unrealized_with_fallback",
            side_effect=lambda store, broker, name, positions: Decimal(len(positions) * 100),
        ),
        patch(
            "scripts.pre_market_brief.TelegramGateway.send_plain_message", new_callable=AsyncMock
        ) as mock_send,
    ):
        mock_store = mock_store_cls.return_value
        mock_store.get_strategy_names.return_value = ["paper_nifty_overlay"]
        mock_store.get_positions.return_value = [
            _open_position("paper_nifty_overlay", "overlay_cc"),
            _open_position("paper_nifty_overlay", "overlay_collar_put"),
            _open_position("paper_nifty_overlay", "overlay_collar_call"),
        ]
        mock_send.return_value = True

        from scripts.pre_market_brief import main

        await main()

        msg = mock_send.call_args[0][0]
        assert "Nifty Overlay" in msg
        assert "├ CC" in msg
        assert "├ Collar" in msg
        assert "└ PP" in msg
        # PP has no open legs in this fixture — both columns show an em-dash.
        pp_line = next(line for line in msg.splitlines() if "└ PP" in line)
        assert "—" in pp_line


@pytest.mark.asyncio
async def test_total_row_sums_without_double_counting_overlay(tmp_path: Path) -> None:
    """Total P&L equals the sum of the per-strategy aggregates — the overlay
    parent counted once, not again via its sub-rows."""
    with (
        patch("scripts.pre_market_brief.settings.telegram_bot_token", "dummy"),
        patch("scripts.pre_market_brief.settings.telegram_chat_id", "dummy"),
        patch("scripts.pre_market_brief.settings.db_path", str(tmp_path / "test.db")),
        patch("scripts.pre_market_brief.settings.upstox_env", "test"),
        patch("scripts.pre_market_brief.create_client"),
        patch("scripts.pre_market_brief.get_current_ivr", return_value=None),
        patch("scripts.pre_market_brief.PaperStore") as mock_store_cls,
        patch(
            "scripts.pre_market_brief._compute_unrealized_with_fallback",
            side_effect=lambda store, broker, name, positions: Decimal(len(positions) * 100),
        ),
        patch(
            "scripts.pre_market_brief.TelegramGateway.send_plain_message", new_callable=AsyncMock
        ) as mock_send,
    ):
        mock_store = mock_store_cls.return_value
        mock_store.get_strategy_names.return_value = [_CSP, "paper_nifty_overlay"]

        def _positions(name: str) -> list[PaperPosition]:
            if name == _CSP:
                return [_open_position(_CSP)]
            return [
                _open_position("paper_nifty_overlay", "overlay_cc"),
                _open_position("paper_nifty_overlay", "overlay_pp"),
            ]

        mock_store.get_positions.side_effect = _positions
        mock_send.return_value = True

        from scripts.pre_market_brief import main

        await main()

        msg = mock_send.call_args[0][0]
        # CSP: 1 leg -> ₹100. Overlay parent: 2 legs -> ₹200 (not summed again
        # via its CC/PP sub-rows). Total legs = 3, total P&L = ₹300.
        total_line = next(line for line in msg.splitlines() if line.startswith("Total"))
        assert "3" in total_line
        assert "+₹300.00" in total_line


@pytest.mark.asyncio
async def test_unmapped_strategy_id(tmp_path: Path) -> None:
    """Every paper_* id get_strategy_names can return must be in STRATEGY_LABELS —
    an unmapped id raises loudly rather than rendering the raw id."""
    with (
        patch("scripts.pre_market_brief.settings.telegram_bot_token", "dummy"),
        patch("scripts.pre_market_brief.settings.telegram_chat_id", "dummy"),
        patch("scripts.pre_market_brief.settings.db_path", str(tmp_path / "test.db")),
        patch("scripts.pre_market_brief.settings.upstox_env", "test"),
        patch("scripts.pre_market_brief.create_client"),
        patch("scripts.pre_market_brief.get_current_ivr", return_value=None),
        patch("scripts.pre_market_brief.PaperStore") as mock_store_cls,
        patch(
            "scripts.pre_market_brief._compute_unrealized_with_fallback",
            return_value=Decimal("0"),
        ),
    ):
        mock_store = mock_store_cls.return_value
        mock_store.get_strategy_names.return_value = ["paper_no_such_strategy"]
        mock_store.get_positions.return_value = [_open_position("paper_no_such_strategy")]

        from scripts.pre_market_brief import main

        with pytest.raises(ValueError, match="no display label mapped"):
            await main()


@pytest.mark.asyncio
async def test_no_open_positions_path(tmp_path: Path) -> None:
    """Every strategy has trades but none are open -> clean MarkdownV2, no HTML."""
    with (
        patch("scripts.pre_market_brief.settings.telegram_bot_token", "dummy"),
        patch("scripts.pre_market_brief.settings.telegram_chat_id", "dummy"),
        patch("scripts.pre_market_brief.settings.db_path", str(tmp_path / "test.db")),
        patch("scripts.pre_market_brief.settings.upstox_env", "test"),
        patch("scripts.pre_market_brief.create_client"),
        patch("scripts.pre_market_brief.get_current_ivr", return_value=None),
        patch("scripts.pre_market_brief.PaperStore") as mock_store_cls,
        patch(
            "scripts.pre_market_brief.TelegramGateway.send_plain_message", new_callable=AsyncMock
        ) as mock_send,
    ):
        mock_store = mock_store_cls.return_value
        mock_store.get_strategy_names.return_value = [_CSP]
        mock_store.get_positions.return_value = [_open_position(_CSP, net_qty=0)]
        mock_send.return_value = True

        from scripts.pre_market_brief import main

        await main()

        msg = mock_send.call_args[0][0]
        assert "<b>" not in msg
        assert "No active open positions" in msg
        assert "```" not in msg
