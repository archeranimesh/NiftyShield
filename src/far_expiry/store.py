import datetime
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from src.db import connect
from src.models.options import OptionChain


@dataclass(frozen=True)
class FarExpiryRow:
    snapshot_date: datetime.date
    captured_at: datetime.datetime
    underlying: str
    expiry: datetime.date
    strike: Decimal
    option_type: str
    source: str
    underlying_spot: Decimal | None
    ltp: Decimal
    bid: Decimal
    ask: Decimal
    oi: int
    volume: int
    iv: Decimal | None
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None


@dataclass(frozen=True)
class LiquidityRow:
    strike: Decimal
    option_type: str
    bid: Decimal
    ask: Decimal
    mid: Decimal | None
    spread_pct_mid: Decimal | None
    is_quoted: bool
    is_crossed_book: bool
    is_one_sided: bool
    has_oi: bool
    is_zero_delta: bool


def _calculate_liquidity(
    strike: Decimal, option_type: str, bid: Decimal, ask: Decimal, oi: int, delta: Decimal | None
) -> LiquidityRow:
    is_one_sided = (bid > 0 and ask == 0) or (bid == 0 and ask > 0)
    is_quoted = bid > 0 and ask > 0
    is_crossed_book = is_quoted and bid >= ask

    mid = None
    spread_pct_mid = None
    if is_quoted:
        mid = (bid + ask) / Decimal("2")
        if mid > 0:
            spread_pct_mid = (ask - bid) / mid

    is_zero_delta = delta is not None and delta == Decimal("0")

    return LiquidityRow(
        strike=strike,
        option_type=option_type,
        bid=bid,
        ask=ask,
        mid=mid,
        spread_pct_mid=spread_pct_mid,
        is_quoted=is_quoted,
        is_crossed_book=is_crossed_book,
        is_one_sided=is_one_sided,
        has_oi=oi > 0,
        is_zero_delta=is_zero_delta,
    )


def chain_to_liquidity_rows(chain: OptionChain) -> list[LiquidityRow]:
    rows = []
    for strike, strike_data in chain.strikes.items():
        if strike_data.ce is not None:
            rows.append(
                _calculate_liquidity(
                    strike=strike,
                    option_type="CE",
                    bid=strike_data.ce.bid,
                    ask=strike_data.ce.ask,
                    oi=strike_data.ce.oi,
                    delta=strike_data.ce.delta,
                )
            )
        if strike_data.pe is not None:
            rows.append(
                _calculate_liquidity(
                    strike=strike,
                    option_type="PE",
                    bid=strike_data.pe.bid,
                    ask=strike_data.pe.ask,
                    oi=strike_data.pe.oi,
                    delta=strike_data.pe.delta,
                )
            )
    return rows


def stored_row_to_liquidity_row(row: FarExpiryRow) -> LiquidityRow:
    return _calculate_liquidity(
        strike=row.strike,
        option_type=row.option_type,
        bid=row.bid,
        ask=row.ask,
        oi=row.oi,
        delta=row.delta,
    )


class FarExpiryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS far_expiry_chain_snapshots (
            snapshot_date TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            underlying TEXT NOT NULL,
            expiry TEXT NOT NULL,
            strike TEXT NOT NULL,
            option_type TEXT NOT NULL,
            source TEXT NOT NULL,
            underlying_spot TEXT,
            ltp TEXT NOT NULL,
            bid TEXT NOT NULL,
            ask TEXT NOT NULL,
            oi INTEGER NOT NULL,
            volume INTEGER NOT NULL,
            iv TEXT,
            delta TEXT,
            gamma TEXT,
            theta TEXT,
            vega TEXT,
            PRIMARY KEY (snapshot_date, expiry, strike, option_type, source)
        );
        CREATE INDEX IF NOT EXISTS idx_far_expiry_chain_snapshots_last_known_delta
        ON far_expiry_chain_snapshots (expiry, option_type, strike, snapshot_date);
        """
        with connect(self.db_path) as conn:
            conn.executescript(schema)

    def record_chain(
        self,
        snapshot_date: datetime.date,
        captured_at: datetime.datetime,
        underlying: str,
        source: str,
        chain: OptionChain,
    ) -> None:
        query = """
            INSERT OR REPLACE INTO far_expiry_chain_snapshots (
                snapshot_date, captured_at, underlying, expiry, strike, option_type, source,
                underlying_spot, ltp, bid, ask, oi, volume, iv, delta, gamma, theta, vega
            ) VALUES (
                :snapshot_date, :captured_at, :underlying, :expiry, :strike, :option_type, :source,
                :underlying_spot, :ltp, :bid, :ask, :oi, :volume, :iv, :delta, :gamma, :theta, :vega
            )
        """
        rows = []
        for strike, strike_data in chain.strikes.items():
            for opt_type, leg in [("CE", strike_data.ce), ("PE", strike_data.pe)]:
                if leg is not None:
                    rows.append(
                        {
                            "snapshot_date": snapshot_date.isoformat(),
                            "captured_at": captured_at.isoformat(),
                            "underlying": underlying,
                            "expiry": chain.expiry.isoformat(),
                            "strike": str(strike),
                            "option_type": opt_type,
                            "source": source,
                            "underlying_spot": str(chain.underlying_spot)
                            if chain.underlying_spot is not None
                            else None,
                            "ltp": str(leg.ltp),
                            "bid": str(leg.bid),
                            "ask": str(leg.ask),
                            "oi": leg.oi,
                            "volume": leg.volume,
                            "iv": str(leg.iv) if leg.iv is not None else None,
                            "delta": str(leg.delta) if leg.delta is not None else None,
                            "gamma": str(leg.gamma) if leg.gamma is not None else None,
                            "theta": str(leg.theta) if leg.theta is not None else None,
                            "vega": str(leg.vega) if leg.vega is not None else None,
                        }
                    )

        if not rows:
            return

        with connect(self.db_path) as conn:
            conn.executemany(query, rows)

    def read_chain_snapshots(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
        expiry: datetime.date,
        source: str | None = None,
    ) -> list[FarExpiryRow]:
        query = """
            SELECT
                snapshot_date, captured_at, underlying, expiry, strike, option_type, source,
                underlying_spot, ltp, bid, ask, oi, volume, iv, delta, gamma, theta, vega
            FROM far_expiry_chain_snapshots
            WHERE snapshot_date >= ? AND snapshot_date <= ? AND expiry = ?
        """
        params = [start_date.isoformat(), end_date.isoformat(), expiry.isoformat()]
        if source is not None:
            query += " AND source = ?"
            params.append(source)

        query += " ORDER BY snapshot_date, strike, option_type"

        with connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            results = []
            for row in cursor:
                results.append(
                    FarExpiryRow(
                        snapshot_date=datetime.date.fromisoformat(row["snapshot_date"]),
                        captured_at=datetime.datetime.fromisoformat(row["captured_at"]),
                        underlying=row["underlying"],
                        expiry=datetime.date.fromisoformat(row["expiry"]),
                        strike=Decimal(row["strike"]),
                        option_type=row["option_type"],
                        source=row["source"],
                        underlying_spot=Decimal(row["underlying_spot"])
                        if row["underlying_spot"] is not None
                        else None,
                        ltp=Decimal(row["ltp"]),
                        bid=Decimal(row["bid"]),
                        ask=Decimal(row["ask"]),
                        oi=row["oi"],
                        volume=row["volume"],
                        iv=Decimal(row["iv"]) if row["iv"] is not None else None,
                        delta=Decimal(row["delta"]) if row["delta"] is not None else None,
                        gamma=Decimal(row["gamma"]) if row["gamma"] is not None else None,
                        theta=Decimal(row["theta"]) if row["theta"] is not None else None,
                        vega=Decimal(row["vega"]) if row["vega"] is not None else None,
                    )
                )
            return results
