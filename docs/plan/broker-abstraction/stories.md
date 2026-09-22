# Broker Abstraction — story specs


> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## BA-0 — Broker Data Quality Analysis: evaluation + decision matrix

> Assigned to: Claude Phase: 0 — Pre-implementation Research (gates all other BA tasks) Priority: LOW — run before starting BA-1

---

### Goal

Before committing to any implementation, understand which broker is best suited for each data access pattern. Brokers differ significantly in data quality, API latency, Greeks availability, rate
limits, and instrument master coverage. A wrong assumption here propagates through 14 subsequent stories.

This story produces:
1. Scratch probe scripts (`scripts/dev/broker_probe/`) that fetch real data from each broker
2. A findings document (`docs/plan/broker-abstraction/broker_analysis.md`) with raw observations
3. A decision matrix (`docs/plan/broker-abstraction/broker_decision_matrix.md`) that assigns each data category to a preferred broker
4. An update to `DECISIONS.md` recording the authoritative assignments

No protocol code, no production changes. Only scripts and docs.

---

### Data categories to evaluate

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

### Brokers to probe

- **Upstox** (Analytics Token + Access Token — already wired)
- **Dhan** (`dhan_client_id` + `dhan_access_token` — already in `src/config.py`)
- **Kite/Zerodha** (requires `kite_api_key` + `kite_access_token` — add to `.env` before running)

---

### Probe scripts to write

All scripts live under `scripts/dev/broker_probe/`. They are one-shot diagnostic tools — not cron jobs, not part of the pipeline. Use `asyncio` + `aiohttp` for consistency; `--broker` flag to select
which broker to probe.

#### `scripts/dev/broker_probe/probe_option_chain.py`

Fetches the current NIFTY option chain (nearest monthly expiry) from each broker. Writes raw JSON response to `data/broker_probe/<broker>_option_chain_<date>.json`.

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

#### `scripts/dev/broker_probe/probe_ltp.py`

Fetches LTP for a fixed basket of 10 instruments (5 NIFTY CE/PE + NIFTYBEES + India VIX + 3 equity ETFs from the portfolio).

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

#### `scripts/dev/broker_probe/probe_historical.py`

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

#### `scripts/dev/broker_probe/probe_instrument_master.py`

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

### Output documents

#### `docs/plan/broker-abstraction/broker_analysis.md`

Raw findings per broker per category. Structure:

```markdown
# Broker Data Quality Analysis — <date>

### Option Chain

#### Upstox
- Greeks present: delta ✓, gamma ✓, theta ✓, vega ✓, IV ✓
- ATM delta (NIFTY, nearest expiry): 0.4923
- ATM IV: 12.3%
- Fetch latency: 280ms
- ...

#### Dhan
...

#### Kite
...

### LTP
...
```

#### `docs/plan/broker-abstraction/broker_decision_matrix.md`

Decision matrix: one row per data category, one column per broker, recommended broker highlighted with rationale.

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

### Mandatory gate before closing BA-0

Before marking BA-0 complete and starting BA-1, the following must be true:
1. All four probe scripts run without error against at least Upstox and Dhan.
2. `broker_analysis.md` is committed with raw observations.
3. `broker_decision_matrix.md` is committed with recommended assignments.
4. `DECISIONS.md` has a new entry: `Broker data source assignments (YYYY-MM-DD, BA-0)` with the matrix summary.

Kite probes are optional at BA-0 time — Kite credentials may not be available. Document as "Not probed — credentials pending" in the analysis.

---

### Files to create

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

### Commit strategy

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

### Pre-baked graph context

```
search_graph("UpstoxMarketClient")     # existing Upstox fetch methods to reference
search_graph("dhan_access_token")      # confirm Dhan credentials in settings
search_graph("settings")               # Settings fields — what's already wired
git log --oneline -5 src/dhan/reader.py   # Dhan fetch patterns already used in codebase
```

Also read `REFERENCES.md` before writing probe scripts — instrument keys for NIFTY index, India VIX, and NIFTYBEES are documented there.


---

## BA-1 — Define `MarketDataParser` protocol + move Upstox parser to conform

> Assigned to: Claude Phase: 1 — Parser Protocol + Upstox Conformance Priority: LOW

---

### Goal

Introduce a typed `MarketDataParser` protocol as the standard interface for converting broker-native option chain responses into the canonical `OptionChain` model. Move the existing Upstox parser to
conform to this protocol without changing any downstream consumer.

**Storage is frozen.** `src/models/options.py` is read-only for this task. No Parquet schema, SQLite schema, or model field names change.

---

### Files to change

| File | Action |
|------|--------|
| `src/client/parsers/__init__.py` | New package (single comment line) |
| `src/client/parsers/protocol.py` | New — `MarketDataParser` protocol |
| `src/client/parsers/upstox.py` | New — move `parse_upstox_option_chain` here, conforming to protocol |
| `src/client/upstox_market.py` | Keep existing function; add deprecation shim that delegates to new module |
| `tests/unit/client/test_parsers_protocol.py` | New — protocol conformance tests |

---

### What to implement

#### `src/client/parsers/protocol.py`

```python
from typing import Protocol, runtime_checkable
from src.models.options import OptionChain

@runtime_checkable
class MarketDataParser(Protocol):
    """Converts broker-native option chain payload to canonical OptionChain.

    Implementors must not expose broker-specific field names past this boundary.
    The returned OptionChain is the sole representation used by storage, paper
    trading, and backtests — its schema is frozen.
    """

    def parse_option_chain(self, raw: dict) -> OptionChain:
        """Parse a broker-native option chain response.

        Args:
            raw: The raw response dict as returned by the broker API.

        Returns:
            Canonical OptionChain. All monetary/price fields use Decimal.

        Raises:
            ValueError: If the payload is missing required fields or is malformed.
        """
        ...
```

`@runtime_checkable` is required so `isinstance(parser, MarketDataParser)` works in `factory.py` guard clauses.

#### `src/client/parsers/upstox.py`

Move the body of `parse_upstox_option_chain` from `src/client/upstox_market.py` into a class `UpstoxMarketDataParser` that implements `MarketDataParser`:

```python
class UpstoxMarketDataParser:
    """MarketDataParser implementation for Upstox option chain API responses."""

    def parse_option_chain(self, raw: dict) -> OptionChain:
        # existing logic verbatim — do not alter field names or Decimal handling
        ...
```

The class must satisfy `isinstance(UpstoxMarketDataParser(), MarketDataParser)`.

#### `src/client/upstox_market.py` — deprecation shim

Keep `parse_upstox_option_chain` as a module-level function for backward compatibility. Delegate to `UpstoxMarketDataParser`:

```python
import warnings
from src.client.parsers.upstox import UpstoxMarketDataParser

_parser = UpstoxMarketDataParser()

def parse_upstox_option_chain(raw: dict) -> OptionChain:
    """Deprecated: use UpstoxMarketDataParser directly."""
    warnings.warn(
        "parse_upstox_option_chain is deprecated; use UpstoxMarketDataParser",
        DeprecationWarning,
        stacklevel=2,
    )
    return _parser.parse_option_chain(raw)
```

Existing callers (`scripts/pipeline/upstox_chain_snapshot.py` etc.) continue to work unchanged — the shim is the migration path.

---

### Tests — `tests/unit/client/test_parsers_protocol.py`

1. **Happy path:** `isinstance(UpstoxMarketDataParser(), MarketDataParser)` → `True`.
2. **Protocol structural check:** a class with `parse_option_chain(self, raw: dict) -> OptionChain` satisfies the protocol even without explicit inheritance.
3. **Non-conforming class:** a class without `parse_option_chain` does **not** satisfy `isinstance(..., MarketDataParser)`.
4. **Shim delegation:** calling `parse_upstox_option_chain(raw)` with a valid fixture returns the same result as `UpstoxMarketDataParser().parse_option_chain(raw)`.
5. **Shim deprecation warning:** calling `parse_upstox_option_chain` emits `DeprecationWarning`.

Use the fixture from `tests/fixtures/responses/` for the Upstox chain payload. No network calls.

---

### Commit message

```
feat(client): introduce MarketDataParser protocol + conform Upstox parser

Why: establishes the seam for multi-broker option chain parsing without touching
     canonical models or downstream storage consumers.
What:
- src/client/parsers/__init__.py: new package stub
- src/client/parsers/protocol.py: MarketDataParser runtime-checkable Protocol
- src/client/parsers/upstox.py: UpstoxMarketDataParser conforming to protocol
- src/client/upstox_market.py: deprecation shim delegating to new class
- tests/unit/client/test_parsers_protocol.py: 5 conformance + shim tests
Ref: docs/plan/broker-abstraction/stories/BA-1.md
```

---

### Pre-baked graph context

Run these before opening any source file:

