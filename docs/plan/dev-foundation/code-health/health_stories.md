# code-health — Story Specs

> One task per session. Find the first unchecked item in `health_tasks.md`.
> After each task: tick `health_tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

---

## CH-1 — Duplicate code scan

**Owner:** Claude
**Files to create:**
- `docs/plan/dev-foundation/code-health/duplication_report.md`

**What to do:**
Run `pylint --disable=all --enable=similarities --min-similarity-lines=6 src/` and capture
output. Also run `jscpd src/ --min-lines 6 --reporters console` if jscpd is available.

Classify findings into three buckets in the report:
1. **Extract to shared helper** — identical logic in 2+ modules (e.g., `Decimal(str(v))` coercion, Telegram formatting patterns)
2. **Acceptable duplication** — structurally similar but contextually distinct (e.g., two `parse_*` functions that happen to have the same shape)
3. **Already abstracted** — false positive, already using shared function

Do not fix anything in this task. The report is the deliverable.

**Commit message:**
```
docs(dev-foundation): add duplication scan report

Why: baseline before Phase 1 — don't carry dead weight forward
What:
- code-health/duplication_report.md: pylint similarity findings, classified
Ref: dev-foundation/code-health CH-1
```

---

## CH-2 — Dead code scan

**Owner:** Claude
**Files to create:**
- `docs/plan/dev-foundation/code-health/dead_code_report.md`

**What to do:**
Run `vulture src/ scripts/ --min-confidence 80` and capture output.

Classify findings:
1. **Safe to delete** — clearly unused, no external callers
2. **Needs investigation** — may be called dynamically or by scripts not in scope
3. **False positive** — used via protocol, `__all__`, or dynamic dispatch

Add a whitelist section: `vulture` whitelists go in `vulture_whitelist.py` at repo root
(standard vulture convention). Do not create it yet — just note candidates.

**Commit message:**
```
docs(dev-foundation): add dead code scan report

Why: identify cleanup targets before Phase 1 expands the codebase
What:
- code-health/dead_code_report.md: vulture findings, classified
Ref: dev-foundation/code-health CH-2
```

---

## CH-3 — `GLOSSARY.md`

**Owner:** Claude
**Files to create:**
- `GLOSSARY.md` — repo root

**What to implement:**

A single-source-of-truth for domain terms used across all docs and AI sessions. Covers
both trading domain and project-specific conventions. Target ~40 entries.

Categories to cover:
- **Options trading:** CE/PE, ATM/OTM/ITM/DITM, DTE, IVR, IV, Delta, Gamma, Theta, Vega,
  lot size (65 for NIFTY), underlying, expiry (weekly/monthly/quarterly/yearly)
- **Strategies:** overlay, protective put (PP), covered call (CC), collar, iron condor,
  strangle, short strangle, cash-secured put (CSP), delta-neutral
- **Project-specific:** paper_ prefix convention, BUY-opened vs SELL-opened position,
  track (A/B/C), roll (close old leg + open new leg atomically), overlay vs base leg,
  leg_role, strategy_name (DB convention), BOD (beginning of day), instrument_key format
- **Data conventions:** Decimal-as-TEXT, UTC storage/IST display, IVR threshold bands
  (< 0.25 low-vol, 0.25–0.50 in-window, > 0.50 high-vol), lot size, LOT_SIZE=65

Format:
```markdown
## <Term>
**Category:** Trading | Project | Data
**Definition:** One sentence.
**Example / note:** Optional clarification or cross-reference.
```

**Commit message:**
```
docs(root): add GLOSSARY.md with ~40 domain and project terms

Why: eliminates per-session re-derivation of domain context; reduces AI token overhead
What:
- GLOSSARY.md: trading terms + project conventions + data layer rules
Ref: dev-foundation/code-health CH-3
```

---

## CH-4 — `__all__` in all `src/` `__init__.py` files

**Owner:** Antigravity

**Before any code:** Run `search_code("__all__")` across `src/` to identify which
`__init__.py` files already have it. Run `search_graph("__init__")` to get the list of
all package init files. Do not use `Read` on individual files until you have the full list.

**What to implement:**

For each `src/<module>/__init__.py`, add an `__all__` list that explicitly names every
public symbol re-exported from that package. A symbol is public if it does not start with `_`.

Rules:
- Empty `__init__.py` (just a package marker comment) → add `__all__: list[str] = []`
- `__init__.py` that re-exports from submodules → list those exports in `__all__`
- Do not change any import structure — only add the `__all__` declaration

**Verify:** `python -c "import src; print('ok')"` must not raise. Run full test suite.

**Commit message:**
```
refactor(src): add __all__ to all package __init__.py files

