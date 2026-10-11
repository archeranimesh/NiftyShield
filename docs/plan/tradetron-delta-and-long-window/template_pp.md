# Strategy Spec — NS PP Long Put POC v1
## METADATA
| Field | Value |
|---|---|
| Strategy name | NS PP Long Put POC v1 |
<!-- lint-ignore-length -->
| Description | NiftyShield protective-put overlay, long put leg only, live-code rules: 0.20-delta put on the nearest monthly expiry with at least 14 DTE, exits at 5x debit, -0.80 delta, or DTE 5, then reopens on the next monthly. |
| Default underlying | NIFTY 50 |
| Price execution | Market Price |
| Exit shorts first | Yes |
## SETS
### Set 1: PP current month
#### Identity
| Field | Value |
|---|---|
| Set name | PP current month |
| Underlying | NIFTY 50 |
| List | 0 |
#### Entry condition (AND-joined)
- `Open Positions Detail('All','PE','NIFTY 50','count')` `==` `Number(0)`
- `Time(NSE)` `>=` `Number(1000)`
- `Days Difference (D2-D1)(Today('NSE'), Current Month Expiry('NIFTY 50', 0))` `>=` `Number(14)`
#### Legs
| # | Buy/Sell | Underlying | Type | Expiry | Strike | Qty | Product |
|---|---|---|---|---|---|---|---|
| 1 | B | NIFTY 50 | PE | Current Month | `Find Strike('NIFTY 50', Select Expiry('month', 0), 'delta', Number(-0.20), 'PE', 'any')` | 1 | NRML |
#### Exit condition (AND-joined)
- `Net Quantity(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,1))` `!=` `Number(0)`
- (group, OR-joined)
  - `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,1),'LTP')` `>=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',1,1,1), Number(5), '*')`
  - `Delta(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,1))` `<=` `Number(-0.80)`
  - `Days Difference (D2-D1)(Today('NSE'), Traded Instrument Name('Entry','expiry','NIFTY 50',1,1,1))` `<=` `Number(5)`
### Set 2: PP next month
#### Identity
| Field | Value |
|---|---|
| Set name | PP next month |
| Underlying | NIFTY 50 |
| List | 0 |
#### Entry condition (AND-joined)
- `Open Positions Detail('All','PE','NIFTY 50','count')` `==` `Number(0)`
- `Time(NSE)` `>=` `Number(1000)`
- `Days Difference (D2-D1)(Today('NSE'), Current Month Expiry('NIFTY 50', 0))` `<` `Number(14)`
#### Legs
| # | Buy/Sell | Underlying | Type | Expiry | Strike | Qty | Product |
|---|---|---|---|---|---|---|---|
| 1 | B | NIFTY 50 | PE | Next Month | `Find Strike('NIFTY 50', Select Expiry('month', 1), 'delta', Number(-0.20), 'PE', 'any')` | 1 | NRML |
#### Exit condition (AND-joined)
- `Net Quantity(Traded Instrument Name('Entry','instrument','NIFTY 50',2,1,1))` `!=` `Number(0)`
- (group, OR-joined)
  - `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',2,1,1),'LTP')` `>=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',2,1,1), Number(5), '*')`
  - `Delta(Traded Instrument Name('Entry','instrument','NIFTY 50',2,1,1))` `<=` `Number(-0.80)`
  - `Days Difference (D2-D1)(Today('NSE'), Traded Instrument Name('Entry','expiry','NIFTY 50',2,1,1))` `<=` `Number(5)`
