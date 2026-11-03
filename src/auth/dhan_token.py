"""Dhan access-token age and validity, read from the token's own claims.

The Dhan token is a manual 24 h JWT. An expired token and a wrong client id
return the same 401 (``roll_checks.md`` section 2), so waiting for the 401 cannot tell them apart;
the ``exp`` claim can. The payload is decoded without verifying the signature
(we only read our own token's clock) and the token value is never returned,
logged or placed in an exception message.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

EXPIRING_SOON = timedelta(hours=2)


class TokenState(str, Enum):
    """Coarse validity of the configured Dhan token."""

    VALID = "valid"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    MISSING = "missing"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class TokenStatus:
    """Token validity and age. Carries no token material.

    Attributes:
        state: Coarse state.
        issued_at: ``iat`` claim (UTC), if present.
        expires_at: ``exp`` claim (UTC), if present.
        age: Time since ``iat`` at inspection, if known.
        remaining: Time until ``exp`` (negative once expired), if known.
    """

    state: TokenState
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    age: timedelta | None = None
    remaining: timedelta | None = None

    @property
    def usable(self) -> bool:
        """Whether a Dhan call is worth attempting now."""
        # UNREADABLE is not blocked: the 401 path decides for a non-JWT token.
        return self.state not in (TokenState.EXPIRED, TokenState.MISSING)

    def describe(self) -> str:
        """Short human-readable summary (no token material)."""
        parts = [f"Dhan token {self.state.value}"]
        if self.age is not None:
            parts.append(f"age {_hours(self.age)}")
        if self.remaining is not None:
            if self.remaining >= timedelta(0):
                parts.append(f"expires in {_hours(self.remaining)}")
            else:
                parts.append(f"expired {_hours(-self.remaining)} ago")
        return ", ".join(parts)


def _hours(delta: timedelta) -> str:
    return f"{delta.total_seconds() / 3600:.1f}h"


def _claims(token: str) -> dict[str, object] | None:
    segments = token.split(".")
    if len(segments) != 3:
        return None
    try:
        padded = segments[1] + "=" * (-len(segments[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (binascii.Error, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _ts(value: object) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def inspect_token(token: str | None, now: datetime) -> TokenStatus:
    """Classify a Dhan access token from its JWT claims.

    Args:
        token: The raw token (never echoed back), or ``None``/blank.
        now: Timezone-aware current time.

    Returns:
        A :class:`TokenStatus`. ``UNREADABLE`` when the token is not a JWT with
        a numeric ``exp`` claim (it may still be valid; the 401 path decides).
    """
    if not token or not token.strip():
        return TokenStatus(TokenState.MISSING)
    claims = _claims(token.strip())
    expires_at = _ts(claims.get("exp")) if claims else None
    if expires_at is None:
        return TokenStatus(TokenState.UNREADABLE)
    issued_at = _ts(claims.get("iat")) if claims else None
    remaining = expires_at - now
    if remaining <= timedelta(0):
        state = TokenState.EXPIRED
    elif remaining < EXPIRING_SOON:
        state = TokenState.EXPIRING
    else:
        state = TokenState.VALID
    age = now - issued_at if issued_at else None
    return TokenStatus(state, issued_at, expires_at, age, remaining)
