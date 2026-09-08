"""SQLite persistence for the daily signal pipeline.

Four tables live in ``data/portfolio/portfolio.sqlite`` (DDL mirrors
``docs/plan/signals/signals_schema.md``). ``SignalStore`` owns only a path;
every method opens its own short-lived connection via ``src.db.connect``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from src.db import connect
from src.signals.models import (
    DailySignal,
    MarketSnapshot,
    SignalOutcome,
    SignalResponse,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_inputs (
    trade_date    TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_responses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date   TEXT    NOT NULL,
    provider     TEXT    NOT NULL,
    direction    TEXT    NOT NULL,
    confidence   INTEGER NOT NULL,
    strike       INTEGER NOT NULL,
    premium_low  TEXT    NOT NULL,
    premium_high TEXT    NOT NULL,
    key_reason   TEXT    NOT NULL,
    key_risk     TEXT    NOT NULL,
    raw_response TEXT    NOT NULL,
    created_at   TEXT    NOT NULL,
    UNIQUE (trade_date, provider)
);

CREATE TABLE IF NOT EXISTS daily_signals (
    trade_date           TEXT PRIMARY KEY,
    consensus_direction  TEXT NOT NULL,
    consensus_confidence TEXT NOT NULL,
    trade_action         TEXT NOT NULL,
    recommended_strike   INTEGER,
    agreeing_models      TEXT NOT NULL,
    dissenting_models    TEXT NOT NULL,
    created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_outcomes (
    trade_date         TEXT PRIMARY KEY,
    trade_action       TEXT NOT NULL,
    recommended_strike INTEGER,
    entry_premium      TEXT,
    exit_premium       TEXT,
    pnl_per_lot        TEXT,
    nifty_close        TEXT NOT NULL,
    executed           INTEGER NOT NULL DEFAULT 0,
    phase              TEXT NOT NULL DEFAULT 'openrouter_only',
    notes              TEXT,
    recorded_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signal_responses_date
    ON signal_responses (trade_date);

CREATE INDEX IF NOT EXISTS idx_signal_outcomes_phase
    ON signal_outcomes (phase, trade_date);
"""


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _opt_str(value: object | None) -> str | None:
    """Serialise an optional value to ``str``, preserving SQL ``NULL``."""
    return None if value is None else str(value)


def _opt_decimal(value: str | None) -> Decimal | None:
    """Parse an optional ``TEXT`` column back to ``Decimal``, preserving ``None``."""
    return None if value is None else Decimal(value)


def _response_from_row(row: sqlite3.Row) -> SignalResponse:
    """Rebuild a ``SignalResponse`` from a ``signal_responses`` row."""
    return SignalResponse(
        trade_date=date.fromisoformat(row["trade_date"]),
        provider=row["provider"],
        direction=row["direction"],
        confidence=row["confidence"],
        recommended_strike=row["strike"],
        entry_premium_low=Decimal(row["premium_low"]),
        entry_premium_high=Decimal(row["premium_high"]),
        key_reason=row["key_reason"],
        key_risk=row["key_risk"],
        raw_response=row["raw_response"],
    )


def _outcome_from_row(row: sqlite3.Row) -> SignalOutcome:
    """Rebuild a ``SignalOutcome`` from a ``signal_outcomes`` row."""
    return SignalOutcome(
        trade_date=date.fromisoformat(row["trade_date"]),
        trade_action=row["trade_action"],
        recommended_strike=row["recommended_strike"],
        entry_premium=_opt_decimal(row["entry_premium"]),
        exit_premium=_opt_decimal(row["exit_premium"]),
        pnl_per_lot=_opt_decimal(row["pnl_per_lot"]),
        nifty_close=Decimal(row["nifty_close"]),
        executed=bool(row["executed"]),
        phase=row["phase"],
        notes=row["notes"] or "",
    )


