# NiftyShield — Unified Codebase Review Prompt

**Use this prompt to drive a full codebase review via a subagent or council call.**
**Output format:** findings ordered from smallest → biggest impact (not by file or severity bucket).

---

## Context

You are reviewing the NiftyShield trading automation codebase — a Python 3.10+ system for
options selling on NSE (Nifty/NiftyBees), backtesting against historical data, and live
portfolio monitoring. Financial correctness bugs here have real monetary consequences.

Read the following before starting:
- `CONTEXT.md` — module tree and authoritative state
- `REVIEW.md` — full Python hygiene checklist (Parts I, II, III)
- `src/client/protocol.py` — BrokerClient protocol definition
- `src/client/exceptions.py` — exception hierarchy

Then scan every file under `src/` and `scripts/`. For each finding, apply the checklist below.

---

## Checklist — in priority order

### Tier 1: Financial Correctness (data corruption / silent wrong P&L)

**T1-A. Decimal Invariant**
- Every monetary field (`entry_price`, `ltp`, `close`, `underlying_price`, `price`,
  `units`, `amount`, `nav`, `settle_price`) must be `Decimal`, never `float`.
- Float values arriving from the Upstox API must be converted at the boundary:
  `Decimal(str(float_val))` — never `Decimal(float_val)` (binary float imprecision).
- SQLite reads: always `Decimal(row["col"])`, never `float(row["col"])`.
- SQLite writes: stored as TEXT, never REAL column type.
- Flag any `float()` cast on a monetary value, or any arithmetic mixing `float` and `Decimal`
  without explicit conversion. Severity: **CRITICAL**.

**T1-B. India-Specific Market Microstructure**

These are implementation-breaking gaps specific to NSE/Indian options:

1. **Bhavcopy VWAP vs Upstox EOD LTP.** NSE Bhavcopy uses a 30-minute VWAP (3:00–3:30 PM)
   for settlement, not 3:30 PM LTP. IV reconstruction using Bhavcopy `settle_price` as input
   diverges from live Greeks on volatile close days. Any code path that feeds `settle_price`
   from Bhavcopy into a BS model without documenting the VWAP-LTP distinction is a bug.
   The validation target for IV reconstruction must be Upstox EOD LTP (live snapshot),
   not Bhavcopy settle price. Severity: **CRITICAL** for any backtest IV path.

2. **Historical lot size.** Nifty lot sizes changed: 75 → 50 → 25 across the 8-year backtest
   window (approximate transitions: 75 lots pre-2019, 50 lots 2019–2024, 25 lots from ~2024).
   Any code that hardcodes `lot_size = 25` or doesn't resolve lot size by date makes P&L,
   margin math, and variance check distributions structurally invalid for 2016–2022 data.
   Flag any hardcoded lot size constant without a date-range lookup. Severity: **CRITICAL**.

3. **Expiry-day STT trap.** A short put expiring ITM incurs STT at 0.125% on intrinsic value
   vs 0.0625% on premium if squared off by 3:15 PM — a 2× cost difference that compounds
   across backtested tail scenarios. Any cost model that doesn't distinguish ITM-expiry from
   squared-off P&L is understating tail losses. Flag any `compute_pnl` / `cost_model` path
   that applies a single STT rate regardless of expiry outcome. Severity: **CRITICAL**.

4. **Weekly vs monthly expiry transitions.** Nifty moved to weekly expiries mid-2019. Any
   calendar logic, expiry resolver, or backtest engine that assumes monthly-only expiries
   before 2019 and weekly-only after 2019 without an explicit transition date is wrong.
   Flag any hardcoded expiry-day-of-week assumption (e.g., "always Thursday") that doesn't
   account for the Nifty monthly expiry still running on the last Thursday of the month
   alongside weeklies. Severity: **ERROR**.

**T1-C. strategy_name Correctness**
- Anywhere `strategy_name` is hardcoded, it must be exactly `finideas_ilts` or `finrakshak`.
  Any other value silently disables the trade overlay (Leg/Trade join logic depends on this
  string match). Flag as **CRITICAL**.

