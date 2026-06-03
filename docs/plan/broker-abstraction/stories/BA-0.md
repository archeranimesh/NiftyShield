# BA-0 — Broker Data Quality Analysis: evaluation + decision matrix

> Assigned to: Claude
> Phase: 0 — Pre-implementation Research (gates all other BA tasks)
> Priority: LOW — run before starting BA-1

---

## Goal

Before committing to any implementation, understand which broker is best suited for each
data access pattern. Brokers differ significantly in data quality, API latency, Greeks
availability, rate limits, and instrument master coverage. A wrong assumption here
propagates through 14 subsequent stories.

This story produces:
1. Scratch probe scripts (`scripts/dev/broker_probe/`) that fetch real data from each broker
2. A findings document (`docs/plan/broker-abstraction/broker_analysis.md`) with raw observations
3. A decision matrix (`docs/plan/broker-abstraction/broker_decision_matrix.md`) that assigns
   each data category to a preferred broker
4. An update to `DECISIONS.md` recording the authoritative assignments

No protocol code, no production changes. Only scripts and docs.

---

## Data categories to evaluate

| Category | What to measure | Why it matters |
|----------|----------------|----------------|
| Option chain (Greeks) | delta, gamma, theta, vega, IV present/absent; precision vs Black-Scholes recompute | Strategy signals depend on broker-supplied Greeks or require recompute overhead |
| Option chain (OI + Volume) | OI staleness, tick frequency, intraday updates | OI walls, PCR, supply/demand zone confirmation |
| LTP (real-time quotes) | Latency from exchange tick, rate limit ceiling, batch size per call | Intraday tracker runs every 5 min; batch LTP must cover all monitored legs |
| Historical candles (OHLC) | Max lookback, resolutions available, data gaps, cost per call | VIX history (252-day IVR window), strategy backtests |
| VIX data | Source, staleness, index key format, any gap in historical coverage | IVR computation; Phase 0.8 gate criterion C/D |
| Instrument master | File format, refresh frequency, expiry/strike coverage, key format | `get_expiry_candidates` depends on this |
| WebSocket / streaming | Available or polling only; protocols; reconnection behaviour | Future Phase 1 streaming — scope only, don't build yet |

---

## Brokers to probe

- **Upstox** (Analytics Token + Access Token — already wired)
- **Dhan** (`dhan_client_id` + `dhan_access_token` — already in `src/config.py`)
- **Kite/Zerodha** (requires `kite_api_key` + `kite_access_token` — add to `.env` before running)

---

## Probe scripts to write

All scripts live under `scripts/dev/broker_probe/`. They are one-shot diagnostic tools —
not cron jobs, not part of the pipeline. Use `asyncio` + `aiohttp` for consistency;
`--broker` flag to select which broker to probe.

### `scripts/dev/broker_probe/probe_option_chain.py`

Fetches the current NIFTY option chain (nearest monthly expiry) from each broker.
Writes raw JSON response to `data/broker_probe/<broker>_option_chain_<date>.json`.

Measures and prints:
- Total strikes returned
- Greeks present on CE leg: delta, gamma, theta, vega, IV (True/False each)
- Sample delta value for ATM CE (compare across brokers)
- Sample IV for ATM CE (compare across brokers)
- OI for ATM CE
- Wall-clock fetch latency (ms)
- Rate limit headers (if exposed)

```bash
python -m scripts.dev.broker_probe.probe_option_chain --broker upstox
python -m scripts.dev.broker_probe.probe_option_chain --broker dhan
python -m scripts.dev.broker_probe.probe_option_chain --broker kite
```

### `scripts/dev/broker_probe/probe_ltp.py`

Fetches LTP for a fixed basket of 10 instruments (5 NIFTY CE/PE + NIFTYBEES + India VIX +
3 equity ETFs from the portfolio).

Measures and prints:
- LTP for each instrument
- Wall-clock fetch latency (ms) per batch
- Maximum batch size supported (probe by doubling until error)
- Rate limit ceiling (calls/minute, if exposed in headers)

```bash
python -m scripts.dev.broker_probe.probe_ltp --broker upstox
python -m scripts.dev.broker_probe.probe_ltp --broker dhan
python -m scripts.dev.broker_probe.probe_ltp --broker kite
```

### `scripts/dev/broker_probe/probe_historical.py`

Fetches daily OHLC candles for India VIX and NIFTY spot for the trailing 1 year.

Measures and prints:
- Date range actually returned (may be shorter than requested)
- Total rows returned
- Any gaps (trading days with missing data)
- Wall-clock fetch latency (ms)
- Whether fractional/intraday resolutions are available (1min, 5min, 15min, 1D)

```bash
python -m scripts.dev.broker_probe.probe_historical --broker upstox
python -m scripts.dev.broker_probe.probe_historical --broker dhan
python -m scripts.dev.broker_probe.probe_historical --broker kite
```

### `scripts/dev/broker_probe/probe_instrument_master.py`

