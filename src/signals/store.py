"""SQLite persistence for the daily signal pipeline.

Four tables live in ``data/portfolio/portfolio.sqlite`` (DDL mirrors
``docs/plan/signals/signals_schema.md``). ``SignalStore`` owns only a path;
every method opens its own short-lived connection via ``src.db.connect``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
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
