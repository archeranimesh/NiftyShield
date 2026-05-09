# Implementation Plan — Dhan Charges Implementation

Add auto-computed trading charges (STT, exchange, SEBI, stamp duty, GST, brokerage) to the Dhan intraday options P&L. Charges are computed from position data already fetched. Brokerage requires a user-supplied `--dhan-trade-count`.

## User Review Required

> [!IMPORTANT]
> This change involves a database schema migration for the `dhan_options_snapshots` table. The migration adds `charges` and `brokerage` columns as `TEXT` with a default of `'0'`. This is handled automatically on `DhanStore` initialization by checking column existence via `PRAGMA table_info`.

## Proposed Changes

### Dhan Models

#### [MODIFY] [models.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/dhan/models.py)
- Import `field` from `dataclasses`: `from dataclasses import dataclass, field`.
- Add `charges: Decimal = field(default_factory=lambda: Decimal("0"))` to `DhanOptionsSummary`.
- Add `brokerage: Decimal = field(default_factory=lambda: Decimal("0"))` to `DhanOptionsSummary`.
- Add `net_pnl` computed property:
```python
@property
def net_pnl(self) -> Decimal:
    """realized_pnl minus all charges and brokerage."""
    return self.realized_pnl - self.charges - self.brokerage
```

### Dhan Positions Logic

#### [MODIFY] [positions.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/dhan/positions.py)
- Implement `compute_charges(positions: list[DhanOptionPosition], trade_count: int) -> tuple[Decimal, Decimal]`.
- **Charge Rates (NSE F&O):**
    - `exchange_charges = 0.000530 × total_turnover`
    - `sebi_charges     = 0.000010 × total_turnover`
    - `stamp_duty       = 0.000030 × buy_turnover` (buy side only)
    - `stt              = 0.001000 × sell_turnover` (Budget 2024 rate, sell side only)
    - `gst              = 0.18 × (brokerage + exchange_charges + sebi_charges)`
- Update `build_options_summary` to accept `trade_count` and populate `charges` and `brokerage`.
- Update `format_options_section` to accept `month_charges` and `month_brokerage`.
- **New Output Format:**
```
📊 Dhan Options (Intraday)
Today P&L:    +10,400  gross
Today Cost:      -331  (chg: -231  brk: -100)
Today Net:    +10,069
Month P&L:    +6,344   gross
Month Cost:   -1,677   (chg: -877  brk: -800)
Month Net:    +4,667
Positions:   8
```

### Dhan Store

#### [MODIFY] [store.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/dhan/store.py)
- Update `DhanStore.__init__` (or a helper) to perform migration:
    - Use `PRAGMA table_info('dhan_options_snapshots')` to check for `charges` and `brokerage` columns.
    - Conditionally run `ALTER TABLE dhan_options_snapshots ADD COLUMN charges TEXT NOT NULL DEFAULT '0'`.
    - Conditionally run `ALTER TABLE dhan_options_snapshots ADD COLUMN brokerage TEXT NOT NULL DEFAULT '0'`.
- Update `record_options_snapshot` to persist `charges` and `brokerage` in the `INSERT` statement.
- Update `get_eod_options_snapshot` to populate `charges` and `brokerage` when reading from the DB.
- Implement `get_monthly_charges(self, year: int, month: int) -> tuple[Decimal, Decimal]`.

### Daily Snapshot Script

#### [MODIFY] [daily_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/daily_snapshot.py)
- Add `--dhan-trade-count` argument to `argparse`.
- In `_async_main` (live path):
    - Pass `args.dhan_trade_count` to `build_options_summary`.
    - Fetch `month_charges` and `month_brokerage` from the store.
    - Pass the new monthly values to `format_options_section`.
- In `_historical_main` (historical path):
    - Read `charges` and `brokerage` from the stored EOD row.
    - Fetch monthly totals from the store.
    - Pass all required args to `format_options_section`.

### Tests

#### [MODIFY] [test_positions.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/tests/unit/dhan/test_positions.py)
- Update `_make_options_summary` helper.
- Add `TestComputeCharges`.
- Add `TestNetPnl`.
- Update `TestFormatOptionsSection` calls to include `month_charges` and `month_brokerage`.

#### [MODIFY] [test_dhan_store_options.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/tests/unit/dhan/test_dhan_store_options.py)
- Update `_make_summary` helper.
- Add `TestRecordOptionsSnapshotCharges`.
- Add `TestGetMonthlyCharges`.

## Verification Plan

### Automated Tests
- Run all Dhan unit tests: `python -m pytest tests/unit/dhan/ --tb=short -q`
- **Numerical DoD:**
    - Verify `compute_charges` produces values within ±5% of actuals for May data (383/263/231 charges).
    - Verify `net_pnl` for May = +4,667 (≈ 6344 − 877 − 800) in tests.
- Verify DB migration correctly adds columns and default values work.
- Verify monthly totals aggregation.

### Manual Verification
- Run `python -m scripts.daily_snapshot --date <past_date>` to ensure historical view still works (charges should show as 0).
- Run a live snapshot (if credentials available) with `--dhan-trade-count 5` and verify the output format.
