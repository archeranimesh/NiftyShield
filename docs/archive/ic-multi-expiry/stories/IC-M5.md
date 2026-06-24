# IC-M5 — `paper_ic_entry.py` with `--expiry-type` flag (supersedes ic-e2e IC-E2)

> **Assigned to: Antigravity** — multi-file script with TDD loop; fully specified below.

**This story supersedes ic-e2e IC-E2.** Do not implement IC-E2 from the ic-e2e plan.

**Prerequisites (all must be committed before starting):**
- ic-multi-expiry IC-M1 — `ICExpiryConfig` + `CONFIGS` + strategy name constants
- ic-multi-expiry IC-M2 — parameterised `IronCondorV1`
- ic-multi-expiry IC-M3 — weekly bucket in `get_expiry_candidates()`

**Files to create/change:**
- `scripts/strategies/ic/__init__.py` — new package init (one comment line)
- `scripts/strategies/ic/paper_ic_entry.py` — new entry script
- `tests/unit/strategies/ic/__init__.py` — new test package init
- `tests/unit/strategies/ic/test_paper_ic_entry.py` — new test file

---

## Purpose

Single entry script for all four IC expiry types. Replaces what ic-e2e IC-E2 would
have built (monthly-only, hardcoded targets). One script, one `--expiry-type` flag,
all gates preserved.

---

## CLI

```
python scripts/strategies/ic/paper_ic_entry.py \
    --expiry-type [weekly|monthly|leaps|yearly] \
    [--dry-run] [--force-entry] [--bod-path PATH]
```

| Flag | Default | Description |
|---|---|---|
| `--expiry-type` | required | Which expiry bucket to trade |
| `--dry-run` / `--no-dry-run` | `--dry-run` | Print commands only; do not execute |
| `--force-entry` | off | Skip IVR gate and portfolio-delta gate (log WARNING for each) |
| `--bod-path PATH` | `DEFAULT_BOD_PATH` | Path to BOD instruments JSON |

---

## Implementation steps (in order)

### Step 1 — Load config

```python
from src.strategy.ic_expiry_config import CONFIGS
config = CONFIGS[args.expiry_type]
strategy_name = config.strategy_name
```

### Step 2 — Duplicate guard

Query `PaperStore.get_open_positions()` filtered by `strategy_name == config.strategy_name`.
If any open position exists → print error and exit 1. One IC per expiry type at a time.

### Step 3 — Mode detection

Query open positions for `strategy_name == STRATEGY_CSP`.
- CSP positions exist → `mode = "concurrent"`
- Else → `mode = "standalone"`

### Step 4 — Delta targets (asymmetric, from ic-e2e IC-E2 council mandate 2026-05-02)

These delta targets apply to **all expiry types** — the asymmetry is about CSP interaction,
not expiry. Expiry-specific calibration comes from paper data after ≥6 cycles.

```python
PUT_DELTA_TARGET_STANDALONE  = Decimal("0.15")
CALL_DELTA_TARGET_STANDALONE = Decimal("0.10")
PUT_DELTA_TARGET_CONCURRENT  = Decimal("0.09")
CALL_DELTA_TARGET_CONCURRENT = Decimal("0.13")
DELTA_RANGE_LO = Decimal("0.06")
DELTA_RANGE_HI = Decimal("0.22")
```

### Step 5 — IVR gate (skip if `--force-entry`)

Load VIX series; compute `ivr = compute_ivr(vix_today, vix_series)`.
If `ivr < 0.25` → exit 1 unless `--force-entry`.

**Weekly exception:** for `expiry_type == "weekly"`, IVR gate threshold is **0.15** (weekly
premium is thin enough that low-IVR entry is less punishing than for monthly). Log the
threshold used in both pass and block cases.

### Step 6 — DTE window check (warn only)

Resolve expiry using `get_expiry_candidates("NIFTY", today, [config.expiry_bucket])`.
If no candidate found → print error and exit 1.

Per-type DTE windows (warn if outside; do not block):
- weekly: DTE 3–7
- monthly: DTE 30–45
- leaps: DTE 60–90
- yearly: DTE 180–270

### Step 7 — Live chain fetch

Use `UpstoxMarketClient(settings.upstox_analytics_token).get_option_chain("NSE_INDEX|Nifty 50", expiry_str)`.

### Step 8 — Strike selection (4 legs)

Same logic as ic-e2e IC-E2: `filter_strikes_by_delta` + `rank_strikes` for short legs;
fixed 500-point wing width for long legs; BOD JSON lookup for long leg instrument keys.

### Step 9 — Liquidity gate

`_apply_liquidity_gate` on both short legs. Long legs not gated.