```
search_graph("parse_upstox_option_chain")   # callers + current location
search_graph("OptionChain")                 # canonical model fields
search_graph("BrokerClient")               # existing protocol pattern to mirror
```

Expected: `parse_upstox_option_chain` lives in `src/client/upstox_market.py`; `OptionChain` is in `src/models/options.py` (frozen Pydantic); `BrokerClient` is in `src/client/protocol.py` as a
`@runtime_checkable Protocol` — mirror that pattern exactly.


---

## BA-2 — Define `InstrumentKeyAdapter` protocol + Upstox adapter

> Assigned to: Claude Phase: 1 — Parser Protocol + Upstox Conformance Priority: LOW Blocked by: BA-1 must be merged first

---

### Goal

Introduce a typed `InstrumentKeyAdapter` protocol to normalize the impedance mismatch between the canonical instrument key format (Upstox-style `NSE_FO|<token>`) and broker-native symbol formats (Dhan
numeric IDs, Kite `NFO:NIFTY24JUN23000CE` strings, etc.).

Adapters translate **at fetch time only**. Stored keys (`instrument_key` in DB and Parquet) are never mutated — they remain Upstox-format strings, as established in `REFERENCES.md`. This is a one-way
translation: broker-native → canonical on ingest; canonical → broker-native when placing orders.

---

### Files to change

| File | Action |
|------|--------|
| `src/client/adapters/__init__.py` | New package (single comment line) |
| `src/client/adapters/protocol.py` | New — `InstrumentKeyAdapter` protocol |
| `src/client/adapters/upstox.py` | New — Upstox adapter (identity: keys are already canonical) |
| `tests/unit/client/test_adapters_protocol.py` | New — protocol conformance + Upstox adapter tests |

---

### What to implement

#### `src/client/adapters/protocol.py`

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class InstrumentKeyAdapter(Protocol):
    """Translates between canonical instrument keys and broker-native symbols.

    Canonical key format: Upstox-style "EXCHANGE_SEGMENT|TOKEN" e.g. "NSE_FO|79653".
    This format is stored in DB and Parquet — it must never be altered at rest.

    Adapters perform translation only at the API boundary:
    - to_broker(canonical_key) called before placing an order via broker API.
    - to_canonical(broker_symbol) called when ingesting broker-native data.
    """

    def to_broker(self, canonical_key: str) -> str:
        """Convert canonical instrument key to broker-native symbol.

        Args:
            canonical_key: Upstox-style key, e.g. "NSE_FO|79653".

        Returns:
            Broker-native symbol string.

        Raises:
            KeyError: If the canonical key is not found in the broker's lookup.
        """
        ...

    def to_canonical(self, broker_symbol: str) -> str:
        """Convert broker-native symbol to canonical instrument key.

        Args:
            broker_symbol: Broker-native symbol, e.g. Dhan numeric security ID.

        Returns:
            Canonical key string in "EXCHANGE_SEGMENT|TOKEN" format.

        Raises:
            KeyError: If the broker symbol has no known canonical mapping.
        """
        ...
```

#### `src/client/adapters/upstox.py`

Upstox keys are already canonical — the adapter is an identity transform:

```python
class UpstoxInstrumentKeyAdapter:
    """InstrumentKeyAdapter for Upstox — keys are already in canonical format."""

    def to_broker(self, canonical_key: str) -> str:
        return canonical_key

    def to_canonical(self, broker_symbol: str) -> str:
        return broker_symbol
```

Simple, but important: it makes the Upstox adapter interchangeable with Dhan/Kite adapters in `factory.py` without special-casing.

---

### Tests — `tests/unit/client/test_adapters_protocol.py`

1. **Protocol conformance:** `isinstance(UpstoxInstrumentKeyAdapter(), InstrumentKeyAdapter)` → `True`.
2. **Identity round-trip:** `adapter.to_broker(key) == key` and `adapter.to_canonical(key) == key` for a sample Upstox key.
3. **Non-conforming class:** a class with only `to_broker` (missing `to_canonical`) does not satisfy the protocol.
4. **Structural conformance:** a third-party class with both methods but no explicit inheritance satisfies `isinstance(..., InstrumentKeyAdapter)`.

---

### Commit message

```
feat(client): introduce InstrumentKeyAdapter protocol + Upstox identity adapter

Why: establishes the translation seam for broker-native ↔ canonical instrument keys
     without mutating stored keys in DB or Parquet.
What:
- src/client/adapters/__init__.py: new package stub
- src/client/adapters/protocol.py: InstrumentKeyAdapter runtime-checkable Protocol
- src/client/adapters/upstox.py: UpstoxInstrumentKeyAdapter (identity transform)
- tests/unit/client/test_adapters_protocol.py: 4 conformance tests
Ref: docs/plan/broker-abstraction/stories/BA-2.md
```

---

### Pre-baked graph context

```
search_graph("BrokerClient")        # mirror the @runtime_checkable Protocol pattern
search_graph("instrument_key")      # confirm field name in OptionLeg / trades table
search_graph("MarketDataParser")    # confirm BA-1 shipped before starting this task
```

Expected: `instrument_key` appears on `OptionLeg` (str field) and in `trades` SQLite table. `MarketDataParser` must exist before starting — abort if graph returns zero results.


---

## BA-3 — Dhan `MarketDataParser` implementation

> Assigned to: Antigravity Phase: 2 — Dhan Integration Priority: LOW Blocked by: BA-1, BA-2 must be merged first

---

### Goal

Implement `DhanMarketDataParser` — a `MarketDataParser` that converts Dhan's option chain API response into the canonical `OptionChain` model. No downstream consumer changes. No DB or Parquet schema
changes.

---

### Context: Dhan option chain API

Dhan's option chain endpoint returns a structure broadly similar to Upstox but with different field names and numeric security IDs instead of `EXCHANGE_SEGMENT|TOKEN` keys.

Key differences from Upstox response:
- Strike price is `strikePrice` (float) vs Upstox `strike_price`
- Call/put legs are nested under `callOption` / `putOption` dicts
- Greeks are under `greeks` sub-dict: `delta`, `gamma`, `theta`, `vega`, `iv`
- Instrument ID is `securityId` (string of numeric ID, e.g. `"49081"`)
- LTP is `lastTradedPrice`
- OI is `openInterest`
- Volume is `volume`

The `DhanInstrumentKeyAdapter` (BA-4) handles `securityId` → canonical key translation. The parser receives raw Dhan API dicts and must produce `OptionChain` with canonical keys already resolved via
the adapter.

**If Dhan API response format is unavailable at implementation time:** build the parser against a locally defined fixture dict (see test section). Do not make live API calls.

---

### Files to change

| File | Action |
|------|--------|
| `src/client/parsers/dhan.py` | New — `DhanMarketDataParser` |
| `tests/unit/client/test_parsers_dhan.py` | New — parser tests with fixture |
| `tests/fixtures/responses/dhan_option_chain.json` | New — representative Dhan fixture |

---

### What to implement

#### `src/client/parsers/dhan.py`

```python
class DhanMarketDataParser:
    """MarketDataParser for Dhan option chain API responses.

    Requires a DhanInstrumentKeyAdapter to resolve securityId → canonical key.
    Constructor injection only — never import a concrete adapter directly.
    """

    def __init__(self, adapter: InstrumentKeyAdapter) -> None:
        self._adapter = adapter

    def parse_option_chain(self, raw: dict) -> OptionChain:
        ...
```

Parsing rules:
- `underlying` from `raw["underlyingSymbol"]` or `raw["underlying"]` (probe actual API)
- `expiry` from `raw["expiryDate"]` — ISO date string `YYYY-MM-DD`
- `spot_price` from `raw["underlyingSpotPrice"]` — `Decimal(str(value))`
- For each strike in `raw["data"]`:
  - `strike` = `Decimal(str(item["strikePrice"]))`
  - CE/PE legs: extract LTP, OI, volume, IV, delta, gamma, theta, vega from respective sub-dicts
  - `instrument_key` = `self._adapter.to_canonical(item["callOption"]["securityId"])` (CE) / PE equivalent
  - All price/monetary fields → `Decimal(str(value))` — never float
  - Missing/null Greek values → `None`

Raise `ValueError` with a descriptive message if required top-level keys are absent.

---

### Fixture — `tests/fixtures/responses/dhan_option_chain.json`

Construct a minimal 2-strike fixture (one ITM, one OTM) that covers:
- Both CE and PE legs present
- At least one Greek populated, at least one Greek null (realistic — Dhan nulls deep OTM Greeks)
- `securityId` values that match entries in the Dhan adapter fixture (BA-4)

---

### Tests — `tests/unit/client/test_parsers_dhan.py`

1. **Happy path:** parse 2-strike fixture → `OptionChain` with correct `underlying`, `expiry`, `spot_price`, both strikes, all legs.
2. **Decimal invariant:** every price field on every leg is `Decimal`, not `float`.
3. **Null Greeks:** leg with null IV/delta → corresponding fields are `None`, not zero.
4. **Missing required key:** `raw` dict missing `"data"` key → raises `ValueError`.
5. **`isinstance` check:** `isinstance(DhanMarketDataParser(mock_adapter), MarketDataParser)` → `True`.

Use `unittest.mock.MagicMock` for the adapter — no concrete adapter dependency in parser tests.

---

### Commit message

```
feat(client): Dhan MarketDataParser + fixture

