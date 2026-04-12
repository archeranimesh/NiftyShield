# src/mf — Module Context

> Auto-loaded when working inside `src/mf/`. Read this before touching any file here.

---

## Data Model: Transaction Ledger

MF holdings use a **ledger model** — never mutate existing rows.

- `mf_transactions` table stores every SIP/redemption as a plain `INSERT`.
- Current holdings are derived at query time via `SUM(units)`.
- New SIP = new row. No UPDATE to existing transactions. Ever.
- This enables full history, attribution, and idempotent re-seeding.

Unique constraint: `(amfi_code, transaction_date, transaction_type)` — allows one BUY and one SELL per NAV date per scheme. Conflict policy: `ON CONFLICT DO NOTHING` (idempotent seeds).

---

## NAV Source: AMFI Flat File

Official source: `https://www.amfiindia.com/spages/NAVAll.txt`

- Semicolon-delimited, 6 fields: `code; ISIN growth; ISIN reinvest; name; NAV; date`
- No auth, no rate limits
- **Parsing gate:** `parts[0].strip().isdigit()` — skips category headers, the column header line, blank lines, and malformed rows. No regex needed.
- AMFI publishes after market close (7–9 PM IST). The 3:45 PM cron fetches T-1 NAV — expected, correct.

`nav_fetcher.py` injectable: accepts a `NavFetcherFn = Callable[[set[str]], dict[str, Decimal]]`. Tests pass a lambda; production gets the real AMFI fetcher. Missing AMFI codes logged as WARNING, not raised.

---

## Decimal TEXT Round-trip Invariant

All monetary fields (`units`, `amount`, `nav`) are stored as **TEXT** in SQLite to preserve exact `Decimal` precision. Never store as float or REAL.

Read back: `Decimal(row["col"])` — always.

`get_holdings()` aggregates in Python via `Decimal` arithmetic, not SQL `SUM()` — avoids CAST rounding.

---

## `MFHolding` Lives in `models.py`

`MFHolding` is a frozen dataclass defined in `src/mf/models.py`, **not** in `tracker.py`.

**Why:** `store.py` imports `MFHolding` to type its return value. If `MFHolding` were in `tracker.py`, `store.py` would need to import from `tracker.py`, creating a circular import.

Do not move it to `tracker.py`. If `src/models/` migration happens, it moves there — not to `tracker.py`.

---

## Models Summary (`models.py`)

| Class | Type | Notes |
|---|---|---|
| `TransactionType` | `(str, Enum)` | `BUY`, `SELL` — StrEnum avoided (3.11+ only) |
| `MFTransaction` | Pydantic, `frozen=True` | Units/amount as `Decimal` |
| `MFNavSnapshot` | Pydantic, `frozen=True` | NAV as `Decimal` |
| `MFHolding` | Frozen dataclass | Derived type: `amfi_code`, `name`, `units`, `avg_nav`, `total_invested` |

---

## Store Behaviours (`store.py`)

- `get_holdings()` → `dict[str, MFHolding]` keyed by `amfi_code`
- NAV snapshots: `ON CONFLICT(amfi_code, snapshot_date) DO UPDATE` — last write wins
- Uses shared `src/db.py` connection factory (WAL, FK enforcement, Row factory)

**Test note:** Tests use `tmp_path` (file-based SQLite), not `:memory:`. The `_connect()` context manager opens/closes on every call — `:memory:` would lose state between calls.

---

## `amfi_code` Type

Typed as `str` with pattern `^\d+$`, **not** `int`. Used as an identifier and join key, never arithmetic. Matches AMFI flat file representation exactly.
