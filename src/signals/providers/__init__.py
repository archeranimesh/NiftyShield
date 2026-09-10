# Signal providers package

from decimal import Decimal, InvalidOperation
from typing import Any

from src.signals.models import SignalUsage


def _usage_from_envelope(envelope: dict[str, Any]) -> SignalUsage | None:
    """Extract OpenRouter usage block and cost, swallowing format errors."""
    usage_block = envelope.get("usage")
    if not isinstance(usage_block, dict):
        return None
    try:
        return SignalUsage(
            prompt_tokens=int(usage_block.get("prompt_tokens", 0)),
            completion_tokens=int(usage_block.get("completion_tokens", 0)),
            cost_usd=Decimal(str(usage_block["cost"])),
        )
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None