Why: enables option chain ingestion from Dhan without altering canonical models or storage.
What:
- src/client/parsers/dhan.py: DhanMarketDataParser conforming to MarketDataParser protocol
- tests/unit/client/test_parsers_dhan.py: 5 parser tests
- tests/fixtures/responses/dhan_option_chain.json: 2-strike Dhan fixture
Ref: docs/plan/broker-abstraction/stories/BA-3.md
```

---

### Pre-baked graph context

```
search_graph("OptionChain")              # canonical model fields — read before writing parser
search_graph("OptionChainStrike")        # strike-level fields
search_graph("OptionLeg")               # leg-level fields including Greeks
search_graph("MarketDataParser")         # protocol — confirm BA-1 shipped
search_graph("InstrumentKeyAdapter")     # protocol — confirm BA-2 shipped
search_graph("UpstoxMarketDataParser")   # reference implementation to mirror
```


---

## BA-4 — Dhan `InstrumentKeyAdapter` implementation

> Assigned to: Antigravity Phase: 2 — Dhan Integration Priority: LOW Blocked by: BA-2 must be merged first. Can run in parallel with BA-3.

---

### Goal

Implement `DhanInstrumentKeyAdapter` — an `InstrumentKeyAdapter` that translates between Dhan's numeric `securityId` strings and the canonical `NSE_FO|<token>` key format.

Translation is lookup-table driven, backed by a CSV mapping file that pairs Dhan security IDs with Upstox instrument tokens. The mapping file is generated offline (see note below) and committed to
`data/instruments/dhan_key_map.csv`. It is never modified at runtime.

**Stored keys are never mutated.** The adapter translates at the API boundary only.

---

### Mapping file

`data/instruments/dhan_key_map.csv` — columns:

```
dhan_security_id,canonical_key,symbol,expiry,strike,option_type
49081,NSE_FO|79653,NIFTY,2026-06-26,23000,CE
...
```

The file does not exist yet — create a minimal 4-row sample (2 strikes × CE/PE) for testing. Production population is a separate operational task (not part of this story).

---

### Files to change

| File | Action |
|------|--------|
| `src/client/adapters/dhan.py` | New — `DhanInstrumentKeyAdapter` |
| `data/instruments/dhan_key_map.csv` | New — sample mapping (4 rows + header) |
| `tests/unit/client/test_adapters_dhan.py` | New — adapter tests |
| `tests/fixtures/instruments/dhan_key_map_fixture.csv` | New — test fixture (4 rows) |

---

### What to implement

#### `src/client/adapters/dhan.py`

```python
class DhanInstrumentKeyAdapter:
    """InstrumentKeyAdapter for Dhan numeric securityId ↔ canonical key translation.

    Loads the mapping from a CSV file at construction time. Raises FileNotFoundError
    if the CSV does not exist. Both directions are O(1) lookup via pre-built dicts.
    """

    def __init__(self, map_path: Path) -> None:
        self._dhan_to_canonical: dict[str, str] = {}
        self._canonical_to_dhan: dict[str, str] = {}
        self._load(map_path)

    def _load(self, map_path: Path) -> None:
        # Read CSV, populate both dicts
        ...

    def to_broker(self, canonical_key: str) -> str:
        # canonical → dhan security ID
        ...

    def to_canonical(self, broker_symbol: str) -> str:
        # dhan security ID → canonical key
        ...
```

Both `to_broker` and `to_canonical` raise `KeyError` with a descriptive message when the key is not found in the map. Do not silently return the input.

---

### Tests — `tests/unit/client/test_adapters_dhan.py`

Use `tests/fixtures/instruments/dhan_key_map_fixture.csv` (4-row fixture) for all tests — never reference `data/instruments/dhan_key_map.csv` in unit tests.

1. **Happy path `to_canonical`:** known Dhan security ID → correct canonical key.
2. **Happy path `to_broker`:** known canonical key → correct Dhan security ID.
3. **Round-trip:** `to_canonical(to_broker(canonical_key)) == canonical_key` for all fixture rows.
4. **Unknown `to_canonical`:** unknown Dhan ID → raises `KeyError`.
5. **Unknown `to_broker`:** unknown canonical key → raises `KeyError`.
6. **Missing CSV:** `DhanInstrumentKeyAdapter(Path("/nonexistent.csv"))` → raises `FileNotFoundError`.
7. **`isinstance` check:** `isinstance(DhanInstrumentKeyAdapter(fixture_path), InstrumentKeyAdapter)` → `True`.

---

### Commit message

```
feat(client): Dhan InstrumentKeyAdapter + sample key map

Why: provides the canonical ↔ Dhan securityId translation layer without mutating stored keys.
What:
- src/client/adapters/dhan.py: DhanInstrumentKeyAdapter with O(1) bidirectional lookup
- data/instruments/dhan_key_map.csv: 4-row sample mapping (production population is separate)
- tests/unit/client/test_adapters_dhan.py: 7 adapter tests
- tests/fixtures/instruments/dhan_key_map_fixture.csv: test fixture
Ref: docs/plan/broker-abstraction/stories/BA-4.md
```

---

### Pre-baked graph context

```
search_graph("InstrumentKeyAdapter")      # protocol — confirm BA-2 shipped
search_graph("UpstoxInstrumentKeyAdapter") # reference implementation
search_graph("instrument_key")             # confirm field name convention in models
```

Also check `REFERENCES.md` for Upstox instrument key format examples before writing the CSV.


---

## BA-5 — Wire Dhan parsers into `factory.py` + integration smoke test

> Assigned to: Claude Phase: 2 — Dhan Integration Priority: LOW Blocked by: BA-3 and BA-4 must be merged first

---

### Goal

Extend `factory.py` (the sole composition root) to build and return a `DhanMarketDataParser` and `DhanInstrumentKeyAdapter` when `UPSTOX_ENV=dhan`. Add a smoke test that exercises the full parse path
end-to-end using fixture data — no network calls.

---

### Context: current factory pattern

`factory.py` currently selects `BrokerClient` implementation based on `settings.upstox_env`. The same env var gates the parser/adapter selection — a single env var controls the entire broker stack,
which is the right constraint for this project (one active broker at a time).

---

### Files to change

| File | Action |
|------|--------|
| `src/client/factory.py` | Add `build_market_data_parser()` factory function |
| `src/config.py` | Add `"dhan"` as a valid `upstox_env` literal (alongside `"prod"`, `"sandbox"`, `"test"`) |
| `tests/unit/client/test_factory_parsers.py` | New — factory selection tests + smoke test |

---

### What to implement

#### `src/client/factory.py` — new function

```python
def build_market_data_parser(
    settings: Settings | None = None,
    adapter: InstrumentKeyAdapter | None = None,
) -> MarketDataParser:
    """Return the MarketDataParser for the active broker environment.

    Args:
        settings: Settings singleton. Uses module-level singleton if None.
        adapter: InstrumentKeyAdapter override (primarily for testing).
                 If None, builds the default adapter for the active env.

    Returns:
        MarketDataParser conforming to the protocol.

    Raises:
        ValueError: If upstox_env is set to an unrecognised broker string.
    """
    ...
```

Selection logic:
- `upstox_env in ("prod", "sandbox", "test")` → `UpstoxMarketDataParser()`
- `upstox_env == "dhan"` → `DhanMarketDataParser(adapter or _build_dhan_adapter())`
- anything else → `ValueError(f"Unknown broker env: {upstox_env}")`

`_build_dhan_adapter()` is a private helper that constructs `DhanInstrumentKeyAdapter` with the production map path (`data/instruments/dhan_key_map.csv`).

#### `src/config.py`

Extend the `upstox_env` literal type to include `"dhan"`:

```python
upstox_env: Literal["prod", "sandbox", "test", "dhan"] = "test"
```

---

### Tests — `tests/unit/client/test_factory_parsers.py`

1. **Upstox selection:** `upstox_env="prod"` → `build_market_data_parser()` returns `UpstoxMarketDataParser` instance.
2. **Upstox test env:** `upstox_env="test"` → also returns `UpstoxMarketDataParser`.
3. **Dhan selection:** `upstox_env="dhan"` with injected mock adapter → returns `DhanMarketDataParser`.
4. **Unknown env:** `upstox_env="unknown_broker"` → raises `ValueError`.
5. **Smoke test — Dhan parse:** with `upstox_env="dhan"`, injected `DhanInstrumentKeyAdapter` using fixture CSV, and Dhan chain fixture → `build_market_data_parser().parse_option_chain(fixture)`
   returns valid `OptionChain` with correct strike count.
6. **Protocol conformance:** returned parser from both `"prod"` and `"dhan"` paths satisfies `isinstance(..., MarketDataParser)`.

All tests use injected settings — no live API calls, no filesystem access except fixture CSV.

---

### Commit message

```
feat(client): wire Dhan parsers into factory + smoke test