Why: defines public API surface explicitly; enables accurate graph queries
What:
- src/*/___init__.py: __all__ declarations added
Ref: dev-foundation/code-health CH-4
```

---

## CH-5 — Mermaid C4 architecture diagram

**Owner:** Claude
**Files to create:**
- `docs/architecture.md`

**What to implement:**

A C4 Container diagram (level 2) showing all `src/` modules, their dependencies, and
data stores. Rendered as a Mermaid `graph TD` block (GitHub renders natively).

Cover:
- All modules in `src/` as boxes with one-line descriptions
- Arrows showing key dependencies (e.g., `scripts/` → `src/client/` → Upstox API)
- Data stores: `portfolio.sqlite`, Parquet files, AMFI flat file
- External systems: Upstox API, Telegram, NSE, AMFI, Nuvama SDK, Dhan API

This diagram should answer the question "what calls what?" without reading CONTEXT_TREE.md.

**Commit message:**
```
docs(architecture): add Mermaid C4 container diagram

Why: replaces reading CONTEXT_TREE.md for structural orientation — ~1800 tokens → ~40
What:
- docs/architecture.md: Mermaid graph TD covering all src/ modules and data flows
Ref: dev-foundation/code-health CH-5
```

---

## CH-6 — `src/utils/logging.py` + `setup_logging()`

**Owner:** Antigravity

**Before any code:** Run `search_code("logging")` and `search_code("structlog")` across
`src/` and `scripts/` to understand current logging state. Run `search_graph("setup_logging")`
to confirm it does not exist yet.

**What to implement:**

`src/utils/logging.py`:
```python
import logging
import sys
import structlog

def setup_logging(*, json: bool = False, level: str = "INFO") -> None:
    """Configure structlog for the application.

    Args:
        json: If True, emit JSON (production). If False, emit coloured console (dev).
        level: Log level string. Defaults to INFO.
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if json:
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        shared_processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
    )
```

Wire `setup_logging()` into the top of each script in `scripts/` (after imports, before
any logic). Use `json=True` when `UPSTOX_ENV == "prod"`.

**Tests:** Two tests in `tests/unit/utils/test_logging.py`:
1. `setup_logging(json=False)` runs without error
2. `setup_logging(json=True)` runs without error

**Commit message:**
```
feat(utils): add setup_logging() with structlog JSON/console modes

Why: implements stated CLAUDE.md standard — structured JSON in prod, console in dev
What:
- src/utils/logging.py: setup_logging() with json/level params
- tests/unit/utils/test_logging.py: 2 smoke tests
- scripts/*.py: setup_logging() wired at entry point
Ref: dev-foundation/code-health CH-6
```

---

## CH-7a — Define `Settings` model

**Owner:** Claude
**Files to create:**
- `src/config.py`

**What to implement:**

Run `search_code("os.getenv")` and `search_code("os.environ")` across `src/` and `scripts/`
to enumerate every env var used. Map them into a `pydantic-settings` `Settings` class.

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Upstox
    upstox_env: str = Field(default="test", pattern="^(prod|sandbox|test)$")
    upstox_analytics_token: str | None = None
    upstox_access_token: str | None = None
    upstox_sandbox_token: str | None = None
    upstox_debug: bool = False

    # Telegram
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # Nuvama
    nuvama_settings_file: str | None = None

    # Dhan
    dhan_client_id: str | None = None
    dhan_access_token: str | None = None

    # Data paths
    vix_data_dir: str = "data/historical/ohlc/india_vix"

settings = Settings()  # singleton — import this, not os.getenv()
```

This task is **definition only**. CH-7b replaces all `os.getenv()` calls.

**Tests:** `tests/unit/test_config.py`:
1. `Settings()` with no env vars — optional fields are None, defaults are correct
2. `Settings()` with `UPSTOX_ENV=prod` — `upstox_env == "prod"`
3. `Settings(upstox_env="invalid")` — raises `ValidationError`

**Commit message:**
```
feat(src): add pydantic-settings Settings model in src/config.py

Why: validates all env vars at startup; replaces scattered os.getenv() calls
What:
- src/config.py: Settings(BaseSettings) with all env vars mapped + validated
- tests/unit/test_config.py: 3 tests
Ref: dev-foundation/code-health CH-7a
```

---

## CH-7b — Replace `os.getenv()` calls with `Settings`

**Owner:** Antigravity

**Before any code:** Run `search_code("os.getenv")` across `scripts/` and `src/` to get
the full list. Do not read files blindly — use the grep output to target only affected files.

**What to implement:**

In each file that calls `os.getenv("SOME_VAR")`:
- Add `from src.config import settings` at the top
- Replace `os.getenv("UPSTOX_ANALYTICS_TOKEN")` with `settings.upstox_analytics_token`
- Replace `os.getenv("UPSTOX_ENV", "test")` with `settings.upstox_env`
- Etc.

Do not change any logic — pure mechanical substitution.

**Verify:** Full test suite must stay green. `python -c "from src.config import settings; print(settings.upstox_env)"` must print `test`.

**Commit message:**
```
refactor(src,scripts): replace os.getenv() calls with Settings singleton

Why: single validation point at startup; removes silent missing-credential failures
What:
- src/*/: os.getenv() → settings.* (N files)
- scripts/*/: os.getenv() → settings.* (N files)
Ref: dev-foundation/code-health CH-7b
```

---

## CH-8 — `scripts/healthcheck.py`

**Owner:** Antigravity

**What to implement:**

A standalone script that validates system health and sends a Telegram alert if anything
is wrong. Intended to run as a cron at 16:30 IST on trading days.

Checks (in order):
1. **Trading day guard** — `is_trading_day(today)` — exit 0 silently on holidays
2. **DB accessible** — `src/db.py` connect() succeeds
3. **Snapshot recency** — query `daily_snapshots` for today's date; alert if missing
4. **Paper snapshot recency** — query `paper_nav_snapshots` for today; warn if missing
5. **VIX data recency** — check latest file in `data/historical/ohlc/india_vix/` — warn if > 2 days stale
6. **Disk space** — warn if `data/` partition < 500 MB free

Alert format (Telegram):
```
⚠️ NiftyShield Healthcheck — YYYY-MM-DD 16:30 IST
❌ daily_snapshots: no row for today
✅ paper_nav_snapshots: ok
✅ DB: accessible
⚠️ VIX data: 3 days stale
```

If all checks pass, no Telegram message is sent (silent success). Exit 0 on success, 1 on
any failure.

**Tests:** `tests/unit/test_healthcheck.py`:
1. All checks pass — no alert sent, exit 0
2. Missing daily snapshot — alert triggered
3. Non-trading day — all checks skipped, exit 0

**Cron entry** (add to `TODOS.md` as a follow-up action item):
```
30 16 * * 1-5  python /path/to/scripts/healthcheck.py
```

**Commit message:**
```
feat(scripts): add healthcheck.py dead man's switch for cron validation

Why: silent cron failure is the highest-risk operational gap for a trading system
What:
- scripts/healthcheck.py: 6 checks, Telegram alert on failure, silent on pass
- tests/unit/test_healthcheck.py: 3 tests
Ref: dev-foundation/code-health CH-8
```

---

## CH-9a — Design `hypothesis` edge cases

**Owner:** Claude

**What to produce:**
A design document at `docs/plan/dev-foundation/code-health/hypothesis_design.md` specifying
the exact `@given` strategies and assertions for each target function. Antigravity implements
from this spec in CH-9b — no ambiguity allowed.

**Targets:**

1. **`compute_ivr(vix_today, vix_series)`** in `src/backtest/ivr.py`
   - Edge cases: empty series, single-element series, all-same values, vix_today outside range, negative values, NaN
   - Invariants: result always in [0.0, 1.0] or None; flat window → 0.5

2. **`aggregate_delta(paper_positions, nifty_spot, lot_size)`** in `src/risk/delta_tracker.py`
   - Edge cases: empty positions, all CE, all PE, mixed, zero lot_size, zero nifty_spot
   - Invariants: CE adds positive delta, PE adds negative; total = options + niftybees

3. **P&L arithmetic in `PaperTracker.compute_pnl()`**
   - Edge cases: all positions closed, single open position, zero net qty
   - Invariants: total_pnl = unrealized + realized; never float (always Decimal)

**Commit message:**
```
docs(dev-foundation): add hypothesis test design for financial math functions

Why: adversarial input generation finds edge cases hand-written tests miss
What:
- code-health/hypothesis_design.md: @given strategies + invariants for 3 targets
Ref: dev-foundation/code-health CH-9a
```

---

## CH-9b — Implement `@given` tests

**Owner:** Antigravity

**Before any code:** Read `docs/plan/dev-foundation/code-health/hypothesis_design.md`
in full. Then run `get_code_snippet("compute_ivr")`, `get_code_snippet("aggregate_delta")`
to get exact current signatures. Do not write test helpers from memory.

**Files to create:**
- `tests/unit/backtest/test_ivr_hypothesis.py`
- `tests/unit/risk/test_delta_hypothesis.py`
- `tests/unit/paper/test_pnl_hypothesis.py`

Implement exactly the strategies and assertions specified in `hypothesis_design.md`.
No additions. No departures from spec.

**Commit message:**
```
test(backtest,risk,paper): add hypothesis property-based tests for financial math

Why: adversarial inputs validate invariants hand-written tests cannot cover
What:
- tests/unit/backtest/test_ivr_hypothesis.py
- tests/unit/risk/test_delta_hypothesis.py
- tests/unit/paper/test_pnl_hypothesis.py
Ref: dev-foundation/code-health CH-9b
```

---

## CH-10 — Docs close

**Owner:** Claude
**Files to change:**
- `CONTEXT.md` — add entries for `src/config.py`, `src/utils/logging.py`, `scripts/healthcheck.py`; update test count
- `DECISIONS.md` — add: pydantic-settings singleton pattern, structlog choice, hypothesis on financial math
- `TODOS.md` — mark code-health complete, session log, add healthcheck cron as follow-up action