class SignalStore:
    """Write/read gateway for the signal-pipeline tables."""

    def __init__(self, db_path: str) -> None:
        """Store the database path; no connection is opened here.

        Args:
            db_path: Filesystem path to the SQLite database file.
        """
        self.db_path = Path(db_path)

    def init_db(self) -> None:
        """Create all four tables and both indexes. Safe to call repeatedly."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)

    def record_snapshot(self, snapshot: MarketSnapshot) -> None:
        """Upsert the assembled market context for one trading day.

        Args:
            snapshot: The full ``MarketSnapshot``; persisted as JSON.
        """
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO signal_inputs (trade_date, snapshot_json) VALUES (?, ?)",
                (snapshot.trade_date.isoformat(), snapshot.model_dump_json()),
            )

    def record_response(self, response: SignalResponse) -> None:
        """Insert one model's raw response; no-op if the pair already exists.

        Args:
            response: The per-provider ``SignalResponse`` for a trading day.
        """
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO signal_responses ("
                " trade_date, provider, direction, confidence, strike,"
                " premium_low, premium_high, key_reason, key_risk,"
                " raw_response, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    response.trade_date.isoformat(),
                    response.provider,
                    response.direction.value,
                    response.confidence,
                    response.recommended_strike,
                    str(response.entry_premium_low),
                    str(response.entry_premium_high),
                    response.key_reason,
                    response.key_risk,
                    response.raw_response,
                    _utc_now_iso(),
                ),
            )

    def record_signal(self, signal: DailySignal) -> None:
        """Upsert the aggregated consensus for one trading day.

        Args:
            signal: The ``DailySignal`` produced by ``SignalAggregator``.
        """
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO daily_signals ("
                " trade_date, consensus_direction, consensus_confidence,"
                " trade_action, recommended_strike, agreeing_models,"
                " dissenting_models, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    signal.trade_date.isoformat(),
                    signal.consensus_direction.value,
                    str(signal.consensus_confidence),
                    signal.trade_action.value,
                    signal.recommended_strike,
                    json.dumps(signal.agreeing_models),
                    json.dumps(signal.dissenting_models),
                    _utc_now_iso(),
                ),
            )

    def record_outcome(self, outcome: SignalOutcome) -> None:
        """Upsert the recorded outcome for one trading day.

        Args:
            outcome: The ``SignalOutcome`` captured at 15:00 IST.
        """
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO signal_outcomes ("
                " trade_date, trade_action, recommended_strike, entry_premium,"
                " exit_premium, pnl_per_lot, nifty_close, executed, phase,"
                " notes, recorded_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    outcome.trade_date.isoformat(),
                    outcome.trade_action.value,
                    outcome.recommended_strike,
                    _opt_str(outcome.entry_premium),
                    _opt_str(outcome.exit_premium),
                    _opt_str(outcome.pnl_per_lot),
                    str(outcome.nifty_close),
                    int(outcome.executed),
                    outcome.phase,
                    outcome.notes,
                    _utc_now_iso(),
                ),
            )

    def get_snapshot(self, trade_date: date) -> MarketSnapshot | None:
        """Return the persisted ``MarketSnapshot`` for a day, or ``None``.

        Args:
            trade_date: The trading day to look up.
        """
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT snapshot_json FROM signal_inputs WHERE trade_date = ?",
                (trade_date.isoformat(),),
            ).fetchone()
        if row is None:
            return None
        return MarketSnapshot.model_validate_json(row["snapshot_json"])

    def get_recent_snapshots(self, n: int) -> list[MarketSnapshot]:
        """Return the ``n`` most recent persisted snapshots, newest first.

        Used to compute ``vix_5d_trend`` in ``assemble_market_snapshot``; the
        caller reverses the list for an oldest→newest comparison.

        Args:
            n: Maximum number of snapshots to return.
        """
        if n <= 0:
            return []
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT snapshot_json FROM signal_inputs ORDER BY trade_date DESC LIMIT ?",
                (n,),
            ).fetchall()
        return [MarketSnapshot.model_validate_json(row["snapshot_json"]) for row in rows]

    def get_responses(self, trade_date: date) -> list[SignalResponse]:
        """Return every stored provider response for a day, ordered by provider.

        Args:
            trade_date: The trading day to look up.
        """
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM signal_responses WHERE trade_date = ? ORDER BY provider",
                (trade_date.isoformat(),),
            ).fetchall()
        return [_response_from_row(row) for row in rows]

    def get_signal(self, trade_date: date) -> DailySignal | None:
        """Return the aggregated ``DailySignal`` for a day, or ``None``.

        The ``responses`` list is repopulated from the ``signal_responses`` table.

        Args:
            trade_date: The trading day to look up.
        """
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM daily_signals WHERE trade_date = ?",
                (trade_date.isoformat(),),
            ).fetchone()
        if row is None:
            return None
        return DailySignal(
            trade_date=date.fromisoformat(row["trade_date"]),
            responses=self.get_responses(trade_date),
            consensus_direction=row["consensus_direction"],
            consensus_confidence=Decimal(row["consensus_confidence"]),
            trade_action=row["trade_action"],
            recommended_strike=row["recommended_strike"],
            agreeing_models=json.loads(row["agreeing_models"]),
            dissenting_models=json.loads(row["dissenting_models"]),
        )

    def get_outcome(self, trade_date: date) -> SignalOutcome | None:
        """Return the recorded ``SignalOutcome`` for a day, or ``None``.

        Args:
            trade_date: The trading day to look up.
        """
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM signal_outcomes WHERE trade_date = ?",
                (trade_date.isoformat(),),
            ).fetchone()
        return None if row is None else _outcome_from_row(row)

    def get_all_outcomes(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
        phase: str | None = None,
    ) -> list[SignalOutcome]:
        """Return recorded outcomes, filtered and ordered by ``trade_date``.

        Args:
            from_date: Inclusive lower bound on ``trade_date``; unbounded if ``None``.
            to_date: Inclusive upper bound on ``trade_date``; unbounded if ``None``.
            phase: Restrict to a single pipeline phase; all phases if ``None``.
        """
        clauses: list[str] = []
        params: list[str] = []
        if from_date is not None:
            clauses.append("trade_date >= ?")
            params.append(from_date.isoformat())
        if to_date is not None:
            clauses.append("trade_date <= ?")
            params.append(to_date.isoformat())
        if phase is not None:
            clauses.append("phase = ?")
            params.append(phase)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with connect(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM signal_outcomes{where} ORDER BY trade_date",
                tuple(params),
            ).fetchall()
        return [_outcome_from_row(row) for row in rows]