Why: makes factory.py the sole composition root for broker selection,
     keeping all concrete broker imports out of feature code.
What:
- src/client/factory.py: build_market_data_parser() with env-based selection
- src/config.py: extend upstox_env Literal to include "dhan"
- tests/unit/client/test_factory_parsers.py: 6 factory + smoke tests
Ref: docs/plan/broker-abstraction/stories/BA-5.md
```

---

### Pre-baked graph context

```
search_graph("factory")                   # current factory.py — build_broker_client pattern
search_graph("build_broker_client")        # existing factory function signature to mirror
search_graph("Settings")                  # upstox_env field — current Literal values
search_graph("MarketDataParser")           # confirm BA-1 shipped
search_graph("DhanMarketDataParser")       # confirm BA-3 shipped
search_graph("DhanInstrumentKeyAdapter")   # confirm BA-4 shipped
```


---

## BA-6 — Kite `MarketDataParser` implementation

> Assigned to: Antigravity Phase: 3 — Kite/Zerodha Integration Priority: LOW Blocked by: BA-1, BA-2 must be merged first. Can run in parallel with BA-7.

---

### Goal

Implement `KiteMarketDataParser` — a `MarketDataParser` that converts Zerodha Kite's option chain API response into the canonical `OptionChain` model.

---

### Context: Kite option chain API

Kite Connect's option chain data is fetched via the instruments endpoint + quote endpoint rather than a single option chain call. For parsing purposes, treat the input `raw` dict as a pre-assembled
dict keyed by Kite `tradingsymbol` (e.g. `"NFO:NIFTY24JUN23000CE"`).

Key differences from Upstox:
- Symbol format: `"NFO:NIFTY{DDMMMYY}{STRIKE}{CE/PE}"` e.g. `"NFO:NIFTY26JUN23000CE"`
- Strike and expiry are encoded in the symbol string — must be parsed out
- LTP is `last_price`
- OI is `oi`
- Volume is `volume`
- Greeks are NOT returned by Kite's quote endpoint — they must be computed externally (Black-Scholes, already available in `src/backtest/` or inject as None)
- `instrument_token` is Kite's numeric identifier (int)

Since Kite does not return Greeks, all Greek fields on `OptionLeg` (`delta`, `gamma`, `theta`, `vega`, `iv`) must be `None` when parsed from Kite data. This is valid — `OptionLeg` already defines
these as `Optional`.

---

### Files to change

| File | Action |
|------|--------|
| `src/client/parsers/kite.py` | New — `KiteMarketDataParser` |
| `tests/unit/client/test_parsers_kite.py` | New — parser tests with fixture |
| `tests/fixtures/responses/kite_option_chain.json` | New — representative Kite fixture |

---

### What to implement

#### `src/client/parsers/kite.py`

```python
class KiteMarketDataParser:
    """MarketDataParser for Kite Connect option chain data.

    Input: pre-assembled dict keyed by Kite tradingsymbol.
    Greeks are not available from Kite quotes — all Greek fields will be None.
    """

    def __init__(self, adapter: InstrumentKeyAdapter) -> None:
        self._adapter = adapter

    def parse_option_chain(self, raw: dict) -> OptionChain:
        ...
```

Symbol parsing helper (private):
```python
def _parse_kite_symbol(symbol: str) -> tuple[str, date, Decimal, str]:
    """Parse 'NFO:NIFTY26JUN23000CE' → (underlying, expiry, strike, option_type)."""
    ...
```

Parsing rules:
- `underlying` from `raw["underlying"]` (top-level key, caller must set it)
- `expiry` from `raw["expiry"]` (ISO date string `YYYY-MM-DD`, caller must set it)
- `spot_price` from `raw["spot_price"]` (Decimal)
- For each symbol in `raw["strikes"]` dict:
  - Parse underlying/expiry/strike/option_type from symbol string
  - `instrument_key` = `self._adapter.to_canonical(str(item["instrument_token"]))`
  - `ltp` = `Decimal(str(item["last_price"]))`
  - `oi` = `item["oi"]` (int)
  - `volume` = `item["volume"]` (int)
  - All Greeks → `None`
- Raise `ValueError` if `raw["strikes"]` is absent

---

### Tests — `tests/unit/client/test_parsers_kite.py`

1. **Happy path:** parse 2-strike fixture → `OptionChain` with correct strikes, legs, `None` Greeks.
2. **Decimal invariant:** LTP and spot_price are `Decimal`, not `float`.
3. **Greeks are None:** delta/gamma/theta/vega/iv on every leg are `None`.
4. **Symbol parser:** `_parse_kite_symbol("NFO:NIFTY26JUN23000CE")` → `("NIFTY", date(2026,6,26), Decimal("23000"), "CE")`.
5. **Missing strikes key:** `raw` dict without `"strikes"` → raises `ValueError`.
6. **`isinstance` check:** `isinstance(KiteMarketDataParser(mock_adapter), MarketDataParser)` → `True`.

---

### Commit message

```
feat(client): Kite MarketDataParser + fixture

Why: enables option chain ingestion from Kite without altering canonical models; Greek fields
     are None (Kite does not return them in quote responses).
What:
- src/client/parsers/kite.py: KiteMarketDataParser conforming to MarketDataParser protocol
- tests/unit/client/test_parsers_kite.py: 6 parser tests
- tests/fixtures/responses/kite_option_chain.json: 2-strike Kite fixture
Ref: docs/plan/broker-abstraction/stories/BA-6.md
```

---

### Pre-baked graph context

```
search_graph("OptionLeg")               # confirm Greek fields are Optional
search_graph("MarketDataParser")         # confirm BA-1 shipped
search_graph("DhanMarketDataParser")     # reference implementation to mirror
search_graph("InstrumentKeyAdapter")     # confirm BA-2 shipped
```


---

## BA-7 — Kite `InstrumentKeyAdapter` implementation

> Assigned to: Antigravity Phase: 3 — Kite/Zerodha Integration Priority: LOW Blocked by: BA-2 must be merged first. Can run in parallel with BA-6.

---

### Goal

Implement `KiteInstrumentKeyAdapter` — translates between Kite's numeric `instrument_token` (int, stored as string) and the canonical `NSE_FO|<token>` key format.

Same pattern as `DhanInstrumentKeyAdapter` (BA-4): CSV-backed, bidirectional, O(1) lookup.

---

### Mapping file

`data/instruments/kite_key_map.csv` — columns:

```
kite_instrument_token,canonical_key,symbol,expiry,strike,option_type
12345678,NSE_FO|79653,NIFTY,2026-06-26,23000,CE
...
```

Create a minimal 4-row sample (2 strikes × CE/PE) for testing. Production population is a separate operational task (not part of this story).

---

### Files to change

| File | Action |
|------|--------|
| `src/client/adapters/kite.py` | New — `KiteInstrumentKeyAdapter` |
| `data/instruments/kite_key_map.csv` | New — sample mapping (4 rows + header) |
| `tests/unit/client/test_adapters_kite.py` | New — adapter tests |
| `tests/fixtures/instruments/kite_key_map_fixture.csv` | New — test fixture (4 rows) |

---

### What to implement

Mirror `DhanInstrumentKeyAdapter` exactly — substitute `kite_instrument_token` for `dhan_security_id` as the broker-side key column.

`to_broker` converts canonical `NSE_FO|<token>` → Kite instrument token string. `to_canonical` converts Kite instrument token string → canonical key. Both raise `KeyError` with descriptive message on
miss.

---

### Tests — `tests/unit/client/test_adapters_kite.py`

Mirror BA-4 test list exactly:
1. Happy path `to_canonical`
2. Happy path `to_broker`
3. Round-trip
4. Unknown `to_canonical` → `KeyError`
5. Unknown `to_broker` → `KeyError`
6. Missing CSV → `FileNotFoundError`
7. `isinstance` check → `True`

---

### Commit message

```
feat(client): Kite InstrumentKeyAdapter + sample key map

