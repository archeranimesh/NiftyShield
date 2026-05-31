# PB3.1 — `src/strategy/ic_nifty_v1.py`: IronCondorV1 + tests

**Files to change:**
- `src/strategy/ic_nifty_v1.py` — `IronCondorV1` implements `PaperStrategy`
- `tests/unit/strategy/test_ic_nifty_v1.py` — new test file

**Before implementing:** Read `docs/strategies/ic_nifty_v1.md` — authoritative spec.
Also read council ruling: `docs/council/2026-05-02_iron-condor-v1-core-design.md` —
no adjustments in v1; all ACTION events route to exit only.

**What to implement:**

```python
class IronCondorV1:
    strategy_name = "paper_ic_nifty_v1"
```

Signal table (from strategy spec):

| Event type | Severity | Trigger |
|---|---|---|
| `PROFIT_TARGET` | ACTION | mark ≤ 50% of entry credit |
| `LOSS_STOP` | ACTION | mark ≥ 2.0× entry credit |
| `DELTA_STOP` | ACTION | either short leg \|delta\| ≥ 0.35 |
| `TIME_STOP` | ACTION | DTE ≤ 14 |
| `DELTA_WARN` | WARN | either short leg \|delta\| ≥ 0.25 |
| `DTE_WARN` | INFO | DTE ≤ 21 |

No open position → `check_signals()` returns `[]`. Entry is manual via
`scripts/paper_ic_entry.py` (not in this phase; document as future script).

`apply_action()` accepts only `CLOSE_FULL`, `CLOSE_CALL_SPREAD`, `CLOSE_PUT_SPREAD`.
Any other `action_type` raises `ValueError` — the spec forbids adjustments in v1.

`describe_context()` — returns: call spread delta, put spread delta, combined credit,
mark-to-market, DTE, IVR, Nifty spot.

**Tests (`tests/unit/strategy/test_ic_nifty_v1.py`):**

- No open positions → `[]`.
- Combined mark ≤ 50% of entry credit → `PROFIT_TARGET` ACTION.
- Combined mark ≥ 200% of entry credit → `LOSS_STOP` ACTION.
- Short call `|delta| = 0.36` → `DELTA_STOP` ACTION.
- Short put `|delta| = 0.36` → `DELTA_STOP` ACTION (either leg triggers it).
- DTE = 13 → `TIME_STOP` ACTION.
- Short call `|delta| = 0.27` → `DELTA_WARN` WARN.
- DTE = 19 → `DTE_WARN` INFO.
- Healthy IC (mark 70%, both deltas 0.15, DTE 30) → `[]`.
- `apply_action(CLOSE_FULL)` → no error.
- `apply_action(CLOSE_CALL_SPREAD)` → no error.
- `apply_action(ADJUST_WINGS)` → raises `ValueError`.

**Commit:** `feat(strategy): add IronCondorV1 backbone integration`

---

## Pre-baked Context

> Graph queries pre-run 2026-05-31. Skip "Before any code" graph calls — use these directly.

**`PaperStrategy`** — `src/strategy/protocol.py` (PB1.1). Protocol with three methods.
`strategy_name` class attribute must start with `"paper_"`.

**`PaperPosition`** — `src/paper/models.py:95`. Dataclass.
Fields: `strategy_name: str`, `leg_role: str`, `net_qty: int`, `avg_cost: Decimal`,
`avg_sell_price: Decimal`, `instrument_key: str`.
IC leg roles to filter: `"short_call"`, `"short_put"`, `"long_call_hedge"`, `"long_put_hedge"`
(confirm actual leg_role strings from live `paper_trades` rows before implementing).

**`OptionChain`** — `src/models/options.py:69`.
Fields: `underlying_spot: Decimal`, `expiry: date`, `strikes: dict[Decimal, OptionChainStrike]`.

**`SignalEvent`** — `src/strategy/protocol.py`. severity literals: `"INFO"`, `"WARN"`, `"ACTION"`.

**Council ruling** — `docs/council/2026-05-02_iron-condor-v1-core-design.md`: v1 has no
wing adjustments. If `apply_action` receives anything other than the three allowed
action_types, it must raise `ValueError` immediately — the spec is intentionally strict.