Downloads or reads the broker's instrument master file.

Measures and prints:
- File format (JSON, CSV, compressed)
- Total instrument count
- NFO (options) instrument count
- Column names present
- Sample row for a known NIFTY strike
- Whether canonical `NSE_FO|<token>` keys are present natively, or must be derived

```bash
python -m scripts.dev.broker_probe.probe_instrument_master --broker upstox
python -m scripts.dev.broker_probe.probe_instrument_master --broker dhan
python -m scripts.dev.broker_probe.probe_instrument_master --broker kite
```

---

## Output documents

### `docs/plan/broker-abstraction/broker_analysis.md`

Raw findings per broker per category. Structure:

```markdown
# Broker Data Quality Analysis — <date>

## Option Chain

### Upstox
- Greeks present: delta ✓, gamma ✓, theta ✓, vega ✓, IV ✓
- ATM delta (NIFTY, nearest expiry): 0.4923
- ATM IV: 12.3%
- Fetch latency: 280ms
- ...

### Dhan
...

### Kite
...

## LTP
...
```

### `docs/plan/broker-abstraction/broker_decision_matrix.md`

Decision matrix: one row per data category, one column per broker, recommended broker
highlighted with rationale.

```markdown
# Broker Decision Matrix

| Data Category | Upstox | Dhan | Kite | Recommended | Rationale |
|---------------|--------|------|------|-------------|-----------|
| Option chain (Greeks) | ✓ Full | ✓ Full | ✗ None | Upstox or Dhan | Kite does not supply Greeks — requires BS recompute |
| LTP (batch) | 500/call | 100/call | 500/call | Upstox or Kite | Dhan batch ceiling too low for full portfolio |
| Historical OHLC | 2Y daily | 1Y daily | 3Y daily | Kite | Widest lookback; Upstox gaps noted on VIX pre-2022 |
| VIX | NSE_INDEX\|India VIX | N/A | N/A | Upstox (or NSE CSV) | Only Upstox exposes India VIX via API |
| Instrument master | JSON.gz BOD | CSV (daily) | CSV (daily) | All equivalent | Format differs; all cover NFO |
| WebSocket | ✓ | ✓ | ✓ | TBD (Phase 1) | Evaluate during streaming story |
```

---

## Mandatory gate before closing BA-0

Before marking BA-0 complete and starting BA-1, the following must be true:
1. All four probe scripts run without error against at least Upstox and Dhan.
2. `broker_analysis.md` is committed with raw observations.
3. `broker_decision_matrix.md` is committed with recommended assignments.
4. `DECISIONS.md` has a new entry: `Broker data source assignments (YYYY-MM-DD, BA-0)` with the matrix summary.

Kite probes are optional at BA-0 time — Kite credentials may not be available. Document
as "Not probed — credentials pending" in the analysis.

---

## Files to create

| File | Type |
|------|------|
| `scripts/dev/broker_probe/__init__.py` | Package stub |
| `scripts/dev/broker_probe/probe_option_chain.py` | Scratch probe |
| `scripts/dev/broker_probe/probe_ltp.py` | Scratch probe |
| `scripts/dev/broker_probe/probe_historical.py` | Scratch probe |
| `scripts/dev/broker_probe/probe_instrument_master.py` | Scratch probe |
| `data/broker_probe/.gitkeep` | Directory placeholder |
| `docs/plan/broker-abstraction/broker_analysis.md` | Findings doc (populate after running) |
| `docs/plan/broker-abstraction/broker_decision_matrix.md` | Decision matrix (populate after analysis) |

---

## Commit strategy

Two commits:

**Commit 1 — probe scripts only (no findings yet):**
```
feat(dev): broker data quality probe scripts

Why: pre-implementation research to assign each data category to the best broker
     before committing to 14 implementation stories.
What:
- scripts/dev/broker_probe/: 4 probe scripts + package stub
- data/broker_probe/.gitkeep: output directory placeholder
Ref: docs/plan/broker-abstraction/stories/BA-0.md
```

**Commit 2 — findings + decision matrix (after running probes):**
```
docs(broker-abstraction): broker analysis findings + decision matrix

Why: documents BA-0 evaluation results; decision matrix gates BA-1 implementation.
What:
- docs/plan/broker-abstraction/broker_analysis.md: raw probe findings
- docs/plan/broker-abstraction/broker_decision_matrix.md: recommended broker per category
- DECISIONS.md: broker data source assignments entry
Ref: docs/plan/broker-abstraction/stories/BA-0.md
```

---

## Pre-baked graph context

```
search_graph("UpstoxMarketClient")     # existing Upstox fetch methods to reference
search_graph("dhan_access_token")      # confirm Dhan credentials in settings
search_graph("settings")               # Settings fields — what's already wired
git log --oneline -5 src/dhan/reader.py   # Dhan fetch patterns already used in codebase
```

Also read `REFERENCES.md` before writing probe scripts — instrument keys for NIFTY index,
India VIX, and NIFTYBEES are documented there.