Why: provides canonical ↔ Kite instrument_token translation without mutating stored keys.
What:
- src/client/adapters/kite.py: KiteInstrumentKeyAdapter with O(1) bidirectional lookup
- data/instruments/kite_key_map.csv: 4-row sample mapping
- tests/unit/client/test_adapters_kite.py: 7 adapter tests
- tests/fixtures/instruments/kite_key_map_fixture.csv: test fixture
Ref: docs/plan/broker-abstraction/stories/BA-7.md
```

---

### Pre-baked graph context

```
search_graph("InstrumentKeyAdapter")       # protocol
search_graph("DhanInstrumentKeyAdapter")   # reference implementation to mirror exactly
```


---

## BA-8 — Wire Kite parsers into `factory.py` + integration smoke test

> Assigned to: Claude Phase: 3 — Kite/Zerodha Integration Priority: LOW Blocked by: BA-6 and BA-7 must be merged first

---

### Goal

Extend `factory.py` to support `upstox_env="kite"`. Mirror BA-5 exactly — add Kite selection branch, extend the `upstox_env` Literal, and add a smoke test.

---

### Files to change

| File | Action |
|------|--------|
| `src/client/factory.py` | Add `"kite"` branch to `build_market_data_parser()` |
| `src/config.py` | Extend `upstox_env` Literal to include `"kite"` |
| `tests/unit/client/test_factory_parsers.py` | Extend — add Kite selection + smoke test cases |

---

### What to implement

Extend the selection logic in `build_market_data_parser()`:
- `upstox_env == "kite"` → `KiteMarketDataParser(adapter or _build_kite_adapter())`

`_build_kite_adapter()` constructs `KiteInstrumentKeyAdapter` with `data/instruments/kite_key_map.csv`.

Extend `src/config.py`:
```python
upstox_env: Literal["prod", "sandbox", "test", "dhan", "kite"] = "test"
```

---

### Tests — extend `tests/unit/client/test_factory_parsers.py`

Add:
1. **Kite selection:** `upstox_env="kite"` with injected mock adapter → returns `KiteMarketDataParser`.
2. **Smoke test — Kite parse:** with `upstox_env="kite"`, injected `KiteInstrumentKeyAdapter` using fixture CSV, and Kite chain fixture → valid `OptionChain`.
3. **Protocol conformance:** Kite parser satisfies `isinstance(..., MarketDataParser)`.

---

### Commit message

```
feat(client): wire Kite parsers into factory + smoke test

Why: completes Kite broker integration at the composition root.
What:
- src/client/factory.py: "kite" branch in build_market_data_parser()
- src/config.py: extend upstox_env Literal to include "kite"
- tests/unit/client/test_factory_parsers.py: 3 additional Kite tests
Ref: docs/plan/broker-abstraction/stories/BA-8.md
```

---

### Pre-baked graph context

```
search_graph("build_market_data_parser")  # existing function — add kite branch
search_graph("KiteMarketDataParser")       # confirm BA-6 shipped
search_graph("KiteInstrumentKeyAdapter")   # confirm BA-7 shipped
```


---

## BA-9 — Add Kite credential block to `src/config.py` + `.env.example`

> Assigned to: Claude Phase: 4 — Config + VIX Ingest Priority: LOW Blocked by: BA-8 must be merged first

---

### Goal

Add Kite/Zerodha API credentials to `Settings` and document them in `.env.example`. Dhan credentials already exist in config (`dhan_client_id`, `dhan_access_token`) — mirror that pattern for Kite.

---

### Files to change

| File | Action |
|------|--------|
| `src/config.py` | Add Kite credential fields |
| `.env.example` | Add Kite credential entries with comments |
| `tests/unit/test_config.py` | Extend — test Kite fields load from env |

---

### What to implement

#### `src/config.py` — new fields

```python
# Kite / Zerodha
kite_api_key: str | None = None
kite_access_token: str | None = None   # daily OAuth token
kite_api_secret: str | None = None     # used for token generation only
```

All optional (None by default) — consistent with the rest of the credentials block. `kite_api_secret` is loaded from env but never logged. Add `repr=False` on the field.

#### `.env.example`

```dotenv
# Kite / Zerodha (set upstox_env=kite to activate)
KITE_API_KEY=your_kite_api_key
KITE_ACCESS_TOKEN=daily_access_token_here
KITE_API_SECRET=your_api_secret   # never commit — used only for token generation
```

---

### Tests — extend `tests/unit/test_config.py`

1. **Kite fields present:** `Settings()` has `kite_api_key`, `kite_access_token`, `kite_api_secret` attributes.
2. **Load from env:** `Settings(_env_file=None)` with `KITE_API_KEY="test_key"` in env → `settings.kite_api_key == "test_key"`. # pragma: allowlist secret
3. **Default None:** without env vars, all three Kite fields are `None`.

---

### Commit message

```
feat(config): add Kite/Zerodha credential fields + .env.example entries

Why: completes config surface for Kite broker activation via upstox_env=kite.
What:
- src/config.py: kite_api_key, kite_access_token, kite_api_secret (all Optional)
- .env.example: Kite credential block with comments
- tests/unit/test_config.py: 3 additional config tests
Ref: docs/plan/broker-abstraction/stories/BA-9.md
```

---

### Pre-baked graph context

```
search_graph("Settings")           # current credential fields — mirror Dhan pattern
search_graph("dhan_client_id")     # exact pattern to replicate for Kite
```


---

## BA-10 — Make VIX ingest broker-agnostic

> Assigned to: Claude Phase: 4 — Config + VIX Ingest Priority: LOW Blocked by: BA-5 must be merged first (Dhan env string exists in config)

---

### Goal

`src/backtest/vix_ingest.py` has two fetch paths: NSE CSV (broker-agnostic) and Upstox API. The Upstox API path is tightly coupled to Upstox endpoint URLs and response shape. This story promotes the
NSE CSV path as the primary path and deprecates the Upstox-specific path, so VIX ingestion continues to work regardless of active broker.

**Storage is frozen.** Parquet output at `data/historical/ohlc/india_vix/` is unchanged. Existing Parquet files are not rewritten.

---

### Files to change

| File | Action |
|------|--------|
| `src/backtest/vix_ingest.py` | Refactor: extract `VixFetcher` protocol, deprecate `_fetch_upstox` |
| `tests/unit/backtest/test_vix_ingest.py` | Extend: add deprecation warning test |

---

### What to implement

#### `VixFetcher` protocol (add to `src/backtest/vix_ingest.py`)

```python
@runtime_checkable
class VixFetcher(Protocol):
    """Fetches raw India VIX OHLC rows for a date range.

    Returns a list of dicts with keys: date (str ISO), open, high, low, close (Decimal).
    The caller (VixIngestPipeline) owns writing to Parquet.
    """
    async def fetch(self, start: date, end: date) -> list[dict]: ...
```

#### Existing fetch implementations

- `NseCsvVixFetcher` — wraps the existing NSE CSV download path. Becomes the default.
- `UpstoxVixFetcher` — wraps existing Upstox API path. Add deprecation warning on instantiation: `DeprecationWarning: UpstoxVixFetcher is deprecated; use NseCsvVixFetcher`.

#### `VixIngestPipeline` update

Constructor accepts an optional `fetcher: VixFetcher | None = None`. Default (None) → uses `NseCsvVixFetcher`. Callers that explicitly pass `UpstoxVixFetcher` continue to work but get the deprecation
warning.

#### `scripts/pipeline/upstox_chain_snapshot.py` (if it instantiates VixIngestPipeline)

Check with `search_graph("VixIngestPipeline")` — if the script passes the Upstox fetcher explicitly, update it to omit the fetcher argument (accept the new default).

---

### Tests — extend `tests/unit/backtest/test_vix_ingest.py`

1. **Default fetcher:** `VixIngestPipeline()` (no args) → internal fetcher is `NseCsvVixFetcher`.
2. **Injected fetcher:** `VixIngestPipeline(fetcher=mock_fetcher)` → uses the mock.
3. **Upstox deprecation:** instantiating `UpstoxVixFetcher()` emits `DeprecationWarning`.
4. **Protocol conformance:** `isinstance(NseCsvVixFetcher(), VixFetcher)` → `True`.

---

### Commit message

```
refactor(backtest): make VIX ingest broker-agnostic via VixFetcher protocol

Why: Upstox-specific fetch path blocks VIX ingestion when broker is Dhan or Kite;
     NSE CSV path is broker-neutral and already works — promote it as default.
What:
- src/backtest/vix_ingest.py: VixFetcher protocol, NseCsvVixFetcher default,
  UpstoxVixFetcher deprecated wrapper
