# Tradetron IC templates — saved copies

> Pulled 2026-10-04 via `tt_get_sample_strategy('iron_condor')` and `tt_get_sample_strategy('pilot_calm')`, so the MCP need not be called again for these. Both are `validate_before_create: true` —
> still run `tt_validate_markdown` before `tt_create_strategy`. Comparison with `docs/strategies/ic_nifty_v1.md` is in `tradetron.md` §"IC v1 vs Tradetron templates". The METADATA `Description` row is
> shortened here to stay under the 200-char doc-line limit; restore the full text only if you want the teaching prose in the created strategy.

## Shared mechanics (both templates)

- **Margin-safe order.** The platform rule for mixed BUY+SELL: BUY wings at Entry, SELL body in a Repair Once gated by the `entered` runtime var. Never put SELL legs at Entry (naked-short margin
  block). `Exit shorts first = Yes`.
- **Strikes** are signed ATM SPOT offsets: `ATM SPOT("NIFTY 50", n)`, n in strike steps (positive = CE side, negative = PE side). Body ±1, wings ±4 in both templates.
- **Strategy-level PNL exits** live in the UNIVERSAL EXIT, never in a Set Exit (D12: loop / double-count). Targets are written `Math Operation(Number(N), Multiplier(), '*')`.
- **Tolerated warning:** `REPAIR_SQUAREOFF_NOT_ANCHORED` on the Repair Once is a known false positive (the repair opens the body, it does not square off). Do not anchor with Traded Instrument.
- **Entry signals in both are placeholders** (time gate / weekday). Swap for the real signal.
- Qty is in lots (1), product NRML, expiry `Current Week`, underlying `NIFTY 50`, price execution `Market Price`.

## Template A — `iron_condor`

Exit: `PNL() >= 1500 × Multiplier` OR `Time(NSE) >= 1515`. One-shot guard `entered`: 1 = flat, flipped to 2 on entry, which arms the body Repair Once. Entry gate `Time(NSE) >= 920`.

```markdown
# Strategy Spec — Iron Condor (reference)
## METADATA
| Field | Value |
|---|---|
| Strategy name | Iron Condor NIFTY (reference) |
| Description | Short iron condor, margin-safe: BUY ATM+4 CE / ATM-4 PE wings at Entry, SELL ATM+1 CE / ATM-1 PE body in one Repair Once gated by the entered var. |
| Default underlying | NIFTY 50 |
| Price execution | Market Price |
| Exit shorts first | Yes |
## INIT VARS (top-level)
| Name | Type | Default expression | Notes |
|---|---|---|---|
| entered | number | `Number(1)` | one-shot guard: 1 = flat (wings armed), flipped to 2 on entry which also arms the body Repair Once |
## SETS
### Set 1: Iron condor
#### Identity
| Field | Value |
|---|---|
| Set name | Iron condor |
| Underlying | NIFTY 50 |
| List | 0 |
#### Entry condition
- `Time(NSE)` `>=` `Number(920)`
- `Get Runtime("entered")` `==` `Number(1)`
#### Legs
| # | Buy/Sell | Underlying | Type | Expiry | Strike | Qty | Product |
|---|---|---|---|---|---|---|---|
| 1 | B | NIFTY 50 | PE | Current Week | `ATM SPOT("NIFTY 50", -4)` | 1 | NRML |
| 2 | B | NIFTY 50 | CE | Current Week | `ATM SPOT("NIFTY 50", 4)` | 1 | NRML |
#### Set Runtime Vars written on entry
| Name | Type | Value expression |
|---|---|---|
| entered | number | `Number(2)` |
#### Repair conditions
##### Repair 1: Sell the inner short strangle body (margin-safe, after the wings)
| Field | Value |
|---|---|
| Type | Repair Once |
| Sub-type | None |
###### Condition
- `Get Runtime("entered")` `==` `Number(2)`
###### Positions
| # | Buy/Sell | Underlying | Type | Expiry | Strike | Qty | Product |
|---|---|---|---|---|---|---|---|
| 1 | S | NIFTY 50 | PE | Current Week | `ATM SPOT("NIFTY 50", -1)` | 1 | NRML |
| 2 | S | NIFTY 50 | CE | Current Week | `ATM SPOT("NIFTY 50", 1)` | 1 | NRML |
## UNIVERSAL EXIT (OR-joined)
- `PNL()` `>=` `Math Operation(Number(1500), Multiplier(), '*')`
- `Time(NSE)` `>=` `Number(1515)`
```

