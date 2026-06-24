# IC-E2 — `scripts/strategies/ic/paper_ic_entry.py`: 4-leg IC entry helper

> **Assigned to: Antigravity** — multi-file script with TDD loop; spec fully defined below.

**Prerequisite:** IC-E1 must be committed (`STRATEGY_IC` constant must exist in `src/paper/constants.py`).

**Files to create/change:**
- `scripts/strategies/ic/__init__.py` — new package init (one comment line)
- `scripts/strategies/ic/paper_ic_entry.py` — new entry script
- `tests/unit/strategies/ic/__init__.py` — new test package init
- `tests/unit/strategies/ic/test_paper_ic_entry.py` — new test file

---

## Purpose

Analogous to `scripts/strategies/cc_calibration/paper_cc_entry.py` but for a 4-leg IC.
Selects strikes, applies gates, prints (dry-run) or executes `record_paper_trade.py`
commands for all four legs.

---

## CLI

```
python scripts/strategies/ic/paper_ic_entry.py [--dry-run] [--force-entry] [--bod-path PATH]
```

| Flag | Default | Description |
|---|---|---|
| `--dry-run` / `--no-dry-run` | `--dry-run` | Print commands only; do not execute |
| `--force-entry` | off | Skip IVR gate and portfolio-delta gate (log WARNING for each bypassed gate) |
| `--bod-path PATH` | `DEFAULT_BOD_PATH` | Path to BOD instruments JSON |

---

## Implementation steps (in order)

### Step 1 — Duplicate guard

Query `PaperStore.get_open_positions()` filtered by `strategy_name == STRATEGY_IC`.
If any open position exists: print error and exit 1. One IC at a time.

### Step 2 — Mode detection

Query `PaperStore.get_open_positions()` filtered by `strategy_name == STRATEGY_CSP`.
- If CSP positions exist → `mode = "concurrent"`
- Else → `mode = "standalone"`

### Step 3 — Delta targets (asymmetric, council mandate 2026-05-02)

```python
# standalone
PUT_DELTA_TARGET_STANDALONE  = Decimal("0.15")   # ~15Δ
CALL_DELTA_TARGET_STANDALONE = Decimal("0.10")   # ~10Δ

# concurrent with open CSP
PUT_DELTA_TARGET_CONCURRENT  = Decimal("0.09")   # ~8–10Δ (use 9 as midpoint)
CALL_DELTA_TARGET_CONCURRENT = Decimal("0.13")   # ~12–15Δ (use 13 as midpoint)

DELTA_RANGE_LO = Decimal("0.06")   # ±6Δ band around target for both modes
DELTA_RANGE_HI = Decimal("0.22")
```

Tie-breaker: prefer farther OTM strike (lower absolute delta) when two strikes straddle target.
This is the default behaviour of `filter_strikes_by_delta` + `rank_strikes` — confirm before use.

### Step 4 — IVR gate (skip if `--force-entry`)

Load VIX series from `data/historical/ohlc/india_vix/` using `load_vix_series()`.
Fetch today's VIX via `fetch_vix_latest()`.
Compute `ivr = compute_ivr(vix_today, vix_series)`.
If `ivr is None` → log WARNING, continue (data gap, do not block entry).
If `ivr < 0.25` → print "IVR gate: BLOCKED (IVR={ivr:.2f} < 0.25)" and exit 1 unless `--force-entry`.

### Step 5 — Entry day / DTE window check (warn only, never block)

Resolve the next monthly Nifty expiry using `InstrumentLookup.get_expiry_candidates("NIFTY", today, ["monthly"])`.
Compute `dte = (expiry_date - today).days`.
If `dte < 30` or `dte > 45`: print WARNING "DTE {dte} outside 30–45 window — verify entry timing".
Do not block. Entry day Wednesday check is informational only (script may be run manually on
any day for testing or manual override).

### Step 6 — Live chain fetch

Use `UpstoxMarketClient(settings.upstox_analytics_token).get_option_chain("NSE_INDEX|Nifty 50", expiry_str)`
where `expiry_str = expiry_date.strftime("%Y-%m-%d")`.
Parse with `parse_upstox_option_chain(raw)` → `OptionChain`.

### Step 7 — Strike selection (4 legs)

Select short put:
```python
put_target = PUT_DELTA_TARGET_CONCURRENT if mode == "concurrent" else PUT_DELTA_TARGET_STANDALONE
short_put_candidates = filter_strikes_by_delta(chain, "PE", (DELTA_RANGE_LO, put_target + DELTA_RANGE_LO), put_target)
short_put = rank_strikes(short_put_candidates, put_target)[0]  # farther OTM on tie
```

Select long put: strike = `short_put.strike - 500` (500-point wing width). Look up instrument
key from BOD JSON via `InstrumentLookup`.

Select short call:
```python
call_target = CALL_DELTA_TARGET_CONCURRENT if mode == "concurrent" else CALL_DELTA_TARGET_STANDALONE
short_call_candidates = filter_strikes_by_delta(chain, "CE", (DELTA_RANGE_LO, call_target + DELTA_RANGE_LO), call_target)
short_call = rank_strikes(short_call_candidates, call_target)[0]
```

Select long call: strike = `short_call.strike + 500`. Look up instrument key from BOD JSON.

If any of the four legs cannot be resolved: print error with the failing leg and exit 1.

