from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.council.models import CouncilOutput
from src.council.rapid import CouncilTimeoutError, RapidCouncil
from src.strategy.protocol import SignalEvent


@pytest.fixture
def signal_event() -> SignalEvent:
    return SignalEvent(
        event_type="TEST_SIGNAL",
        severity="ACTION",
        description="Test description",
        payload={"nifty_spot": 22000.0},
    )


@pytest.fixture
def spec_doc() -> str:
    return "This is the strategy spec document."


@pytest.fixture
def council(spec_doc: str) -> RapidCouncil:
    return RapidCouncil(
        spec_doc=spec_doc,
        openrouter_api_key="or-key",  # pragma: allowlist secret
        anthropic_api_key="anthropic-key",  # pragma: allowlist secret
        xai_api_key="xai-key",  # pragma: allowlist secret
    )


@pytest.mark.asyncio
async def test_rapid_council_happy_path(council: RapidCouncil, signal_event: SignalEvent) -> None:
    # Setup mock responses
    def mock_post(url: str, *args, **kwargs) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()

        json_payload = kwargs.get("json", {})
        model = json_payload.get("model")

        if "openrouter.ai" in url:
            if model == "deepseek/deepseek-r1-0528":
                resp_data = {"choices": [{"message": {"content": "QuantAnalyst response"}}]}
            else:
                resp_data = {"choices": [{"message": {"content": "RiskManager response"}}]}
        elif "api.anthropic.com" in url:
            if model == "claude-haiku-4-5-20251001":
                resp_data = {
                    "content": [{"text": "SpecGuardian response: COMPLIANT with Clause 1."}]
                }
            else:
                resp_data = {
                    "content": [
                        {
                            "text": (
                                '{"actions": ['
                                '  {"action_type": "ADJUST", "legs_to_close": ["leg1"], '
                                '   "legs_to_open": [{"instrument_key": "NIFTY26JUN22000CE", "action": "BUY", "quantity": 50, "leg_role": "leg2", "notes": "New leg"}], '
                                '   "rationale": "Perfect setup", "council_rank": 1}'
                                '], "chairman_rationale": "Synthesized fine", "dissenting_notes": null}'
                            )
                        }
                    ]
                }
        elif "api.x.ai" in url:
            resp_data = {"choices": [{"message": {"content": "OptionsStrategist response"}}]}
        else:
            resp_data = {}

        mock_resp.json = AsyncMock(return_value=resp_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        return mock_resp

    with patch("aiohttp.ClientSession.post", side_effect=mock_post):
        output = await council.consult(
            event=signal_event, context="Current position is delta neutral."
        )

        assert isinstance(output, CouncilOutput)
        assert len(output.stage1_responses) == 4
        assert not any(resp.timed_out for resp in output.stage1_responses)
        assert len(output.actions) == 1
        assert output.actions[0].action_type == "ADJUST"
        assert output.actions[0].legs_to_close == ["leg1"]
        assert len(output.actions[0].legs_to_open) == 1
        assert output.actions[0].legs_to_open[0].instrument_key == "NIFTY26JUN22000CE"
        assert output.actions[0].legs_to_open[0].action == "BUY"
        assert output.actions[0].legs_to_open[0].quantity == 50
        assert output.actions[0].legs_to_open[0].leg_role == "leg2"
        assert output.actions[0].legs_to_open[0].notes == "New leg"
        assert output.chairman_rationale == "Synthesized fine"
        assert output.dissenting_notes is None
        assert output.latency_ms > 0


@pytest.mark.asyncio
async def test_rapid_council_partial_timeout(
    council: RapidCouncil, signal_event: SignalEvent
) -> None:
    def mock_post(url: str, *args, **kwargs) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()

        json_payload = kwargs.get("json", {})
        model = json_payload.get("model")

        if "openrouter.ai" in url:
            if model == "deepseek/deepseek-r1-0528":
                mock_resp.__aenter__ = AsyncMock(
                    side_effect=asyncio.TimeoutError("Connection timed out")
                )
                return mock_resp
            else:
                resp_data = {"choices": [{"message": {"content": "RiskManager response"}}]}
        elif "api.anthropic.com" in url:
            if model == "claude-haiku-4-5-20251001":
                resp_data = {"content": [{"text": "SpecGuardian response"}]}
            else:
                resp_data = {
                    "content": [
                        {
                            "text": (
                                '{"actions": [], "chairman_rationale": "Sufficient info", "dissenting_notes": null}'
                            )
                        }
                    ]
                }
        elif "api.x.ai" in url:
            resp_data = {"choices": [{"message": {"content": "OptionsStrategist response"}}]}
        else:
            resp_data = {}

        mock_resp.json = AsyncMock(return_value=resp_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        return mock_resp

    with patch("aiohttp.ClientSession.post", side_effect=mock_post):
        output = await council.consult(
            event=signal_event, context="Current position is delta neutral."
        )

        assert isinstance(output, CouncilOutput)
        assert len(output.stage1_responses) == 4
        # QuantAnalyst should be timed out
        quant_resp = next(r for r in output.stage1_responses if r.persona == "QuantAnalyst")
        assert quant_resp.timed_out is True
        assert quant_resp.response == ""

        # Others should not be timed out
        other_resps = [r for r in output.stage1_responses if r.persona != "QuantAnalyst"]
        assert all(not r.timed_out for r in other_resps)
        assert output.chairman_rationale == "Sufficient info"


@pytest.mark.asyncio
async def test_rapid_council_spec_guardian_non_compliant(
    council: RapidCouncil, signal_event: SignalEvent
) -> None:
    def mock_post(url: str, *args, **kwargs) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()

        json_payload = kwargs.get("json", {})
        model = json_payload.get("model")

        if "openrouter.ai" in url:
            if model == "deepseek/deepseek-r1-0528":
                resp_data = {"choices": [{"message": {"content": "QuantAnalyst response"}}]}
            else:
                resp_data = {"choices": [{"message": {"content": "RiskManager response"}}]}
        elif "api.anthropic.com" in url:
            if model == "claude-haiku-4-5-20251001":
                resp_data = {
                    "content": [
                        {"text": "SpecGuardian response: Action 1 is NON-COMPLIANT with Clause 2."}
                    ]
                }
            else:
                resp_data = {
                    "content": [
                        {
                            "text": (
                                '{"actions": [], "chairman_rationale": "Rejected due to spec", "dissenting_notes": "None"}'
                            )
                        }
                    ]
                }
        elif "api.x.ai" in url:
            resp_data = {"choices": [{"message": {"content": "OptionsStrategist response"}}]}
        else:
            resp_data = {}

        mock_resp.json = AsyncMock(return_value=resp_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        return mock_resp

    with patch("aiohttp.ClientSession.post", side_effect=mock_post):
        output = await council.consult(
            event=signal_event, context="Current position is delta neutral."
        )
        assert output.dissenting_notes is not None
        assert "[SpecGuardian Compliance Alert] NON-COMPLIANT detected" in output.dissenting_notes


@pytest.mark.asyncio
async def test_rapid_council_chairman_timeout(
    council: RapidCouncil, signal_event: SignalEvent
) -> None:
    def mock_post(url: str, *args, **kwargs) -> MagicMock:
        json_payload = kwargs.get("json", {})
        model = json_payload.get("model")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()

        if "api.anthropic.com" in url and model == "claude-sonnet-4-6":
            mock_resp.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError("Chairman timeout"))
            return mock_resp

        mock_resp.json = AsyncMock(return_value={})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = MagicMock(return_value=None)
        return mock_resp

    with patch("aiohttp.ClientSession.post", side_effect=mock_post):
        with pytest.raises(CouncilTimeoutError):
            await council.consult(event=signal_event, context="Context")
