"""Tests for look-back feature derivation (pure)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from src.gamma.features import PriorScan, derive_features

NOW = datetime(2026, 10, 12, 5, 0, tzinfo=timezone.utc)
CLOSE = NOW + timedelta(hours=3)


def prior(minutes_ago: float, **kw: object) -> PriorScan:
    base: dict[str, object] = dict(
        nifty_spot=D("24000"),
        gamma_val=D("0.001"),
        best_ask=D("4"),
        oi=1000,
        distance_pct=D("0.01"),
    )
    base.update(kw)
    return PriorScan(at=NOW - timedelta(minutes=minutes_ago), **base)  # type: ignore[arg-type]


def feats(history: list[PriorScan], option_type: str = "CE", **kw: object):
    args: dict[str, object] = dict(
        now=NOW,
        option_type=option_type,
        spot=D("24060"),
        gamma=D("0.002"),
        ask=D("5"),
        oi=1300,
        distance_pct=D("0.008"),
        history=history,
        close_at=CLOSE,
    )
    args.update(kw)
    return derive_features(**args)  # type: ignore[arg-type]


def test_no_history_everything_unavailable():
    f = feats([])
    assert f.speed_5m is None and f.underlying_return_15m is None
    assert f.oi_velocity_15m is None and f.option_price_rising is None
    assert f.distance_sigma is None


def test_full_lookback_values():
    f = feats([prior(15), prior(5)])
    assert f.underlying_return_15m == D("24060") / D("24000") - 1
    assert f.distance_pct_15m_ago == D("0.01")
    assert f.oi_velocity_15m == D("0.3")
    assert f.option_price_rising is True
    assert f.speed_5m == D("0.001") / D("60")


def test_speed_is_direction_signed_for_puts():
    # PE: spot falls 60 while gamma rises -> positive speed
    f = feats([prior(5)], option_type="PE", spot=D("23940"))
    assert f.speed_5m == D("0.001") / D("60")


def test_speed_none_when_spot_unchanged_and_price_falling_flag():
    f = feats([prior(5, best_ask=D("6"))], spot=D("24000"))
    assert f.speed_5m is None
    assert f.option_price_rising is False


def test_lookback_outside_tolerance_is_ignored():
    f = feats([prior(9)])
    assert f.speed_5m is None and f.option_price_rising is None


def test_oi_velocity_guards_zero_prior_oi():
    f = feats([prior(15, oi=0)])
    assert f.oi_velocity_15m == D("1300")


def test_distance_sigma_needs_three_returns():
    assert feats([prior(10), prior(5)]).distance_sigma is None
    hist = [
        prior(15, nifty_spot=D("24000")),
        prior(10, nifty_spot=D("24020")),
        prior(5, nifty_spot=D("24010")),
    ]
    f = feats(hist)
    assert f.underlying_rvol_15m is not None and f.underlying_rvol_15m > 0
    assert f.distance_sigma is not None and f.distance_sigma > 0


def test_flat_spot_gives_no_sigma():
    hist = [prior(m, nifty_spot=D("24060")) for m in (15, 10, 5)]
    assert feats(hist).distance_sigma is None


def test_speed_none_when_spot_moves_away_with_falling_gamma():
    ce = feats([prior(5, gamma_val=D("0.0015"))], spot=D("23940"), gamma=D("0.001"))
    pe = feats(
        [prior(5, gamma_val=D("0.0015"))], option_type="PE", spot=D("24060"), gamma=D("0.001")
    )
    assert ce.speed_5m is None and pe.speed_5m is None