- tests/unit/backtest/test_vix_ingest.py: 4 additional tests
Ref: docs/plan/broker-abstraction/stories/BA-10.md
```

---

### Pre-baked graph context

```
search_graph("VixIngestPipeline")      # current constructor signature + callers
search_graph("_fetch_upstox")          # Upstox-specific fetch method location
search_graph("NseCsvVixFetcher")       # may already exist — check before creating
git log --oneline -10 src/backtest/vix_ingest.py   # intent of recent changes
```


---

## BA-11 — `InstrumentMasterLoader` protocol + Upstox BOD adapter

> Assigned to: Claude Phase: 5 — Instrument Master Abstraction Priority: LOW Blocked by: BA-2 must be merged first (mirrors same adapter pattern)

---

### Goal

`src/instruments/lookup.py` and `scripts/lookup/instrument_lookup.py` are hardwired to the Upstox BOD JSON file (`NSE.json.gz` from `assets.upstox.com`). The entire `InstrumentLookup` class parses
Upstox's JSON schema. Dhan and Kite ship their own instrument master files (Dhan: CSV, Kite: CSV from `api.kite.trade/instruments`), which have different column names and no `instrument_key` field.

This story introduces an `InstrumentMasterLoader` protocol so instrument master loading is broker-agnostic. The output of every loader must produce dicts with the canonical `instrument_key`
(`NSE_FO|<token>`) — translation from broker-native IDs uses the `InstrumentKeyAdapter` from BA-2/BA-4/BA-7.

**`src/instruments/lookup.py` core logic (`get_expiry_candidates`, `InstrumentLookup.search`) is not rewritten** — it continues to operate on dicts with canonical keys. Only the *loading* layer
changes.

---

### Files to change

| File | Action |
|------|--------|
| `src/instruments/protocol.py` | New — `InstrumentMasterLoader` protocol |
| `src/instruments/loaders/__init__.py` | New package stub |
| `src/instruments/loaders/upstox_bod.py` | New — wraps existing `InstrumentLookup.from_file` |
| `src/instruments/loaders/dhan.py` | New — Dhan CSV loader stub (raises `NotImplementedError` until Dhan CSV schema confirmed) |
| `src/instruments/loaders/kite.py` | New — Kite CSV loader stub (raises `NotImplementedError` until Kite CSV schema confirmed) |
| `tests/unit/instruments/test_loader_protocol.py` | New — protocol conformance tests |

---

### What to implement

#### `src/instruments/protocol.py`

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class InstrumentMasterLoader(Protocol):
    """Loads broker instrument master data into canonical-key dicts.

    Each returned dict must contain at minimum:
      - instrument_key: str  — canonical "EXCHANGE_SEGMENT|TOKEN" format
      - symbol: str          — NSE ticker (e.g. "NIFTY")
      - expiry: str          — ISO date "YYYY-MM-DD"
      - strike: str          — strike price as string (e.g. "23000.0")
      - option_type: str     — "CE" or "PE"
      - lot_size: int

    Downstream consumers (InstrumentLookup, get_expiry_candidates) depend
    on these keys — do not add broker-specific fields to the output dicts.
    """

    def load(self) -> list[dict]: ...
```

#### `src/instruments/loaders/upstox_bod.py`

```python
class UpstoxBodLoader:
    """InstrumentMasterLoader that reads the Upstox BOD JSON (NSE.json.gz).

    Keys are already canonical — no adapter needed.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[dict]:
        # Delegates to InstrumentLookup.from_file(self._path)._instruments
        # Returns the raw instrument dicts — already canonical
        ...
```

#### Dhan and Kite stubs

Both raise `NotImplementedError` with a clear message explaining that the CSV schema must be confirmed before implementation. Include a docstring describing the expected column mapping when the schema
becomes available.

```python
class DhanInstrumentLoader:
    """InstrumentMasterLoader for Dhan instrument master CSV.

    NOT YET IMPLEMENTED — Dhan CSV column mapping not confirmed.
    Expected columns: security_id, trading_symbol, expiry_date, strike_price,
    option_type, lot_size. Requires DhanInstrumentKeyAdapter to produce canonical keys.
    """
    def load(self) -> list[dict]:
        raise NotImplementedError(
            "DhanInstrumentLoader not yet implemented. "
            "Confirm Dhan CSV column schema before implementing."
        )
```

---

### Tests — `tests/unit/instruments/test_loader_protocol.py`

1. **Protocol conformance:** `isinstance(UpstoxBodLoader(fixture_path), InstrumentMasterLoader)` → `True`.
2. **Load returns canonical keys:** every dict in `UpstoxBodLoader(fixture_path).load()` has `instrument_key` matching `NSE_FO|...` pattern.
3. **Stubs raise NotImplementedError:** `DhanInstrumentLoader().load()` raises `NotImplementedError`; same for `KiteInstrumentLoader`.
4. **Protocol structural check:** a plain class with a `load(self) -> list[dict]` method satisfies `isinstance(..., InstrumentMasterLoader)`.
5. **Missing BOD file:** `UpstoxBodLoader(Path("/nonexistent.json.gz")).load()` raises `FileNotFoundError`.

Use the existing `data/instruments/NSE.json.gz` fixture path (or a 3-row test fixture) — no network calls.

---

### Commit message

```
feat(instruments): InstrumentMasterLoader protocol + Upstox BOD adapter + stubs

Why: decouples instrument master loading from Upstox BOD JSON schema so Dhan/Kite
     loaders can be added without touching InstrumentLookup or get_expiry_candidates.
What:
- src/instruments/protocol.py: InstrumentMasterLoader runtime-checkable Protocol
- src/instruments/loaders/__init__.py: new package stub
- src/instruments/loaders/upstox_bod.py: UpstoxBodLoader wrapping existing BOD logic
- src/instruments/loaders/dhan.py: DhanInstrumentLoader stub (NotImplementedError)
- src/instruments/loaders/kite.py: KiteInstrumentLoader stub (NotImplementedError)
- tests/unit/instruments/test_loader_protocol.py: 5 protocol + conformance tests
Ref: docs/plan/broker-abstraction/stories/BA-11.md
```

---

### Pre-baked graph context

```
search_graph("InstrumentLookup")          # current class — from_file + _instruments field
search_graph("get_expiry_candidates")     # callers — must continue to work unchanged
search_graph("InstrumentKeyAdapter")      # confirm BA-2 shipped before starting
git log --oneline -10 src/instruments/lookup.py
```


---

## BA-12 — `MarketQuoteClient` protocol + Upstox adapter

> Assigned to: Claude Phase: 5 — Instrument Master Abstraction Priority: LOW Blocked by: BA-1 must be merged first. Can run in parallel with BA-11.

---

### Goal

`src/client/upstox_market.py` (`UpstoxMarketClient`) is called directly by `UpstoxLiveClient` and in some paper snapshot scripts. It hardcodes Upstox Analytics Token endpoints for:
- `get_ltp()` — `https://api.upstox.com/v3/market-quote/ltp`
- `get_ohlc_sync()` — `https://api.upstox.com/v3/market-quote/ohlc`
- `get_option_chain()` — `https://api.upstox.com/v2/option/chain`

The `BrokerClient` protocol already declares `get_ltp` and `get_option_chain` at the interface level. The problem is `UpstoxLiveClient.__init__` constructs an `UpstoxMarketClient` directly — it is the
only place in `src/` where a concrete market data class is instantiated outside `factory.py`.

This story introduces a `MarketQuoteClient` protocol (a narrow subset of `BrokerClient` focused on read-only market data) and wires `UpstoxLiveClient` to accept it via constructor injection, removing
the internal `UpstoxMarketClient` instantiation.

**No URL constants change. No Parquet schema changes. No model changes.**

---

### Files to change

| File | Action |
|------|--------|
| `src/client/market_quote_protocol.py` | New — `MarketQuoteClient` protocol (read-only subset) |
| `src/client/upstox_live.py` | Edit — accept injected `MarketQuoteClient`; remove internal `UpstoxMarketClient` construction |
| `src/client/factory.py` | Edit — inject `UpstoxMarketClient` when building `UpstoxLiveClient` |
| `tests/unit/client/test_market_quote_protocol.py` | New — protocol conformance tests |

---

### What to implement

#### `src/client/market_quote_protocol.py`

```python
from decimal import Decimal
from typing import Protocol, runtime_checkable
from src.models.options import OptionChain

@runtime_checkable
class MarketQuoteClient(Protocol):
    """Read-only market data interface: LTP, OHLC, option chain.

    This is the narrow read subset of BrokerClient. Implementing this protocol
    is sufficient for paper trading and portfolio snapshot use cases that do not
    place orders.

    All price values are Decimal. Instrument keys use canonical NSE_FO|token format.
    """

    async def get_ltp(self, instruments: list[str]) -> dict[str, Decimal]:
        """Fetch last traded price for a list of canonical instrument keys.

        Args:
            instruments: List of canonical instrument keys e.g. ["NSE_FO|79653"].

        Returns:
            Dict mapping instrument_key → LTP as Decimal.

        Raises:
            LTPFetchError: If all instruments fail.
        """
        ...

    async def get_option_chain(self, instrument: str, expiry: str) -> dict:
        """Fetch raw option chain for an underlying + expiry.

        Args:
            instrument: Canonical instrument key for the underlying index.
            expiry: Expiry date string "YYYY-MM-DD".

        Returns:
            Raw broker response dict — callers pass this to MarketDataParser.
        """
        ...
```

