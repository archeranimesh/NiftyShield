# Strategy Spec — NS CC Short Call POC
## METADATA
| Field | Value |
|---|---|
| Strategy name | NS CC Short Call POC |
| Description | NiftyShield covered-call overlay, short call leg only: 15-delta monthly NIFTY call, Wednesday entry at 30-45 DTE, exits at 30% of credit, 2.5x credit, 0.55 delta, or DTE 5. |
| Default underlying | NIFTY 50 |
| Price execution | Market Price |
| Exit shorts first | Yes |
## INIT VARS (top-level)
| Name | Type | Default expression | Notes |
|---|---|---|---|
| entered | Number | `Number(1)` | one-shot guard: 1 = armed, flipped to 2 on entry |
## UNIVERSAL EXIT (OR-joined)
- (group, AND-joined)
  - `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,1),'LTP')` `<=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',1,1,1), Number(0.30), '*')`
  - `Traded Instrument('Entry','price','NIFTY 50',1,1,1)` `>=` `Number(15)`
- `LTP(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,1),'LTP')` `>=` `Math Operation(Traded Instrument('Entry','price','NIFTY 50',1,1,1), Number(2.5), '*')`
- `Delta(Traded Instrument Name('Entry','instrument','NIFTY 50',1,1,1))` `>=` `Number(0.55)`
- `Days Difference (D2-D1)(Today('NSE'), Traded Instrument Name('Entry','expiry','NIFTY 50',1,1,1))` `<=` `Number(5)`
## SETS
### Set 1: CC short call
#### Identity
| Field | Value |
|---|---|
| Set name | CC short call |
| Underlying | NIFTY 50 |
| List | 0 |
#### Entry condition
- `Get Runtime("entered")` `==` `Number(1)`
- `Week Day(NSE)` `==` `Number(3)`
- `Time(NSE)` `>=` `Number(1000)`
- `Days Difference (D2-D1)(Today('NSE'), Current Month Expiry('NIFTY 50', 0))` `>=` `Number(30)`
- `Days Difference (D2-D1)(Today('NSE'), Current Month Expiry('NIFTY 50', 0))` `<=` `Number(45)`
#### Legs
| # | Buy/Sell | Underlying | Type | Expiry | Strike | Qty | Product |
|---|---|---|---|---|---|---|---|
| 1 | S | NIFTY 50 | CE | Current Month | `Find Strike('NIFTY 50', Select Expiry('month', 0), 'delta', Number(0.15), 'CE', 'any')` | 1 | NRML |
#### Set Runtime Vars written on entry
| Name | Type | Value expression |
|---|---|---|
| entered | Number | `Number(2)` |
