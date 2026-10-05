# Strategy Spec — NS CC Short Call POC v2
## METADATA
| Field | Value |
|---|---|
| Strategy name | NS CC Short Call POC v2 |
<!-- lint-ignore-length -->
| Description | NiftyShield covered-call overlay, short call leg only, live-code rules: 15-delta call on the nearest monthly expiry with at least 14 DTE, any weekday, exits at 30% of credit, 2.5x credit, 0.55 delta, or DTE 5. |
| Default underlying | NIFTY 50 |
| Price execution | Market Price |
| Exit shorts first | Yes |
## SETS
### Set 1: CC current month
#### Identity
| Field | Value |
|---|---|
| Set name | CC current month |
| Underlying | NIFTY 50 |
| List | 0 |
#### Entry condition (AND-joined)
- `Open Positions Detail('All','CE','NIFTY 50','count')` `==` `Number(0)`
- `Time(NSE)` `>=` `Number(1000)`
- `Days Difference (D2-D1)(Today('NSE'), Current Month Expiry('NIFTY 50', 0))` `>=` `Number(14)`
#### Legs
| # | Buy/Sell | Underlying | Type | Expiry | Strike | Qty | Product |
|---|---|---|---|---|---|---|---|
| 1 | S | NIFTY 50 | CE | Current Month | `Find Strike('NIFTY 50', Select Expiry('month', 0), 'delta', Number(0.15), 'CE', 'any')` | 1 | NRML |
#### Exit condition (AND-joined)
- `Net Quantity(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,1))` `!=` `Number(0)`
- (group, OR-joined)
  - (group, AND-joined)
    - `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,1),'LTP')` `<=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',1,1,1), Number(0.30), '*')`
    - `Traded Instrument('Entry','price','NIFTY 50',1,1,1)` `>=` `Number(15)`
  - `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,1),'LTP')` `>=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',1,1,1), Number(2.5), '*')`
  - `Delta(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,1))` `>=` `Number(0.55)`
  - `Days Difference (D2-D1)(Today('NSE'), Traded Instrument Name('Entry','expiry','NIFTY 50',1,1,1))` `<=` `Number(5)`
### Set 2: CC next month
#### Identity
| Field | Value |
|---|---|
| Set name | CC next month |
| Underlying | NIFTY 50 |
| List | 0 |
#### Entry condition (AND-joined)
- `Open Positions Detail('All','CE','NIFTY 50','count')` `==` `Number(0)`
- `Time(NSE)` `>=` `Number(1000)`
- `Days Difference (D2-D1)(Today('NSE'), Current Month Expiry('NIFTY 50', 0))` `<` `Number(14)`
#### Legs
| # | Buy/Sell | Underlying | Type | Expiry | Strike | Qty | Product |
|---|---|---|---|---|---|---|---|
| 1 | S | NIFTY 50 | CE | Next Month | `Find Strike('NIFTY 50', Select Expiry('month', 1), 'delta', Number(0.15), 'CE', 'any')` | 1 | NRML |
#### Exit condition (AND-joined)
- `Net Quantity(Traded Instrument Name('Entry','instrument','NIFTY 50',2,1,1))` `!=` `Number(0)`
- (group, OR-joined)
  - (group, AND-joined)
    - `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',2,1,1),'LTP')` `<=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',2,1,1), Number(0.30), '*')`
    - `Traded Instrument('Entry','price','NIFTY 50',2,1,1)` `>=` `Number(15)`
  - `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',2,1,1),'LTP')` `>=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',2,1,1), Number(2.5), '*')`
  - `Delta(Traded Instrument Name('Entry','instrument','NIFTY 50',2,1,1))` `>=` `Number(0.55)`
  - `Days Difference (D2-D1)(Today('NSE'), Traded Instrument Name('Entry','expiry','NIFTY 50',2,1,1))` `<=` `Number(5)`