### Step 8 — Liquidity gate

Call `_apply_liquidity_gate(short_put_leg)` and `_apply_liquidity_gate(short_call_leg)`.
Import from `src.instruments.strike_selector`. If either fails the gate: print error and exit 1.
Long legs are not liquidity-gated (they are protection legs, not premium-collection legs).

### Step 9 — Portfolio interaction check (skip if `--force-entry`)

Fetch current portfolio delta via `PortfolioDeltaTracker.aggregate_delta(open_positions, nifty_spot, LOT_SIZE)`.
Compute IC's marginal delta contribution:
  `ic_delta = short_put_delta - short_call_delta`  (signed lot-equivalent, approximate)
  `projected_total = current_delta.total_delta_lots + ic_delta`

If `projected_total < Decimal("-0.05")` or `projected_total > Decimal("0.25")`:
  First attempt: try shifting the put wing one strike farther OTM (next farther strike).
  If still breaching: print "Portfolio delta gate: BLOCKED (projected={projected_total})" and exit 1.

Log the combined delta and both individual deltas regardless of gate outcome.

### Step 10 — Print / execute commands

For each of the four legs, build the `record_paper_trade.py` command:

```python
cmd = [
    "python", "scripts/record/record_paper_trade.py",
    "--strategy", STRATEGY_IC,
    "--instrument-key", leg.instrument_key,
    "--action", leg.action,          # SELL for short legs, BUY for long legs
    "--leg-role", leg.leg_role,      # short_put / long_put / short_call / long_call
    "--quantity", str(LOT_SIZE),
    "--entry-price", str(leg.mid_price),
    "--ivr", str(round(ivr, 4)) if ivr is not None else "0",
]
```

In dry-run mode: print each command prefixed with `[DRY-RUN]`.
In live mode: `subprocess.run(cmd, check=True)` for each leg in order:
  short_put → long_put → short_call → long_call.
  On any failure: print the error and exit 1 (do not attempt remaining legs).

### Step 11 — Summary output

Print a summary block to stdout:
```
Iron Condor Entry Summary
Mode        : standalone | concurrent-with-CSP
IVR         : 0.42
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

All tests must be offline (no network). Mock `UpstoxMarketClient`, `PaperStore`,
`load_vix_series`, `fetch_vix_latest`, and `InstrumentLookup`.

**Happy-path tests:**
1. Standalone mode (no CSP open) → puts 15Δ target, calls 10Δ target selected
2. Concurrent mode (CSP open) → puts 9Δ target, calls 13Δ target selected
3. `--dry-run` → no `subprocess.run` called; commands printed
4. IVR ≥ 0.25 → gate passes; IVR logged in command

**Error/edge-case tests:**
5. Open IC position already exists → exit 1 before any chain fetch
6. IVR < 0.25 without `--force-entry` → exit 1 with IVR gate message
7. IVR < 0.25 with `--force-entry` → gate bypassed, WARNING logged, continues
8. Projected portfolio delta > 0.25 without `--force-entry` → exit 1
9. Short put strike has no instrument key in BOD JSON → exit 1 with leg identification message
10. `_apply_liquidity_gate` rejects short call → exit 1 with liquidity gate message

---

## Commit

```
feat(scripts/ic): add paper_ic_entry.py — 4-leg IC entry helper

Why: No entry automation existed; operators had to construct 4 record_paper_trade
calls manually, error-prone and missing delta/IVR validation.
What:
- scripts/strategies/ic/__init__.py: new package
- scripts/strategies/ic/paper_ic_entry.py: 4-leg entry with gates + dual-mode delta
- tests/unit/strategies/ic/__init__.py: new test package
- tests/unit/strategies/ic/test_paper_ic_entry.py: 10 offline tests
Ref: ic-e2e IC-E2
```

---

## Pre-baked Context

**`filter_strikes_by_delta` / `rank_strikes` / `_apply_liquidity_gate`** — `src/instruments/strike_selector.py`.
Accepts `OptionChain`, option_type `"CE"` or `"PE"`, delta bounds tuple, target delta.
Returns list of `OptionChainStrike`. `rank_strikes` sorts by proximity to target; index 0 is best.

**`compute_ivr`** — `src/backtest/ivr.py`. Signature: `compute_ivr(vix_today: float, vix_series: pd.Series) -> float | None`.

**`load_vix_series` / `fetch_vix_latest`** — `src/backtest/vix_ingest.py`.

**`InstrumentLookup.get_expiry_candidates`** — `src/instruments/lookup.py`.
Returns list of dicts sorted by DTE; each dict has `expiry` (date), `dte` (int), `instrument_key`.
`preference=["monthly"]` restricts to monthly expiries.

**`PortfolioDeltaTracker`** — `src/risk/delta_tracker.py`.
`aggregate_delta(paper_positions, nifty_spot, lot_size) → PortfolioDelta`.
`PortfolioDelta.total_delta_lots` is a `Decimal`.

**`STRATEGY_IC`** — `src/paper/constants.py` (added in IC-E1). Value: `"paper_ic_nifty_v1"`.
**`STRATEGY_CSP`** — same file. Value: `"paper_csp_nifty_v1"`.
**`LOT_SIZE`** — same file. Current value: 65.
**`DEFAULT_BOD_PATH`** / **`DEFAULT_DB_PATH`** — same file.
