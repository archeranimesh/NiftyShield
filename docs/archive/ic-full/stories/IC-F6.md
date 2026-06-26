# IC-F6 — `paper_ic_entry.py` with `--expiry-type` and config-driven parameters

> **Assigned to: Antigravity** — new multi-file script; TDD loop.

**Prerequisites (all committed before starting):**
- IC-F2 — `ICExpiryConfig` + `CONFIGS`
- IC-F3 — parameterised `IronCondorV1` (strategy names stable)
- IC-F4 — weekly bucket in `get_expiry_candidates()`

**Files to create:**
- `scripts/strategies/ic/__init__.py` — one comment line
- `scripts/strategies/ic/paper_ic_entry.py`
- `tests/unit/strategies/ic/__init__.py` — one comment line
- `tests/unit/strategies/ic/test_paper_ic_entry.py`

---

## CLI

```
python scripts/strategies/ic/paper_ic_entry.py \
    --expiry-type [weekly|monthly|leaps|yearly] \
    [--dry-run | --no-dry-run] \
    [--force-entry] \
    [--bod-path PATH]
```

| Flag | Default | Description |
|---|---|---|
| `--expiry-type` | required | Which expiry bucket to trade |
| `--dry-run` | on | Print commands; do not execute |
| `--force-entry` | off | Skip IVR gate and portfolio-delta gate; log WARNING per bypass |
| `--bod-path` | `DEFAULT_BOD_PATH` | Path to BOD instruments JSON |

---

## Implementation (in order)

**Step 1 — Load config**
```python
from src.strategy.ic_expiry_config import CONFIGS
config = CONFIGS[args.expiry_type]
```

**Step 2 — Duplicate guard**
`store.get_positions(config.strategy_name)` — if any open position → print error, exit 1.

**Step 3 — Mode detection**
Open CSP positions (`STRATEGY_CSP`) → `mode = "concurrent"`, else `mode = "standalone"`.

**Step 4 — Delta targets** (asymmetric per mode; same across expiry types — see rationale)
```python
# standalone
PUT_DELTA_STANDALONE  = config.short_put_delta
CALL_DELTA_STANDALONE = config.short_call_delta

# concurrent with open CSP (shift both legs farther OTM)
PUT_DELTA_CONCURRENT  = config.short_put_delta - Decimal("0.06")
CALL_DELTA_CONCURRENT = config.short_call_delta + Decimal("0.03")
```
Rationale: when CSP is open, the portfolio already has short-put delta exposure.
Shifting IC put farther OTM reduces net short-put concentration. Call bias adjusts
correspondingly. The offset values (0.06 / 0.03) are the same as the original
monthly council ruling — proportional to the base delta.

**Step 5 — IVR gate** (skip if `--force-entry`)
Load VIX → compute IVR. Block if `ivr < config.ivr_gate`. Log threshold used.

**Step 6 — DTE window check** (warn only, never block)
`get_expiry_candidates("NIFTY", today, [config.expiry_bucket])`. If empty → exit 1.
Warn if DTE outside `[config.dte_warn_lo, config.dte_warn_hi]`.

**Step 7 — Live chain fetch**
`UpstoxMarketClient(settings.upstox_analytics_token).get_option_chain("NSE_INDEX|Nifty 50", expiry_str)`.

**Step 8 — Strike selection (4 legs)**
```
short_put:  filter_strikes_by_delta(chain, "PE", delta_range, put_target) → rank → [0]
long_put:   strike = short_put.strike - config.wing_width_points  → BOD lookup
short_call: filter_strikes_by_delta(chain, "CE", delta_range, call_target) → rank → [0]
long_call:  strike = short_call.strike + config.wing_width_points → BOD lookup
```
`delta_range = (config.delta_range, config.short_put_delta + config.delta_range)` — symmetric band.
If any leg fails to resolve → print error with failing leg name, exit 1.

**Step 9 — Liquidity gate**
`_apply_liquidity_gate(short_put_leg)` and `_apply_liquidity_gate(short_call_leg)`.
Long legs not gated. Either failure → exit 1.

**Step 10 — Portfolio delta check** (skip if `--force-entry`)
`PortfolioDeltaTracker.aggregate_delta(open_positions, nifty_spot, LOT_SIZE)`.
`ic_delta ≈ put_target - call_target` (approximate signed lots).
Projected total outside `[-0.05, 0.25]` → one-strike OTM adjustment attempt, then exit 1 if still breaching.

