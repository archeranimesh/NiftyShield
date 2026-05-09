# Implementation Plan — Dhan Charges Implementation

Add auto-computed trading charges (STT, exchange, SEBI, stamp duty, GST, brokerage) to the Dhan intraday options P&L. Charges are computed from position data already fetched. Brokerage requires a user-supplied `--dhan-trade-count`.

## User Review Required

> [!IMPORTANT]
> This change involves a database schema migration for the `dhan_options_snapshots` table. The migration adds `charges` and `brokerage` columns as `TEXT` with a default of `'0'`. This is handled automatically on `DhanStore` initialization.

## Proposed Changes

### Dhan Models

#### [MODIFY] [models.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/dhan/models.py)
- Add `charges: Decimal = field(default_factory=lambda: Decimal("0"))` to `DhanOptionsSummary`.
- Add `brokerage: Decimal = field(default_factory=lambda: Decimal("0"))` to `DhanOptionsSummary`.
- Add `net_pnl` computed property to `DhanOptionsSummary`.

### Dhan Positions Logic

#### [MODIFY] [positions.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/dhan/positions.py)
- Implement `compute_charges(positions: list[DhanOptionPosition], trade_count: int) -> tuple[Decimal, Decimal]`.
- Update `build_options_summary` to accept `trade_count` and populate `charges` and `brokerage`.
- Update `format_options_section` to accept `month_charges` and `month_brokerage` and update the output format to include net P&L and cost breakdown.

### Dhan Store

#### [MODIFY] [store.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/dhan/store.py)
- Update `DhanStore.__init__` to perform schema migration (add `charges` and `brokerage` columns if missing).
- Update `record_options_snapshot` to persist `charges` and `brokerage`.
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
- Update `TestFormatOptionsSection`.

#### [MODIFY] [test_dhan_store_options.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/tests/unit/dhan/test_dhan_store_options.py)
- Update `_make_summary` helper.
- Add `TestRecordOptionsSnapshotCharges`.
- Add `TestGetMonthlyCharges`.

## Verification Plan

### Automated Tests
- Run all Dhan unit tests: `python -m pytest tests/unit/dhan/ --tb=short -q`
- Verify `compute_charges` precision and rounding.
- Verify DB migration doesn't break existing data.
- Verify monthly totals aggregation.

### Manual Verification
- Run `python -m scripts.daily_snapshot --date <past_date>` to ensure historical view still works (charges should show as 0).
- Run a live snapshot (if credentials available) with `--dhan-trade-count 5` and verify the output format.