## Template B — `pilot_calm` (flagship CREATE shape)

Entry: flat (`Open Positions("NIFTY 50") == 0`), 10:00–14:00, Wednesday (`Week Day(NSE) == 3`). `entered` starts at 0 and is set to 1 on entry, which arms the body Repair Once. Exit: `Time >= 1515` OR
`PNL >= +2000 × Multiplier` OR `PNL <= -4000 × Multiplier`. The flat guard is `Open Positions`, not a scoped Positions Detail (verified 2026-07-13). The template's old reference JSON is **deprecated**
(all legs at Entry → naked-short margin block); the markdown below is the source of truth.

```markdown
# Strategy Spec — Iron Condor pilot_calm (margin-safe reference CREATE shape)
## METADATA
| Field | Value |
|---|---|
| Strategy name | Iron Condor pilot_calm Reference |
| Description | Margin-safe short iron condor on weekly NIFTY: wings at Entry, inner short strangle via Repair Once once entered==1. Wednesday 10:00-14:00 window is a placeholder signal. |
| Default underlying | NIFTY 50 |
| Price execution | Market Price |
| Exit shorts first | Yes |
## INIT VARS (top-level)
| Name | Type | Default expression | Notes |
|---|---|---|---|
| entered | Number | `Number(0)` | Repair Once gate: set to 1 on entry so the inner short strangle is sold once, right after the wings are placed (margin safety) |
## SETS
### Set 1: A_CALM
#### Identity
| Field | Value |
|---|---|
| Set name | A_CALM |
| Underlying | NIFTY 50 |
| List | 0 |
#### Entry condition
- `Open Positions("NIFTY 50")` `==` `Number(0)`
- `Time(NSE)` `>=` `Number(1000)`
- `Time(NSE)` `<=` `Number(1400)`
- `Week Day(NSE)` `==` `Number(3)`
#### Legs
| # | Buy/Sell | Underlying | Type | Expiry | Strike | Qty | Product |
|---|---|---|---|---|---|---|---|
| 1 | B | NIFTY 50 | CE | Current Week | `ATM SPOT("NIFTY 50", 4)` | 1 | NRML |
| 2 | B | NIFTY 50 | PE | Current Week | `ATM SPOT("NIFTY 50", -4)` | 1 | NRML |
#### Set Runtime Vars written on entry
| Name | Type | Value expression |
|---|---|---|
| entered | Number | `Number(1)` |
#### Repair conditions
##### Repair 1: Sell the inner short strangle to complete the condor (after the wings, margin-safe)
| Field | Value |
|---|---|
| Type | Repair Once |
| Sub-type | None |
###### Condition
- `Get Runtime("entered")` `==` `Number(1)`
###### Positions
| # | Buy/Sell | Underlying | Type | Expiry | Strike | Qty | Product |
|---|---|---|---|---|---|---|---|
| 1 | S | NIFTY 50 | CE | Current Week | `ATM SPOT("NIFTY 50", 1)` | 1 | NRML |
| 2 | S | NIFTY 50 | PE | Current Week | `ATM SPOT("NIFTY 50", -1)` | 1 | NRML |
## UNIVERSAL EXIT (OR-joined)
- `Time(NSE)` `>=` `Number(1515)`
- `PNL()` `>=` `Math Operation(Number(2000), Multiplier(), '*')`
- `PNL()` `<=` `Math Operation(Number(-4000), Multiplier(), '*')`
```
