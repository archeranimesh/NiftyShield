# Strategy Spec — NS Collar POC v1
## METADATA
| Field | Value |
|---|---|
| Strategy name | NS Collar POC v1 |
<!-- lint-ignore-length -->
| Description | NiftyShield collar overlay: long 0.20-delta put and short 0.18-delta call on the nearest monthly with at least 14 DTE; the call exits (30% of credit, 2.5x, 0.55 delta, DTE 5) or the put crash-monetize (5x debit, -0.80 delta) close both legs, then reopen. |
| Default underlying | NIFTY 50 |
| Price execution | Market Price |
| Exit shorts first | Yes |
## SETS
### Set 1: Collar current month
#### Identity
| Field | Value |
|---|---|
| Set name | Collar current month |
| Underlying | NIFTY 50 |
| List | 0 |
#### Entry condition (AND-joined)
- `Open Positions Detail('All','All','NIFTY 50','count')` `==` `Number(0)`
- `Time(NSE)` `>=` `Number(1000)`
- `Days Difference (D2-D1)(Today('NSE'), Current Month Expiry('NIFTY 50', 0))` `>=` `Number(14)`
#### Legs
| # | Buy/Sell | Underlying | Type | Expiry | Strike | Qty | Product |
|---|---|---|---|---|---|---|---|
| 1 | B | NIFTY 50 | PE | Current Month | `Find Strike('NIFTY 50', Select Expiry('month', 0), 'delta', Number(-0.20), 'PE', 'any')` | 1 | NRML |
| 2 | S | NIFTY 50 | CE | Current Month | `Find Strike('NIFTY 50', Select Expiry('month', 0), 'delta', Number(0.18), 'CE', 'any')` | 1 | NRML |
#### Exit condition (AND-joined)
- `Net Quantity(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,2))` `!=` `Number(0)`
- (group, OR-joined)
  - (group, AND-joined)
    - `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,2),'LTP')` `<=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',1,1,2), Number(0.30), '*')`
    - `Traded Instrument('Entry','price','NIFTY 50',1,1,2)` `>=` `Number(15)`
  - `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,2),'LTP')` `>=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',1,1,2), Number(2.5), '*')`
  - `Delta(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,2))` `>=` `Number(0.55)`
  - `Days Difference (D2-D1)(Today('NSE'), Traded Instrument Name('Entry','expiry','NIFTY 50',1,1,2))` `<=` `Number(5)`
  - `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,1),'LTP')` `>=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',1,1,1), Number(5), '*')`
  - `Delta(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,1))` `<=` `Number(-0.80)`
### Set 2: Collar next month
#### Identity
| Field | Value |
|---|---|
| Set name | Collar next month |
| Underlying | NIFTY 50 |
| List | 0 |
#### Entry condition (AND-joined)
- `Open Positions Detail('All','All','NIFTY 50','count')` `==` `Number(0)`
- `Time(NSE)` `>=` `Number(1000)`
- `Days Difference (D2-D1)(Today('NSE'), Current Month Expiry('NIFTY 50', 0))` `<` `Number(14)`
#### Legs
| # | Buy/Sell | Underlying | Type | Expiry | Strike | Qty | Product |
|---|---|---|---|---|---|---|---|
| 1 | B | NIFTY 50 | PE | Next Month | `Find Strike('NIFTY 50', Select Expiry('month', 1), 'delta', Number(-0.20), 'PE', 'any')` | 1 | NRML |
| 2 | S | NIFTY 50 | CE | Next Month | `Find Strike('NIFTY 50', Select Expiry('month', 1), 'delta', Number(0.18), 'CE', 'any')` | 1 | NRML |
#### Exit condition (AND-joined)
- `Net Quantity(Traded Instrument Name('Entry','instrument','NIFTY 50',2,1,2))` `!=` `Number(0)`
- (group, OR-joined)
  - (group, AND-joined)
    - `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',2,1,2),'LTP')` `<=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',2,1,2), Number(0.30), '*')`
    - `Traded Instrument('Entry','price','NIFTY 50',2,1,2)` `>=` `Number(15)`
  - `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',2,1,2),'LTP')` `>=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',2,1,2), Number(2.5), '*')`
  - `Delta(Traded Instrument Name('Entry','instrument','NIFTY 50',2,1,2))` `>=` `Number(0.55)`
  - `Days Difference (D2-D1)(Today('NSE'), Traded Instrument Name('Entry','expiry','NIFTY 50',2,1,2))` `<=` `Number(5)`
  - `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',2,1,1),'LTP')` `>=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',2,1,1), Number(5), '*')`
  - `Delta(Traded Instrument Name('Entry','instrument','NIFTY 50',2,1,1))` `<=` `Number(-0.80)`