**Step 11 — Build and print/execute commands**
```python
cmd = [
    "python", "scripts/record/record_paper_trade.py",
    "--strategy", config.strategy_name,
    "--instrument-key", leg.instrument_key,
    "--action", leg.action,       # SELL / BUY
    "--leg-role", leg.leg_role,   # short_put / long_put_hedge / short_call / long_call_hedge
    "--quantity", str(LOT_SIZE),
    "--entry-price", str(leg.mid_price),
    "--ivr", str(round(ivr, 4)) if ivr is not None else "0",
]
```
Order: short_put → long_put_hedge → short_call → long_call_hedge.
Dry-run: print with `[DRY-RUN]` prefix. Live: `subprocess.run(cmd, check=True)`.

**Step 12 — Telegram entry notification**
After all four legs recorded (live mode only):
```
✅ IC Entry — {config.expiry_type} ({config.strategy_name})
Mode: standalone | concurrent-with-CSP
IVR: {ivr:.2f}  DTE: {dte}  Nifty: {spot:,.0f}

Short Put  {short_put_strike}PE  δ={put_delta:.3f}  mid=₹{put_mid:.2f}
Long Put   {long_put_strike}PE   (hedge)
Short Call {short_call_strike}CE δ={call_delta:.3f}  mid=₹{call_mid:.2f}
Long Call  {long_call_strike}CE  (hedge)

Net credit: ₹{net_credit:.2f}/lot  (₹{net_credit * LOT_SIZE:,.0f} for {LOT_SIZE} units)
```
Send via `TelegramGateway`. Non-fatal — if send fails, log WARNING and continue.

---

## Tests (all offline — 12 tests)

Mock: `UpstoxMarketClient`, `PaperStore`, `load_vix_series`, `fetch_vix_latest`,
`compute_ivr`, `InstrumentLookup`, `subprocess.run`, `TelegramGateway`.

**Happy-path:**
1. `weekly` standalone → weekly strategy_name in record cmd; 10Δ put, 8Δ call; 200pt wing
2. `monthly` standalone → monthly strategy_name; 15Δ put, 10Δ call; 500pt wing
3. `monthly` concurrent → shifted deltas (9Δ put, 13Δ call)
4. `--dry-run` → `subprocess.run` not called; `[DRY-RUN]` prefix in output
5. IVR ≥ gate → passes; IVR in record command
6. Telegram sent after live entry; failure non-fatal

**Error/edge:**
7. Open position for same strategy_name → exit 1 before chain fetch
8. IVR < gate, no `--force-entry` → exit 1 with gate message
9. IVR < gate, `--force-entry` → WARNING logged, continues
10. No expiry candidate for bucket → exit 1
11. BOD lookup fails for long put → exit 1 with leg name
12. Portfolio delta breaches, no `--force-entry` → exit 1

---

## Commit

```
feat(scripts/ic): paper_ic_entry.py — config-driven multi-expiry IC entry

Why: Research pipeline needs automated entry for all four IC expiry types;
all parameters sourced from ICExpiryConfig — no hardcoded values.
What:
- scripts/strategies/ic/__init__.py: new package
- scripts/strategies/ic/paper_ic_entry.py: entry script with --expiry-type
- tests/unit/strategies/ic/__init__.py: new test package
- tests/unit/strategies/ic/test_paper_ic_entry.py: 12 offline tests
Ref: ic-full IC-F6
```

---

## Pre-baked Context

**`CONFIGS`** — `src.strategy.ic_expiry_config`. Each entry has `strategy_name`,
`expiry_bucket`, `short_put_delta`, `short_call_delta`, `delta_range`,
`wing_width_points`, `ivr_gate`, `dte_warn_lo`, `dte_warn_hi`.

**`get_expiry_candidates`** returns `list[tuple[str, str]]`: `(label, expiry_date_str)`.
Pass `preference=[config.expiry_bucket]`.

**`filter_strikes_by_delta` / `rank_strikes` / `_apply_liquidity_gate`** — `src.instruments.strike_selector`.

**`PortfolioDeltaTracker`** — `src.risk.delta_tracker`. `aggregate_delta(positions, spot, lot_size) → PortfolioDelta`. `.total_delta_lots` is `Decimal`.

**`STRATEGY_CSP`** — `src.paper.constants` = `"paper_csp_nifty_v1"`.
**`LOT_SIZE`** — `src.paper.constants` = 65.
**`DEFAULT_BOD_PATH` / `DEFAULT_DB_PATH`** — `src.paper.constants`.

**`_SCRIPT_NAME` convention:**
```python
_SCRIPT_NAME = "scripts.strategies.ic.paper_ic_entry"
logger = structlog.get_logger(_SCRIPT_NAME)
```

**Reference script:** `scripts/strategies/cc_calibration/paper_cc_entry.py` — IVR load,
chain fetch, subprocess.run pattern, dotenv load, sys.path insert.