**Weekly exception:** liquidity gate uses a lower OI floor for weekly legs — pass
`min_oi=500` explicitly if `expiry_type == "weekly"` (default is 1000 for monthly+).
Check `_apply_liquidity_gate` signature before implementing — if it does not accept
`min_oi`, this exception is deferred to a future calibration story and a WARNING is logged.

### Step 10 — Portfolio interaction check (skip if `--force-entry`)

Same as ic-e2e IC-E2 — `PortfolioDeltaTracker.aggregate_delta`; projected delta check
with one-strike adjustment attempt before blocking.

### Step 11 — Print / execute commands

Build `record_paper_trade.py` commands for all four legs with `--strategy config.strategy_name`.
Leg order: short_put → long_put → short_call → long_call.

### Step 12 — Summary output

```
Iron Condor Entry Summary
Expiry type : weekly | monthly | leaps | yearly
Strategy    : paper_ic_nifty_v1_monthly
Mode        : standalone | concurrent-with-CSP
IVR         : 0.42  (gate threshold: 0.25)
DTE         : 35
Nifty spot  : 24750

Short Put   : NIFTY24750PE  δ=-0.149  mid=₹85.50
Long Put    : NIFTY24250PE  (protection)
Short Call  : NIFTY25200CE  δ=0.098   mid=₹42.25
Long Call   : NIFTY25700CE  (protection)

Net credit  : ₹127.75 / lot  (₹8,304 for 65 units)
```

---

## Tests (`tests/unit/strategies/ic/test_paper_ic_entry.py`)

All offline. Mock `UpstoxMarketClient`, `PaperStore`, `load_vix_series`, `fetch_vix_latest`,
`InstrumentLookup`, `subprocess.run`.

**Happy-path tests:**
1. `--expiry-type monthly`, standalone → monthly strategy_name, 15Δ put / 10Δ call targets
2. `--expiry-type monthly`, concurrent → 9Δ put / 13Δ call targets
3. `--expiry-type weekly` → weekly strategy_name, IVR gate uses 0.15 threshold
4. `--expiry-type leaps` → leaps strategy_name emitted in record command
5. `--dry-run` → `subprocess.run` not called; `[DRY-RUN]` prefix in output
6. IVR ≥ threshold → gate passes; IVR logged in record command

**Error/edge-case tests:**
7. Open position for same strategy_name exists → exit 1, no chain fetch
8. `--expiry-type monthly`, IVR < 0.25, no `--force-entry` → exit 1
9. `--expiry-type monthly`, IVR < 0.25, `--force-entry` → WARNING logged, continues
10. No expiry candidate found for bucket → exit 1
11. Short put BOD lookup fails → exit 1 with leg identification message
12. Projected portfolio delta breaches → exit 1 without `--force-entry`

---

## Commit

```
feat(scripts/ic): paper_ic_entry.py — multi-expiry IC entry with --expiry-type

Why: Research pipeline needs independent entry across four expiry types from
a single script; ic-e2e IC-E2 spec superseded by multi-expiry design.
What:
- scripts/strategies/ic/__init__.py: new package
- scripts/strategies/ic/paper_ic_entry.py: entry script with expiry-type routing
- tests/unit/strategies/ic/__init__.py: new test package
- tests/unit/strategies/ic/test_paper_ic_entry.py: 12 offline tests
Ref: ic-multi-expiry IC-M5
```

---

## Pre-baked Context

**`CONFIGS`** import: `from src.strategy.ic_expiry_config import CONFIGS`
Keys: `"weekly"`, `"monthly"`, `"leaps"`, `"yearly"`.
Each `config.strategy_name` is the correct DB discriminator to pass to `--strategy`.

**`get_expiry_candidates`** — returns `list[tuple[str, str]]`: `(label, expiry_date_str)`.
Pass `preference=[config.expiry_bucket]` to get only the target expiry type.
`config.expiry_bucket` values: `"weekly"` / `"monthly"` / `"quarterly"` / `"yearly"`.

**`STRATEGY_CSP`** — `src.paper.constants`: `"paper_csp_nifty_v1"`.
**`LOT_SIZE`** — `src.paper.constants`: 65.
**`DEFAULT_BOD_PATH`** / **`DEFAULT_DB_PATH`** — same file.

**`filter_strikes_by_delta` / `rank_strikes` / `_apply_liquidity_gate`** — `src.instruments.strike_selector`.

**`compute_ivr`** — `src.backtest.ivr`. Signature: `compute_ivr(vix_today: float, vix_series: pd.Series) -> float | None`.

**`PortfolioDeltaTracker`** — `src.risk.delta_tracker`. `aggregate_delta(paper_positions, nifty_spot, lot_size) → PortfolioDelta`. `PortfolioDelta.total_delta_lots` is `Decimal`.

**`paper_cc_entry.py`** at `scripts/strategies/cc_calibration/paper_cc_entry.py` — use as
structural reference for IVR load, chain fetch, and subprocess.run pattern.
