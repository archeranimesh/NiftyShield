"""Tests for Dhan token claim inspection (offline; synthetic JWTs only)."""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from src.auth.dhan_token import TokenState, inspect_token

NOW = datetime(2026, 11, 3, 5, 0, tzinfo=timezone.utc)


def make_jwt(exp: datetime | None, iat: datetime | None = None) -> str:
    claims: dict[str, int] = {}
    if exp is not None:
        claims["exp"] = int(exp.timestamp())
    if iat is not None:
        claims["iat"] = int(iat.timestamp())
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"hdr.{body}.sig"


def test_valid_token_reports_age_and_remaining() -> None:
    status = inspect_token(make_jwt(NOW + timedelta(hours=10), NOW - timedelta(hours=14)), NOW)
    assert status.state is TokenState.VALID and status.usable
    assert status.age == timedelta(hours=14) and status.remaining == timedelta(hours=10)
    assert "age 14.0h" in status.describe() and "expires in 10.0h" in status.describe()


def test_expiring_token_is_still_usable() -> None:
    status = inspect_token(make_jwt(NOW + timedelta(minutes=30)), NOW)
    assert status.state is TokenState.EXPIRING and status.usable


def test_expired_token_is_unusable_and_says_how_stale() -> None:
    status = inspect_token(make_jwt(NOW - timedelta(hours=32), NOW - timedelta(hours=56)), NOW)
    assert status.state is TokenState.EXPIRED and not status.usable
    assert "expired 32.0h ago" in status.describe()


@pytest.mark.parametrize("token", [None, "", "   "])
def test_missing_token(token: str | None) -> None:
    status = inspect_token(token, NOW)
    assert status.state is TokenState.MISSING and not status.usable


@pytest.mark.parametrize("token", ["opaque", "a.b.c", "a.!!!.c", make_jwt(None)])
def test_unreadable_token_is_not_blocked_and_never_raises(token: str) -> None:
    status = inspect_token(token, NOW)
    assert status.state is TokenState.UNREADABLE and status.usable


def test_describe_never_contains_token() -> None:
    token = make_jwt(NOW - timedelta(hours=1))
    assert token not in inspect_token(token, NOW).describe()
    assert repr(inspect_token(token, NOW)).find("sig") == -1
