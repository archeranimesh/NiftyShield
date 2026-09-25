"""Provider/category-level performance and volatility stats for MVP picks.

Combines realized + unrealized P&L per category and computes an
inflow-corrected daily-return volatility series (capital-weighted average
of each pick's own price return, so new tranches/picks entering a category
are not mistaken for a price move).
"""

from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from src.db import connect
from src.mvp.models import PickStatus
from src.mvp.store import MVPStore

TRADING_DAYS_PER_YEAR = 252


class CategoryReturn(BaseModel):
    """Combined realized + unrealized return for one provider/category."""

    model_config = ConfigDict(frozen=True)

    provider: str
    category: str
    n_picks: int
    deployed: Decimal
    current_value: Decimal
    total_return_pct: Decimal | None


class CategoryVolatility(BaseModel):
    """Daily-return volatility stats for one provider/category."""

    model_config = ConfigDict(frozen=True)

    provider: str
    category: str
    n_days: int
    annualized_stdev_pct: float
    annualized_mean_pct: float
    sharpe: float | None
    max_drawdown_pct: float


def _latest_ltp_by_pick(db_path: Path) -> dict[str, Decimal]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            WITH ranked AS (
                SELECT pick_id, ltp,
                       ROW_NUMBER() OVER (
                           PARTITION BY pick_id ORDER BY captured_at DESC, snapshot_id DESC
                       ) rn
                FROM mvp_snapshots
            )
            SELECT pick_id, ltp FROM ranked WHERE rn = 1
            """
        ).fetchall()
    return {row["pick_id"]: Decimal(row["ltp"]) for row in rows}


def compute_category_returns(store: MVPStore) -> list[CategoryReturn]:
    """Blended realized + unrealized return per provider/category.

    Args:
        store: The MVP store to read picks and providers/categories from.

    Returns:
        One ``CategoryReturn`` per provider/category with at least one
        pick that ever had deployed capital, sorted by return descending
        (``None`` returns, i.e. zero capital deployed, sort last).
    """
    category_map = {
        category.category_id: (provider.display_name, category.display_name)
        for provider in store.list_providers()
        for category in store.list_categories(provider.provider_id)
    }
    latest_ltp = _latest_ltp_by_pick(store.db_path)

    grouped: dict[tuple[str, str], list] = defaultdict(list)
    for pick in store.list_picks():
        if pick.deployed_capital == 0 or pick.category_id is None:
            continue
        grouped[category_map.get(pick.category_id, ("-", "-"))].append(pick)

    results = []
    for (provider, category), picks in grouped.items():
        deployed = sum((p.deployed_capital for p in picks), Decimal("0"))
        current = Decimal("0")
        for p in picks:
            if p.status == PickStatus.OPEN:
                ltp = latest_ltp.get(p.pick_id)
                current += ltp * p.total_qty if ltp is not None else p.deployed_capital
            else:
                current += p.deployed_capital + p.realized_pnl
        total_return_pct = (current - deployed) / deployed * 100 if deployed else None
        results.append(
            CategoryReturn(
                provider=provider,
                category=category,
                n_picks=len(picks),
                deployed=deployed,
                current_value=current,
                total_return_pct=total_return_pct,
            )
        )

    def sort_key(r: CategoryReturn) -> tuple[bool, Decimal]:
        ret = r.total_return_pct if r.total_return_pct is not None else Decimal("0")
        return (r.total_return_pct is None, -ret)

    results.sort(key=sort_key)
    return results


def _daily_price_returns(db_path: Path) -> dict[str, dict[str, float]]:
    """Per-pick {date: pct_return} from that pick's own snapshot price series."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            WITH ranked AS (
                SELECT pick_id, date(captured_at) AS d, ltp,
                       ROW_NUMBER() OVER (
                           PARTITION BY pick_id, date(captured_at) ORDER BY captured_at DESC
                       ) rn
                FROM mvp_snapshots
            )
            SELECT pick_id, d, ltp FROM ranked WHERE rn = 1
            """
        ).fetchall()

    series: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        series[row["pick_id"]][row["d"]] = float(row["ltp"])

    returns: dict[str, dict[str, float]] = defaultdict(dict)
    for pick_id, by_date in series.items():
        days = sorted(by_date)
        for i in range(1, len(days)):
            prev, cur = by_date[days[i - 1]], by_date[days[i]]
            if prev > 0:
                returns[pick_id][days[i]] = (cur / prev - 1) * 100
    return returns


def compute_category_volatility(store: MVPStore, min_days: int = 10) -> list[CategoryVolatility]:
    """Inflow-corrected daily-return volatility per provider/category.

    Each pick's own day-over-day price return is capital-weighted and
    averaged across the category for that day, then annualized. This
    avoids treating new capital deployed into a tranche or a newly added
    pick as a price move, which a raw portfolio-value time series would.

    Args:
        store: The MVP store to read picks and providers/categories from.
        min_days: Categories with fewer overlapping return-days than this
            are skipped (too little history to estimate volatility).

    Returns:
        One ``CategoryVolatility`` per qualifying provider/category,
        ranked by annualized stdev ascending (least volatile first).
    """
    category_map = {
        category.category_id: (provider.display_name, category.display_name)
        for provider in store.list_providers()
        for category in store.list_categories(provider.provider_id)
    }
    deployed_picks = [
        pick
        for pick in store.list_picks()
        if pick.deployed_capital != 0 and pick.category_id is not None
    ]
    pick_weight = {pick.pick_id: pick.deployed_capital for pick in deployed_picks}
    pick_category = {
        pick.pick_id: category_map.get(pick.category_id, ("-", "-")) for pick in deployed_picks
    }

    daily_returns_by_pick = _daily_price_returns(store.db_path)

    cat_day_returns: dict[tuple[str, str], dict[str, list[tuple[Decimal, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for pick_id, by_date in daily_returns_by_pick.items():
        if pick_id not in pick_weight:
            continue
        key = pick_category[pick_id]
        weight = pick_weight[pick_id]
        for d, r in by_date.items():
            cat_day_returns[key][d].append((weight, r))

    results = []
    for key, by_date in cat_day_returns.items():
        days = sorted(by_date)
        if len(days) < min_days:
            continue
        weighted_rets = [_weighted_avg(by_date[d]) for d in days]
        results.append(_category_volatility(key, weighted_rets))
    results.sort(key=lambda r: (r.annualized_stdev_pct is None, r.annualized_stdev_pct or 0))
    return results


def _weighted_avg(pairs: list[tuple[Decimal, float]]) -> float:
    total_weight = float(sum(w for w, _ in pairs))
    if total_weight == 0:
        return 0.0
    return sum(float(w) * r for w, r in pairs) / total_weight


def _category_volatility(key: tuple[str, str], daily_rets: list[float]) -> CategoryVolatility:
    n = len(daily_rets)
    daily_mean = sum(daily_rets) / n
    daily_var = sum((r - daily_mean) ** 2 for r in daily_rets) / (n - 1) if n > 1 else 0.0
    daily_sd = math.sqrt(daily_var)
    ann_sd = daily_sd * math.sqrt(TRADING_DAYS_PER_YEAR)
    ann_mean = daily_mean * TRADING_DAYS_PER_YEAR
    sharpe = ann_mean / ann_sd if ann_sd else None

    idx = [100.0]
    for r in daily_rets:
        idx.append(idx[-1] * (1 + r / 100))
    peak = idx[0]
    max_dd = 0.0
    for v in idx:
        peak = max(peak, v)
        max_dd = min(max_dd, (v - peak) / peak * 100)

    return CategoryVolatility(
        provider=key[0],
        category=key[1],
        n_days=n,
        annualized_stdev_pct=ann_sd,
        annualized_mean_pct=ann_mean,
        sharpe=sharpe,
        max_drawdown_pct=max_dd,
    )