---

### Tier 2: Protocol and Async Correctness (crashes / silent wrong behavior)

**T2-A. BrokerClient Protocol**
- No file outside `src/client/factory.py` may import `UpstoxLiveClient` or `MockBrokerClient`
  directly. All modules must accept `BrokerClient` (or a sub-protocol) via constructor
  injection. Any `from src.client.upstox_live import` or `from src.client.mock_client import`
  outside `factory.py` is an **ERROR**.

**T2-B. Async Hot Path**
- No blocking calls (`requests.get`, `time.sleep`, synchronous `open()`, `sqlite3` operations)
  in any `async def` that is part of the event-loop hot path (`_async_main()` or any coroutine
  it awaits). Flag as **ERROR**.
- All Upstox REST calls must be `await`ed — flag any coroutine used without `await` as **ERROR**.
- No unbounded `await` — every `aiohttp` call must have explicit timeout handling. Flag
  missing timeouts as **ERROR**.
- `asyncio.run()` called from inside a coroutine (nested event loop) is **ERROR**.

**T2-C. Non-Fatal Notification Contract**
- `TelegramNotifier.send()` must never re-raise. Any code path that allows `send()` to
  propagate an exception breaks the non-fatal contract. Flag as **ERROR**.
- Every caller of `build_notifier()` must guard with `if notifier:` before calling `.send()`.
  Unguarded `.send()` on a potentially-None notifier is **ERROR**.