Note: `get_ohlc_sync()` is intentionally excluded — it is a sync convenience method on `UpstoxMarketClient` used only in a few non-critical places. It does not belong on a protocol; callers of
`get_ohlc_sync` should be identified and migrated to `get_ltp` or a separate async path before Phase 1.

#### `src/client/upstox_live.py` — constructor injection

Change:
```python
# Before
def __init__(self, token: str) -> None:
    self._market = UpstoxMarketClient(token=token)
```

To:
```python
# After
def __init__(self, token: str, market: MarketQuoteClient | None = None) -> None:
    self._market = market or UpstoxMarketClient(token=token)
```

This is backward-compatible — existing callers that pass only `token` continue to work. The `market` parameter is used by tests and `factory.py` for injection.

#### `src/client/factory.py`

No change needed immediately — the default (`market=None`) means `UpstoxLiveClient` self-constructs `UpstoxMarketClient` as before. This story just opens the injection seam. If `factory.py` currently
constructs `UpstoxLiveClient`, verify it passes `token` only — no code change required if so.

---

### Tests — `tests/unit/client/test_market_quote_protocol.py`

1. **Protocol conformance:** `isinstance(UpstoxMarketClient(token="x"), MarketQuoteClient)` → `True`.
2. **Structural conformance:** a mock class with `async get_ltp` and `async get_option_chain` satisfies the protocol.
3. **Non-conforming:** class missing `get_option_chain` → `isinstance` → `False`.
4. **Injection accepted:** `UpstoxLiveClient(token="x", market=mock_market)` uses the injected mock — `get_ltp` call on the client delegates to the mock.
5. **Default fallback:** `UpstoxLiveClient(token="x")` (no market arg) → internal `_market` is `UpstoxMarketClient` instance.

---

### Commit message

```
feat(client): MarketQuoteClient protocol + constructor injection in UpstoxLiveClient

Why: removes internal UpstoxMarketClient construction from UpstoxLiveClient so
     market data can be swapped in tests and future broker implementations.
What:
- src/client/market_quote_protocol.py: MarketQuoteClient runtime-checkable Protocol
- src/client/upstox_live.py: accept injected MarketQuoteClient; default unchanged
- tests/unit/client/test_market_quote_protocol.py: 5 protocol + injection tests
Ref: docs/plan/broker-abstraction/stories/BA-12.md
```

---

### Pre-baked graph context

```
search_graph("UpstoxLiveClient")          # constructor + _market usage
search_graph("UpstoxMarketClient")        # get_ltp / get_option_chain signatures
search_graph("get_ltp")                   # all callers — must not break
trace_path("get_ltp")                     # confirm no direct UpstoxMarketClient refs in callers
search_graph("BrokerClient")             # existing protocol to avoid duplicating
git log --oneline -10 src/client/upstox_live.py
```


---

## BA-13 — Broker-agnostic Parquet filename prefix in `chain_writer` / `chain_reader`

> Assigned to: Antigravity Phase: 5 — Instrument Master Abstraction Priority: LOW Blocked by: BA-1 must be merged first (confirms broker env string pattern) Note: Existing Parquet files on disk are
> NOT renamed — only new writes change.

---

### Goal

`src/backtest/chain_writer.py` writes files as `upstox_YYYYMMDD.parquet` and `upstox_HHMM.parquet`. `src/backtest/chain_reader.py` globs for `upstox_*.parquet`.

When chain snapshots are fetched from Dhan or Kite, the prefix should reflect the source broker — or be removed entirely. This story makes the prefix configurable via a constructor parameter,
defaulting to `"upstox"` for backward compatibility with existing Parquet files on disk.

**Existing files are never touched.** The reader must continue to find them.

---

### Files to change

| File | Action |
|------|--------|
| `src/backtest/chain_writer.py` | Accept `broker_prefix: str = "upstox"` in constructor |
| `src/backtest/chain_reader.py` | Accept `broker_prefix: str = "upstox"` in constructor; update glob |
| `tests/unit/backtest/test_chain_writer.py` | Extend — test custom prefix produces correct filename |
| `tests/unit/backtest/test_chain_reader.py` | Extend — test custom prefix glob matches correct files |

---

### What to implement

#### `src/backtest/chain_writer.py`

Change `ChainWriter.__init__` to accept:
```python
def __init__(
    self,
    eod_dir: Path,
    intraday_dir: Path,
    broker_prefix: str = "upstox",
) -> None:
```

Use `self._prefix` in place of the hardcoded `"upstox"` string when constructing filenames:
- EOD: `f"{self._prefix}_{date_str}.parquet"` (was `f"upstox_{date_str}.parquet"`)
- Intraday: `f"{self._prefix}_{hhmm}.parquet"` (was `f"upstox_{hhmm}.parquet"`)

#### `src/backtest/chain_reader.py`

Same pattern:
```python
def __init__(
    self,
    eod_dir: Path,
    intraday_dir: Path,
    broker_prefix: str = "upstox",
) -> None:
```

Update the two glob patterns:
- EOD: `f"{self._prefix}_*.parquet"` (was `"upstox_*.parquet"`)
- Intraday: `f"{self._prefix}_*.parquet"`

Verify all existing callers of `ChainWriter` and `ChainReader` pass positional `eod_dir` / `intraday_dir` only — they will receive the `"upstox"` default and behaviour is unchanged.

---

### Tests

#### `tests/unit/backtest/test_chain_writer.py` — add:

1. **Default prefix:** `ChainWriter(eod_dir, intraday_dir)` → EOD file written as `upstox_YYYYMMDD.parquet`.
2. **Custom prefix:** `ChainWriter(eod_dir, intraday_dir, broker_prefix="dhan")` → EOD file written as `dhan_YYYYMMDD.parquet`.

#### `tests/unit/backtest/test_chain_reader.py` — add:

3. **Default prefix glob:** reader with default prefix finds `upstox_*.parquet` files.
4. **Custom prefix glob:** reader with `broker_prefix="dhan"` finds `dhan_*.parquet` files and does not match `upstox_*.parquet`.

---

### Commit message

```
feat(backtest): configurable broker prefix in ChainWriter + ChainReader

Why: enables Dhan/Kite chain snapshots to be stored with correct source prefix
     without breaking existing upstox_*.parquet files on disk.
What:
- src/backtest/chain_writer.py: broker_prefix constructor param (default "upstox")
- src/backtest/chain_reader.py: broker_prefix constructor param (default "upstox")
- tests/unit/backtest/test_chain_writer.py: 2 additional prefix tests
- tests/unit/backtest/test_chain_reader.py: 2 additional prefix tests
Ref: docs/plan/broker-abstraction/stories/BA-13.md
```

---

### Pre-baked graph context

```
search_graph("ChainWriter")       # constructor signature + write_eod_snapshot callers
search_graph("ChainReader")       # constructor signature + callers
git log --oneline -10 src/backtest/chain_writer.py
```


---

## BA-14 — Auth flow abstraction: `BrokerAuthProvider` protocol

> Assigned to: Claude Phase: 6 — Auth Abstraction (Phase 1+ gate) Priority: LOW ⚠️ BLOCKED until `src/execution/` is built (Phase 1 gate). Do NOT start before then.

---

### Background

`src/auth/login.py` is hardwired to Upstox OAuth:
- Imports `upstox_client` SDK directly
- Hardcodes the Upstox authorization dialog URL
- Writes `UPSTOX_ACCESS_TOKEN` to `.env`

Dhan does not use OAuth — it uses a static access token generated from the Dhan web portal (Client ID + Access Token). Kite uses its own OAuth flow (`kite.trade/connect/login`).

This is the most invasive broker dependency but also the least urgent — auth is called once daily (or on demand) and is already isolated in `src/auth/`. It is **not blocking** any paper trading or
backtesting work.

**This story must not start until `src/execution/` (live order execution layer) exists**, because the auth token is only needed when placing real orders. Until then, the current Upstox OAuth flow is
sufficient.

---

### Goal

Introduce a `BrokerAuthProvider` protocol so each broker's daily token refresh logic is interchangeable. The rest of the codebase only ever touches the token string (via
`settings.upstox_access_token`); the auth flow that produces that token should be pluggable.

---

### Files to change

