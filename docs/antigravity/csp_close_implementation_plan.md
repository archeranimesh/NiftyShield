# Extension of `--close` in `record_paper_trade.py`

This plan details the implementation of automatic instrument key resolution and price fetching for the `--close` flag in `scripts/record_paper_trade.py`. When `--close` is used, the script will attempt to find the instrument key from the current open position in the database and fetch the latest market price (LTP) if they are not explicitly provided.

## Proposed Changes

### [scripts/record_paper_trade.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/record_paper_trade.py)

#### [MODIFY] [record_paper_trade.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/record_paper_trade.py)

1.  **Add `_resolve_from_position(args: argparse.Namespace) -> str | None`**:
    *   Instantiate `PaperStore(args.db_path)`.
    *   Call `get_position(args.strategy, args.leg)`.
    *   Check `pos.net_qty`. If `>= 0`, print error to `stderr` and return `None`.
    *   Print the resolved key: `Resolved key from position: {pos.instrument_key}`.
    *   Return `pos.instrument_key`.

2.  **Update `_resolve_instrument_key(args)`**:
    *   Insert a branch **before** the existing chain-mode check (`if not args.key and not args.underlying:`):
        ```python
        if args.close and not args.key and not args.underlying:
            key = _resolve_from_position(args)
            if key:
                return key
            # If _resolve_from_position returns None, it already printed error and we'll exit 1
            return None
        ```

3.  **Update `main()`**:
    *   After `instrument_key = _resolve_instrument_key(args)` and the `instrument_key is None` check.
    *   Locate the price guard block: `if args.price is None and (args.key or args.underlying):`.
    *   Modify it to handle LTP fetch when `--close` is set:
        ```python
        if args.price is None:
            if args.close:
                # Fetch LTP
                try:
                    client = UpstoxMarketClient()
                    ltp_dict = client.get_ltp_sync([instrument_key])
                    if instrument_key not in ltp_dict:
                        print(f"ERROR: LTP not found for {instrument_key}", file=sys.stderr)
                        sys.exit(1)
                    
                    price = ltp_dict[instrument_key]
                    print(f"Auto-price: LTP=₹{price}")
                    args.price = str(price)
                except ValueError as exc:
                    print(f"ERROR: {exc}", file=sys.stderr)
                    sys.exit(1)
                except Exception as exc:
                    print(f"ERROR: failed to fetch LTP — {exc}", file=sys.stderr)
                    sys.exit(1)
            elif args.key or args.underlying:
                print("ERROR: --price is required when not in chain mode (auto-expiry).", file=sys.stderr)
                sys.exit(1)
        ```
    *   Ensure `args.price` is converted to `Decimal(str(ltp_value))` in the `PaperTrade` construction (the code already does `Decimal(args.price)`).

## Verification Plan

### Automated Tests
I will add 4 new tests to `tests/unit/paper/test_record_paper_trade.py`:

1.  `test_close_auto_resolves_key_from_position`:
    *   Pre-seed a short position.
    *   Run with `--close` and no `--key`.
    *   Assert success and correct key in the trade.
2.  `test_close_auto_key_flat_position_exits_1`:
    *   No position or flat position.
    *   Run with `--close` and no `--key`.
    *   Assert exit code 1 and error message.
3.  `test_close_auto_fetches_ltp_when_no_price`:
    *   Mock `UpstoxMarketClient.get_ltp_sync`.
    *   Run with `--close` and no `--price`.
    *   Assert LTP is used as price.
4.  `test_close_explicit_key_skips_db_lookup`:
    *   Mock `PaperStore.get_position`.
    *   Run with `--close` and explicit `--key`.
    *   Assert `get_position` is NOT called.

### Manual Verification
*   Run `python -m pytest tests/unit/paper/test_record_paper_trade.py --tb=no -q`.
*   Verify all 23 tests pass.