**T2-D. Backtest Reproducibility**
- Every backtest run must record: `git_commit` hash, `strategy_spec_hash` (config YAML
  checksum), `data_version` (Parquet file checksums or date range), `cost_model_version`,
  and `run_timestamp`. Any backtest results store that omits these fields makes debugging
  variance check failures impossible (can't distinguish "I fixed a bug" from "data changed
  under me"). Flag missing lineage metadata as **ERROR**.

---

### Tier 3: Type Safety and Python Bug Classes (silent wrong behavior)

Apply every rule from `REVIEW.md` Part I. Key ones most likely to surface here:

**T3-A. Mutable Default Arguments** — any `def f(x=[])` or `def f(x={})`. Severity: **ERROR**.

**T3-B. Bare or Overly Broad `except`** — `except:` or `except Exception: pass` without
logging and an explicit intent comment. Severity per REVIEW.md G5: **CRITICAL** for broad
catch without justification, **WARNING** if logged but unjustified.

**T3-C. Float Comparisons** — `==` between `float` values in any financial context. Use
`Decimal` or `math.isclose()`. Severity: **ERROR** for financial paths, **WARNING** elsewhere.

**T3-D. Generator Exhaustion** — generator passed as argument and consumed more than once;
second iteration silently returns nothing. Severity: **ERROR** if in data pipeline.

**T3-E. Dict/Set/List Mutation During Iteration** — `.pop()`, `.update()`, `del`, `.append()`
on the container being iterated. Severity: **ERROR**.

**T3-F. `__eq__` Without `__hash__`** — any class defining `__eq__` must explicitly define
`__hash__` or be documented as unhashable. Severity: **WARNING**.

**T3-G. `None` as Sentinel When `None` Is a Valid Domain Value** — use `_MISSING = object()`
instead. Severity: **WARNING**.

**T3-H. SQL / Shell Injection** — f-strings feeding into `cursor.execute()` or
`os.system()` / `subprocess`. Use parameterized queries and argument lists. Severity: **CRITICAL**.

**T3-I. Late Binding Closures** — lambdas or nested functions inside loops that capture the
loop variable without binding (`lambda i=i: i`). Severity: **ERROR**.

**T3-J. `zip` Without `strict=True`** — silent truncation on mismatched-length sequences.
Python 3.10+ project; all `zip()` calls over parallel sequences should use `strict=True`.
Severity: **WARNING**.

**T3-K. Set Iteration Order Assumptions** — `list(some_set)[0]` or any ordering assumption
on an unordered `set`. Severity: **ERROR** if result feeds into logic.

**T3-L. `copy.copy()` on Nested Mutables** — should be `copy.deepcopy()` for complex objects.
Severity: **WARNING**.

---

### Tier 4: Type Hints (missing contracts)

- Every public function and method must have type hints on all parameters and return type.
  `-> None` must be explicit, not omitted.
- Pydantic models must not use bare `dict` or `list` where a typed model exists.
- `Any` is only permitted at true system boundaries (JSON deserialization, untyped third-party
  libs). Severity: **WARNING** per missing hint; **ERROR** if `Any` propagates through
  business logic.

---

### Tier 5: Google Style Guide (new code only — applies at diff level)

From `REVIEW.md` Part III:

- **G1**: No `@staticmethod` in any class — move to module-level private function. **CRITICAL**.
- **G2**: Line length ≤ 80 characters. **WARNING**.
- **G3**: No vertical token alignment. **WARNING**.
- **G4**: Every `# TODO:` must include a bug tracker reference (URL or issue ID). **WARNING**.
- **G5**: `except Exception` without an inline intent comment. **CRITICAL**.
- **G6**: No `assert` outside `tests/` — use domain exceptions. **CRITICAL**.
- **G7**: Logger calls must use `%`-style formatting, not f-strings. **CRITICAL**.
- **G8**: Import ordering — three groups, blank-line separated, alphabetically sorted within
  groups. **ERROR**.

---

### Tier 6: Structural / Clean Code

From `REVIEW.md` Part II:

- Functions mixing abstraction levels (fetch + transform + validate + persist in one body).
- Boolean names that are nouns not predicates (`flag`, `check`, `status` vs `is_valid`).
- Classes with only `__init__` and one method — probably a function with a config object.
- Missing `__repr__` on non-dataclass classes used in logs or tracebacks.
- Comprehensions with more than one `if` or nested `for` — should be a loop.
- `range(len(items))` instead of `enumerate`.
- Missing `field(default_factory=...)` in `@dataclass` mutable fields.
- Walrus operator (`:=`) scope collision with outer variables.

Severity: **WARNING** for all items in this tier.

---

### Tier 7: Design Quality — DRY, KISS, Cohesion, Coupling

This tier is about structural debt: code that works correctly today but will compound into
maintenance cost or silent divergence over time. Flag at **WARNING** unless the duplication
involves financial logic (Decimal paths, cost model, Greeks), in which case flag as **ERROR**
— duplicated financial logic means two places to fix when the rule changes, and one will
always be missed.

#### 7-A. DRY — Don't Repeat Yourself

**What to scan for:**

1. **Same calculation in 2+ places.** Any block of 5+ lines doing the same transform —
   Decimal conversion, Greek calculation, cost model arithmetic, lot-size resolution —
   appearing in more than one file without being extracted to a shared helper. The canonical
   NiftyShield risk: slippage calculation or STT formula duplicated across backtest engine
   and live P&L tracker. When the formula changes (and it will — STT rates change), only
   one copy gets updated.

2. **SQLite access outside `src/db.py`.** Any module under `src/` or `scripts/` that opens
   its own `sqlite3.connect()` instead of going through the shared `db.py` context manager.
   The shared manager handles WAL mode, row_factory, and Decimal TEXT serialization
   consistently. Raw `connect()` calls in business logic mean those guarantees don't apply
   and the connection may not be closed on exception.

3. **Copy-pasted model construction.** If the same `Leg(...)` or `Trade(...)` construction
   block (with the same field assignments) appears in more than one place — a script, a
   test, and a tracker — it should be a factory function or a `from_api_response()` class
   method. Any future required-field addition breaks every callsite silently.

4. **Duplicate validation logic.** Field-level validation (e.g., checking that `expiry` is
   a valid Thursday, that `quantity > 0`, that `strike` aligns to the NSE strike interval)
   written inline in multiple functions rather than in the model's `__post_init__` or
   Pydantic validator. Inline validation diverges; model-level validation can't be bypassed.

5. **Telegram notification calls scattered in business logic.** Any `notifier.send()` call
   embedded inside a store, tracker, or engine function. Notifications are a side effect;
   they belong in the orchestration layer (scripts or the tracker that drives the store),
   not inside functions that should be pure transforms. Scattered sends are impossible to
   silence in tests without mocking the notifier everywhere.

6. **Repeated API shape handling.** If two or more modules parse the same Upstox API
   response shape (e.g., option chain Greeks, LTP batch response) independently, that
   parsing belongs in one place — either a `BrokerClient` method or a dedicated parser
   module. Divergent parsers produce divergent field interpretations under edge cases
   (missing keys, null Greeks, rate-limit partial responses).

#### 7-B. KISS — Keep It Simple

**What to scan for:**

1. **Indirection with no variance.** A function or method whose entire body is a single
   call to another function with the same arguments, and no transformation, logging, or
   error handling added. This is not abstraction — it's indirection. Name the real function
   clearly and call it directly.

2. **Protocol or ABC with only one real implementation.** A `Protocol` or `ABC` class that
   has exactly one concrete implementation (other than the `MockBrokerClient`) and no plan
   for a second. The `BrokerClient` protocol is justified — it has `UpstoxLiveClient`,
   `MockBrokerClient`, and `UpstoxSandboxClient`. A protocol with one implementation and
   one mock that is never varied is just interface ceremony. Prefer a concrete class with
   injected dependencies.

3. **Config dataclass with >8 fields where the callsite only varies 2–3.** A configuration
   object that forces callers to construct 10 fields to change 2 is not a simplification —
   it is the complexity of 10 fields hidden behind a constructor. Use keyword arguments with
   defaults directly on the function, or split into a required-fields object and an
   optional-overrides object.

4. **Factory for a non-varying object.** A factory function or class that always returns
   the same concrete type with no conditional logic. Factories are justified when the type
   or construction varies based on input (as `factory.py` does with `UPSTOX_ENV`). A
   factory that always constructs the same class is just a renamed constructor.

5. **Multi-step pipeline where a single pass works.** Any sequence of `.apply()`, `.map()`,
   or list comprehension chains that iterate over the same dataset N times when a single
   pass with a compound transform would be equivalent. In a backtesting context with
   millions of rows, this is also a performance issue.

6. **Exception wrapping that loses information.** `raise NewException("something failed")`
   inside an `except` block without `from e` (i.e., without `raise NewException(...) from e`).
   This severs the exception chain and makes stack traces useless in production logs.
   Use `raise NewException(...) from e` always. Severity: **ERROR**.

#### 7-C. Cohesion — Each Module Owns One Thing

**What to scan for:**

1. **Modules importing from 5+ other `src/` modules.** High fan-in import counts signal
   that a module is doing coordination work it shouldn't. Either it should be broken apart,
   or the coordinated modules should expose a higher-level API so the coordinator's imports
   reduce.

2. **Business logic living in `scripts/`.** Scripts are entry points — argument parsing,
   environment setup, orchestration. Any non-trivial calculation (P&L, Greeks, margin math,
   expiry resolution) found in a script file instead of a `src/` module cannot be unit-tested
   without invoking the script. Extract to `src/` and call from the script.

3. **A function that accesses more than 3 fields of a passed model.** When a function
   accepts a `Leg` or `Trade` but reaches into 6 of its fields, the function belongs on the
   model itself (as a method) or the model should expose a computed property. Deep field
   access is a symptom of feature envy — the function wants to be the model.

4. **Notification side effects inside `src/` core modules.** A `store.py` or `tracker.py`
   that calls `notifier.send()` directly is mixing persistence and alerting. The notifier
   is a dependency that should be injected and called by the orchestrator, not by the layer
   below it. This also makes stores impossible to test without a live or mock notifier.

#### 7-D. Coupling — Modules Should Know Less About Each Other

**What to scan for:**

1. **`scripts/` importing `src/` internals directly.** Any `from src.client.upstox_live import`
   or `from src.portfolio.store import _private_helper` in a script. Scripts should use the
   public module API only. Internal imports couple the script to implementation details that
   are not part of the module's contract.

2. **Cross-module `isinstance` checks.** If module A checks `isinstance(obj, ConcreteClassFromModuleB)`,
   A is coupled to B's implementation, not its interface. Use duck typing or protocol checks
   (`isinstance(obj, SomeProtocol)` with `runtime_checkable`) or move the behaviour onto
   the object itself.

3. **Hardcoded file paths outside config.** Any `open("data/portfolio/portfolio.sqlite")`
   or `Path("logs/snapshot.log")` embedded in a `src/` module. Paths belong in config or
   are passed as arguments. Hardcoded paths make the module untestable without the real
   directory structure present.

4. **Direct SQLite schema knowledge across module boundaries.** If `src/mf/tracker.py`
   knows the column names of the `portfolio` table defined in `src/portfolio/store.py`,
   those two modules are structurally coupled. Any schema change breaks both. The owning
   module should expose a query method; the consuming module should call that method,
   not write raw SQL against another module's table.

---

### Tier 8: Structural Integrity — SOLID Principles

DRY/KISS keeps code readable. SOLID keeps it **changeable without breakage**. A trading
system accumulates requirement changes faster than most software: broker APIs change, NSE
rules change, strategy parameters change, cost models change. Code that isn't structurally
sound makes each of those changes a archaeology exercise.

Severity for all items in this tier: **WARNING** unless a violation also triggers a Tier 1–2
rule (e.g., a God Class that also bypasses the BrokerClient protocol → **ERROR**).

#### 8-A. SRP — Single Responsibility: The "Change Vector" Test

A class or module has a single responsibility if there is only **one reason for it to change**.
Apply this test to every non-trivial class in `src/`:

> "If the broker API changes, does this class need to change? If the strategy rules change,
> does this class *also* need to change?"

If the answer to both is "yes", the class carries two responsibilities and must be split.

**NiftyShield-specific smells to scan for:**
- Any `engine.py` or `tracker.py` that handles data fetch, signal generation, *and* database
  persistence in one class body. The fetch layer changes when the API changes; the persistence
  layer changes when the schema changes; the signal layer changes when the strategy spec
  changes. Three change vectors = three classes (or at minimum three clearly separated methods
  that could be extracted).
- A `Notifier` that also formats messages *and* decides which events are worth notifying.
  Formatting belongs in a renderer; routing logic belongs in the caller. The `TelegramNotifier`
  should only send — it should not decide what merits a notification.
- A script (`daily_snapshot.py`, `record_trade.py`) that both validates input *and* persists
  *and* sends notifications inline. Scripts are orchestrators; each of those three steps
  belongs in a `src/` module the script calls.

#### 8-B. OCP — Open/Closed: The "Switch-Case" Smell

Code should be **open for extension, closed for modification**. The signal: a long
`if/elif/match` block that checks a type tag to branch into different behaviour.

**NiftyShield-specific smells to scan for:**
- Any chain like `if strategy_name == "finideas_ilts": ... elif strategy_name == "finrakshak": ...`
  branching into different leg-construction, exit-condition, or cost-model logic. This means
  every new strategy requires editing the existing branch, which risks breaking the existing
  strategies. The correct structure is a `Strategy` protocol with a `compute_legs()` /
  `check_exit()` method — each strategy is a class, adding a new one touches zero existing code.
- Any `if instrument_type == "CE": ... elif instrument_type == "PE": ...` in the backtest
  engine that could be resolved by the option leg object knowing its own payoff. The engine
  should call `leg.pnl_at(spot)`, not branch on the leg's type.
- Exit condition routing in the backtester: `if exit_reason == "expiry": ... elif exit_reason == "stop_loss": ...`
  Each exit type should be a handler that computes cost differently; the engine dispatches
  to the handler, not inspects the string.

#### 8-C. DIP — Dependency Inversion: The "Hard-Coded Import" Trap

High-level policy modules must not depend on low-level implementation details. They should
depend on abstractions (protocols/ABCs), with concrete implementations injected.

**This project already enforces DIP for the broker layer** (`BrokerClient` protocol,
constructor injection, `factory.py` as composition root). The review focus is on whether
this discipline has held as the codebase grew, and whether it extends beyond the client layer.

**What to scan for:**
- `self.client = UpstoxLiveClient()` anywhere in `src/` outside `factory.py`. The correct
  form is `self.client: BrokerClient = client` (constructor injection). Any `new`-style
  construction of a concrete client inside a business-logic class breaks the mock/sandbox
  test path.
- Any `src/` module that `import`s a specific database adapter (`sqlite3`, `aiosqlite`) and
  constructs connections directly, rather than accepting a connection or using `src/db.py`.
  The persistence layer is also an implementation detail — high-level modules shouldn't
  depend on it concretely.
- Any `src/` class that calls `os.environ["UPSTOX_ACCESS_TOKEN"]` directly. Config/credential
  resolution belongs at the composition root, not embedded in business logic. Modules that
  read env vars directly are impossible to test with alternate config without process-level
  hacks.
- **ISP sub-check:** If the `BrokerClient` protocol has grown to include methods that not all
  consumers use, check whether it should be split into narrower sub-protocols
  (`MarketDataClient`, `OrderClient`, `PortfolioClient`). A module that only needs LTP data
  should not depend on a protocol that includes `place_order()`.

---

### Tier 9: Domain Integrity — Tactical DDD

In trading, the most expensive bugs are not crashes — they are **semantic drift**: the code's
math stops matching the market's reality, silently. DDD's lightweight patterns are a defence
against this.

Severity: **WARNING** for design drift; **ERROR** if a domain violation also causes a Tier 1
financial correctness issue (e.g., a "Primitive Obsession" where a raw `float` slips through
where a validated `Decimal` was required).

#### 9-A. Primitive Obsession — Value Objects for Domain Concepts

**The smell:** passing raw `Decimal`, `int`, or `str` through function signatures for concepts
that have domain rules attached to them.

**NiftyShield-specific patterns to flag:**

- `strike: Decimal` passed between 5 functions with no validation that it aligns to the
  NSE strike interval (50-point intervals for Nifty below ~18000; 100-point above). Any
  function that accepts a raw `strike` argument could silently receive an off-grid value and
  produce an invalid order. A `Strike` value object with an `__post_init__` that validates
  alignment eliminates this class of error at construction time.
- `quantity: int` with no validation that it is a positive multiple of the current lot size.
  A `Quantity` or `LotCount` value object that knows the lot size at construction prevents
  a raw integer from representing half a lot.
- `expiry: date` with no validation that it is a valid NSE expiry Thursday (accounting for
  weekly/monthly transitions). An `ExpiryDate` value object that validates at construction
  means every downstream function that accepts `ExpiryDate` has a guarantee — it doesn't
  need to re-validate.
- `delta: float` used directly in strategy decisions without a domain wrapper. Delta has
  domain constraints (typically −1.0 to 1.0 for standard options; positive for calls,
  negative for puts). A `Delta` value object with range validation and sign convention
  makes strategy comparisons self-documenting: `leg.delta < Delta(-0.25)` is clearer
  and safer than `leg.delta < -0.25`.

**Note:** Do not gold-plate this. Wrap a concept in a value object only when:
(a) it has invariants (constraints that must always hold), or
(b) it is passed through 3+ functions and currently carries validation inline in each.
A `str` for `symbol` that is never validated and always trusted from the API is fine as a
primitive. A `strike` that must align to NSE grid and is computed from delta reconstruction
is not.

#### 9-B. Anti-Corruption Layer — Broker Jargon Must Not Leak into Core Logic

**The smell:** Upstox-specific field names, key strings, or response shapes appearing inside
`src/portfolio/`, `src/backtest/`, or `src/paper/` — modules that should speak the domain
language, not the broker's language.

**What to scan for:**
- `instrument_token`, `exchange_segment`, `trading_symbol` (raw Upstox API keys) referenced
  as dict keys or model fields inside strategy or portfolio modules. These belong only in
  `src/client/` (the translation layer). The rest of the system should use the project's own
  field names (`instrument_key`, `symbol`, `expiry`).
- Upstox response shapes (e.g., `response["data"]["Greeks"]["delta"]` path navigation)
  appearing outside a client or parser module. If the Upstox API restructures its response,
  the blast radius should be confined to one file, not scattered across modules.
- Any `if exchange == "NSE_FO": ...` branch in portfolio or strategy logic. Exchange routing
  is a broker concept; the domain only knows "this is an NSE options leg." The client layer
  translates domain intent into broker-specific exchange codes.
- `ltp` used as a variable name for values that have already been converted to the domain's
  `Decimal` price — at that point it is `price`, not `ltp`. `ltp` is the broker's term for
  last traded price; once it crosses into the domain model, use the domain term.

#### 9-C. Ubiquitous Language — Consistent Naming Across Code and Docs

The codebase and documentation (strategy specs, `CONTEXT.md`, `BACKTEST_PLAN.md`) should
use the same terms for the same concepts. Naming divergence is an early symptom of model
drift.

**What to scan for:**
- Terms used in the strategy spec (`csp_nifty_v1.md`) that map to different names in code.
  For example, if the spec calls it "entry premium" and the code calls it `credit_received`,
  one of them will drift when someone updates the spec without updating the code or vice versa.
- "Trade" vs "Position" vs "Leg" used interchangeably. The project has a specific meaning
  for each (`Leg` is a single option contract; `Trade` is a multi-leg structure; `Position`
  may refer to aggregated exposure). Any file that uses these terms loosely introduces
  ambiguity in code review and future changes.
- Greek names used inconsistently (`delta` vs `Δ` in comments, `gamma` vs `γ`). Pick one
  convention per context (code uses snake_case names; comments may use Greek letters only
  in formulas, not as variable name substitutes).

---

### Tier 10: Operational Safety — Resilience for a Hostile Environment

Trading systems run in a hostile environment: APIs timeout, rate limits are hit, data is
missing, crons fail silently. "Works on a good day" is not a passing bar. This tier reviews
whether the system **degrades gracefully** and **recovers correctly** after failures.

Severity: **ERROR** for any pattern that can cause a silent incorrect state in live positions;
**WARNING** for degradation gaps that cause missed alerts or data gaps but not wrong orders.

#### 10-A. Idempotency — Commands Must Be Safe to Retry

**The core question:** if the process crashes halfway through an operation and restarts,
does it produce a correct outcome, a duplicate, or a missed action?

**What to scan for:**
- **Order placement without idempotency check.** Any `place_order()` call that does not
  first check whether the order was already placed in the current session (e.g., by checking
  the audit log or order ID). A crash between "order sent" and "order confirmed" results in
  a duplicate order on restart. The correct pattern: write intent to an audit log *before*
  placing the order; on startup, check the log for in-flight orders before placing new ones.
- **`record_trade.py` without duplicate detection.** If the script is run twice for the same
  trade (user error, cron misfire), does it insert a duplicate `Leg` row or detect the
  collision? The `Leg` model should have a unique constraint on `(strategy_name, entry_date,
  instrument_key, action)` or equivalent that rejects the second insert.
- **EOD snapshot cron without "already ran today" check.** If the cron fires twice (DST edge
  case, manual trigger), does it overwrite today's snapshot file or append a second record
  to the SQLite table? The snapshot write must be idempotent: `INSERT OR REPLACE` with a
  date-keyed unique constraint, or a file-existence check before writing.
- **`daily_snapshot.py` P&L aggregation that double-counts.** If the script runs, fails
  mid-way, and re-runs, does the partial first run leave residue that inflates the second
  run's totals? The fix is transactional writes: all or nothing, never partial.

#### 10-B. Circuit Breakers and Graceful Degradation

**The core question:** if one external dependency (Upstox API, Telegram, NSE data source)
fails, does the rest of the system continue operating, or does the failure propagate?

**What to scan for:**
- **Missing Telegram failure isolation.** The non-fatal notification contract (Tier 2-C) is
  the first line of defence. The second line is: if `send()` is called in a tight loop (e.g.,
  alerting on each of 10 positions), a single 30-second Telegram timeout stalls the entire
  loop for 5 minutes. Wrap Telegram calls with an explicit short timeout (`asyncio.wait_for`,
  `aiohttp` timeout config) and a per-session call budget (e.g., no more than 5 alerts per
  minute). Excess alerts should be queued or dropped with a log entry, not blocking.
- **No retry budget on Upstox API calls.** `RateLimitError` and `DataFetchError` are marked
  retryable in the exception hierarchy. Scan for whether the retry is actually implemented
  with a budget (max N retries, exponential backoff) or whether it is unbounded (while True:
  retry). An unbounded retry on a 429 response will saturate the rate limit further, not
  resolve it.
- **Upstox API failure collapsing the entire snapshot run.** If `daily_snapshot.py` calls
  the API for 20 positions and position 7 returns a timeout, do positions 8–20 still get
  processed? The correct pattern is collect-errors-continue: accumulate failures, complete
  what is possible, alert on the failures at the end. An exception that propagates out of
  the loop leaves positions 8–20 with stale mark-to-market.
- **No fallback for missing LTP.** If the LTP fetch for a leg returns `None` or raises, what
  does the P&L computation do? Silently use the last known value? Use zero? Crash? Each of
  these is wrong in a different way. The correct behaviour is: mark the leg's LTP as
  `UNAVAILABLE`, exclude it from the total P&L, and flag it in the Telegram summary.
  "Unknown" is a valid state; "pretend we have data" is not.

#### 10-C. Audit Trail and State Recovery

**The core question:** after a crash or a bad run, can you reconstruct exactly what happened
and return to a known-good state?

**What to scan for:**
- **No `git_commit` / `run_timestamp` in backtest results.** Covered in Tier 2-D but
  repeated here because it is also a recovery concern: if a backtest run produces a bad
  result, you must be able to reproduce the exact conditions. Without lineage metadata,
  "re-run with identical inputs" is not achievable.
- **Mutable state in the `PortfolioStore` with no write-ahead log.** If the store updates a
  position and the process crashes mid-update, is the SQLite DB left in a consistent state?
  SQLite in WAL mode (which `db.py` should configure) provides crash safety for individual
  writes. Check that WAL mode is explicitly enabled in `src/db.py` and that all multi-step
  updates (e.g., close one leg, open another) are wrapped in a single transaction — not in
  separate `commit()` calls.
- **Scripts that mutate state without logging the intent first.** The safest pattern for
  irreversible operations (close a leg, record a roll): write a log entry describing the
  intent *before* executing, and another entry marking completion *after*. On restart, the
  system can detect orphaned intents and either complete or roll back. Without this,
  a script that crashes after mutation but before completion leaves the DB in a state that
  has no audit trail.
- **No operator-visible "last successful run" indicator.** The `2.1a` cron healthcheck is
  planned but may not exist yet. If it doesn't, flag as **WARNING**: there is currently no
  mechanism to detect a silent cron failure until a human notices stale data. The healthcheck
  is not a nice-to-have for a solo operator — it is the only failsafe.

---

## Output Format

Do not bucket findings by severity. Instead, output a **single flat list ordered from
smallest impact to largest impact**. Each entry:

```
[N] <impact-label> | <file>:<line> | <one-sentence issue> | Fix: <concrete action>
```

Impact labels (for ordering reference, not bucketing):
- `style` — cosmetic, zero behavioral risk
- `contract` — type hint / docstring gap, affects maintainability
- `hygiene` — Pythonic pattern issue, low crash risk
- `async` — event loop correctness, crash risk under load
- `protocol` — BrokerClient or notification contract violation
- `financial` — Decimal, STT, lot size, VWAP/LTP: wrong money calculations
- `data-loss` — reproducibility gap, silent data corruption, injection risk

End with a one-paragraph verdict: is the codebase safe to run live? What is the single
highest-leverage fix to make first?