| File | Action |
|------|--------|
| `src/auth/protocol.py` | New — `BrokerAuthProvider` protocol |
| `src/auth/providers/__init__.py` | New package stub |
| `src/auth/providers/upstox.py` | New — wraps existing `src/auth/login.py` flow |
| `src/auth/providers/dhan.py` | New — Dhan static token provider (reads from `settings.dhan_access_token`) |
| `src/auth/providers/kite.py` | New — Kite OAuth stub (raises `NotImplementedError` until Kite OAuth confirmed) |
| `src/auth/login.py` | Edit — add deprecation shim; existing behaviour unchanged |
| `tests/unit/auth/test_auth_protocol.py` | New — protocol conformance tests |

---

### What to implement

#### `src/auth/protocol.py`

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class BrokerAuthProvider(Protocol):
    """Produces a valid broker access token.

    Each broker's daily auth flow is isolated here. The token produced is
    written to settings / .env so the rest of the system can read it via
    the Settings singleton.

    Implementations must be idempotent: calling refresh_token() when a valid
    token already exists must not error and may return the cached token.
    """

    def refresh_token(self) -> str:
        """Obtain or refresh the broker access token.

        Returns:
            Valid access token string.

        Raises:
            AuthError: If the token cannot be obtained (wrong credentials,
                       network failure, OAuth code exchange failure, etc.).
        """
        ...

    def is_token_valid(self) -> bool:
        """Check whether the current token is still valid without refreshing.

        Returns:
            True if the current token is usable; False if refresh is needed.
        """
        ...
```

#### `src/auth/providers/upstox.py`

```python
class UpstoxAuthProvider:
    """BrokerAuthProvider wrapping the existing Upstox OAuth flow.

    Delegates to src.auth.login for the browser-based authorization code flow.
    Token is written to .env on success.
    """

    def refresh_token(self) -> str:
        from src.auth.login import run_oauth_flow  # lazy import — avoids upstox_client at import time
        return run_oauth_flow()

    def is_token_valid(self) -> bool:
        token = settings.upstox_access_token
        return token is not None and len(token) > 0
```

#### `src/auth/providers/dhan.py`

```python
class DhanAuthProvider:
    """BrokerAuthProvider for Dhan — token is static (no OAuth flow).

    Dhan access tokens are generated manually from the Dhan web portal
    and set in DHAN_ACCESS_TOKEN env var. This provider validates that
    the token is present; it cannot refresh automatically.
    """

    def refresh_token(self) -> str:
        token = settings.dhan_access_token
        if not token:
            raise AuthError(
                "DHAN_ACCESS_TOKEN not set. Generate a token from the Dhan "
                "web portal and set it in your .env file."
            )
        return token

    def is_token_valid(self) -> bool:
        return bool(settings.dhan_access_token)
```

#### `src/auth/providers/kite.py`

Stub — raises `NotImplementedError` with a comment describing the Kite OAuth flow (request token → session token exchange via `/session/token` endpoint).

#### `src/auth/login.py` — deprecation shim

Preserve the existing `main()` / `run_oauth_flow()` functions unchanged. Add a module-level deprecation note in the docstring:
> Deprecated: use `UpstoxAuthProvider` from `src.auth.providers.upstox` for new code.

Do not change any existing function signatures — this is a pure additive shim.

---

### Tests — `tests/unit/auth/test_auth_protocol.py`

1. **Protocol conformance — Upstox:** `isinstance(UpstoxAuthProvider(), BrokerAuthProvider)` → `True`.
2. **Protocol conformance — Dhan:** `isinstance(DhanAuthProvider(), BrokerAuthProvider)` → `True`.
3. **Dhan valid token:** with `DHAN_ACCESS_TOKEN="test"` in env → `DhanAuthProvider().is_token_valid()` → `True` and `refresh_token()` → `"test"`.
4. **Dhan missing token:** `DHAN_ACCESS_TOKEN` not set → `DhanAuthProvider().refresh_token()` raises `AuthError`.
5. **Kite stub:** `KiteAuthProvider().refresh_token()` raises `NotImplementedError`.
6. **Structural conformance:** plain class with `refresh_token` + `is_token_valid` satisfies protocol.

No network calls. `UpstoxAuthProvider` tests use mocking only — do not invoke the real OAuth flow.

---

### Commit message

```
feat(auth): BrokerAuthProvider protocol + Upstox/Dhan providers + Kite stub

Why: isolates broker-specific daily token refresh so auth flow is swappable
     alongside BrokerClient and MarketDataParser at the factory boundary.
What:
- src/auth/protocol.py: BrokerAuthProvider runtime-checkable Protocol
- src/auth/providers/__init__.py: package stub
- src/auth/providers/upstox.py: UpstoxAuthProvider wrapping existing OAuth flow
- src/auth/providers/dhan.py: DhanAuthProvider (static token, no OAuth)
- src/auth/providers/kite.py: KiteAuthProvider stub (NotImplementedError)
- src/auth/login.py: deprecation note added to module docstring
- tests/unit/auth/test_auth_protocol.py: 6 tests
Ref: docs/plan/broker-abstraction/stories/BA-14.md
```

---

### Pre-baked graph context

```
search_graph("AuthError")               # confirm exception class exists in src/client/exceptions.py
search_graph("BrokerAuthProvider")      # must return zero results (confirm not already created)
search_graph("run_oauth_flow")          # confirm existing function name in src/auth/login.py
search_graph("dhan_access_token")       # confirm settings field name
git log --oneline -10 src/auth/login.py
```

**Gate check before starting:** run `search_graph("ExecutionClient")` or equivalent. If `src/execution/` classes do not exist → do not start this story. Come back after Phase 1 gate.


---

## BA-15 — Remove `upstox_client` SDK direct import from `sandbox_order_lifecycle.py`

> Assigned to: Antigravity Phase: 6 — Auth Abstraction (Phase 1+ gate) Priority: LOW (dev/diagnostic script — no production impact) Blocked by: BA-12 (`MarketQuoteClient` protocol) should be merged
> first

---

### Goal

`scripts/dev/sandbox_order_lifecycle.py` imports `upstox_client` and `upstox_client.rest` directly. It bypasses the `BrokerClient` protocol entirely, using the Upstox SDK objects to place sandbox
orders. This script cannot be ported to Dhan or Kite without a full rewrite.

This story refactors the script to use `BrokerClient` protocol methods via `factory.py`, removing the direct SDK dependency. The script remains Upstox-only in practice (since it targets the sandbox
environment) but its structure becomes consistent with the rest of the codebase.

**This is a dev/diagnostic script.** There are no callers in production cron jobs. Low risk, low priority. If the refactor is complex or the script is rarely used, defer.

---

### Files to change

| File | Action |
|------|--------|
| `scripts/dev/sandbox_order_lifecycle.py` | Refactor — replace `upstox_client` SDK calls with `BrokerClient` protocol methods |

---

### What to implement

Replace:
```python
import upstox_client
from upstox_client.rest import ApiException
```

With:
```python
from src.client.factory import build_broker_client
from src.client.protocol import OrderRequest
```

Replace direct SDK object construction (`upstox_client.PlaceOrderV3Request(...)`) with `OrderRequest` dicts and `BrokerClient.place_order()` calls.

Replace `ApiException` catch blocks with `BrokerError` subclass catches from `src/client/exceptions.py`.

The `UPSTOX_ENV=sandbox` env var already routes `factory.build_broker_client()` to the sandbox client — no additional configuration needed.

If any order field mapping from the Upstox SDK request format to `OrderRequest` dict is non-obvious, document it in a comment rather than silently guessing.

---

### Tests

No unit tests required for this story — `sandbox_order_lifecycle.py` is a dev script with no public functions. Add a module docstring update noting the refactor date and confirming it was tested
against the Upstox sandbox.

Manual verification step (not automated):
```bash
UPSTOX_ENV=sandbox python -m scripts.dev.sandbox_order_lifecycle --dry-run
```
Confirm the script runs without `ImportError` or `AttributeError`.

---

### Commit message

```
refactor(dev): remove upstox_client SDK import from sandbox_order_lifecycle

Why: direct SDK imports in scripts are inconsistent with BrokerClient protocol pattern
     and block future broker porting.
What:
- scripts/dev/sandbox_order_lifecycle.py: use factory.build_broker_client + BrokerClient
  protocol; replace ApiException with BrokerError hierarchy
Ref: docs/plan/broker-abstraction/stories/BA-15.md
```

---

### Pre-baked graph context

```
search_graph("build_broker_client")     # factory function signature
search_graph("OrderRequest")            # current type alias (dict) in protocol.py
search_graph("BrokerError")             # exception hierarchy root
search_graph("place_order")             # BrokerClient.place_order signature
git log --oneline -10 scripts/dev/sandbox_order_lifecycle.py
```
