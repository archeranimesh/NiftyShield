# Scripts Restructure — Design & Story Specs

> Status: **SR0 closed 2026-05-29** — scripts/ layout finalised.
> **SS0 closed 2026-05-29** — src/ audit complete; SS1–SS5 stories ready.
> Implementation starts at SR1 / SS1 (cron-sensitive moves post-market only).
> Full implementation rules in `CLAUDE.md`, `REVIEW.md`, and `prompt.md`.

---

## Background

`scripts/` has 36 files in a flat layout. As strategies and infra have grown, three distinct
functional roles have emerged. The flat layout makes it impossible to reason about which scripts
are shared infrastructure vs strategy-specific vs one-off tooling.

---

## Classification Axes (apply to every new script, forever)

Before placing a new script, answer these three questions in order:

**1. Is it shared — called by more than one strategy or daemon?**
→ Yes: it belongs in `pipeline/`, `lookup/`, or `record/` (see below).
→ No: it belongs in `strategies/<name>/` or a domain folder.

**2. If shared, what is its runtime model?**

| Runtime model | Folder | Examples |
|---|---|---|
| Cron-driven, produces data or snapshots | `pipeline/` | chain snapshots, gamma watch, bhavcopy ingest |
| On-demand query, called by humans or entry scripts | `lookup/` | find_strike_by_delta, instrument_lookup |
| Human-facing CLI that writes to DB (called once per action) | `record/` | record_paper_trade, record_trade |

**3. If strategy-specific, which strategy owns it?**
→ Goes into `strategies/<strategy-name>/`. One subfolder per strategy, permanently.

**Supporting categories (non-strategy, non-shared):**

| Folder | Contents |
|---|---|
| `portfolio/` | Live portfolio P&L crons and snapshot scripts |
| `intraday/` | Intraday position monitoring crons |
| `seed/` | One-time DB seed scripts — never in cron |
| `council/` | Council workflow tooling + templates — used during planning, not trading |
| `dev/` | Diagnostics, smoke tests, one-off migrations — throwaway or rarely run |

---

## Migration Principle

**New scripts:** Land in the correct folder immediately. No exceptions.
**Existing scripts:** Move folder-by-folder, one commit per folder, only when there is an
adjacent reason to touch that area. No big-bang refactor.
**Cron-sensitive moves (SR7, SR8):** Do post-market only. Update crontab in the same commit.

---

## Final Directory Layout

```
scripts/
├── __init__.py
│
├── pipeline/               # cron-driven; produces data or snapshots; shared across strategies
│   ├── __init__.py
│   ├── upstox_chain_snapshot.py    # EOD option chain → Parquet
│   ├── upstox_chain_intraday.py    # 5-min intraday chain → Parquet
│   ├── gamma_daily_watch.py        # Greeks monitoring from chain snapshots
│   └── bhavcopy_bootstrap.py       # NSE bhavcopy bulk ingest
│
├── lookup/                 # on-demand queries; called by humans or entry scripts
│   ├── __init__.py
│   ├── find_strike_by_delta.py     # live chain → filter by delta range
│   ├── find_overlay_strikes.py     # overlay-specific strike finder
│   └── instrument_lookup.py        # BOD JSON instrument key resolver
│
├── record/                 # human-facing write CLIs; one action per invocation
│   ├── __init__.py
│   ├── record_paper_trade.py       # entry/close for any paper strategy
│   └── record_trade.py             # live trade recording
│
├── strategies/             # strategy-specific scripts; one subfolder per strategy
│   ├── __init__.py
│   ├── csp/
│   │   ├── __init__.py
│   │   └── paper_csp_roll.py       # profit-target / time-stop / delta-stop exit
│   ├── three_track/
│   │   ├── __init__.py
│   │   ├── paper_3track_entry.py
│   │   ├── paper_3track_overlay.py
│   │   ├── paper_3track_overlay_entry.py
│   │   ├── paper_3track_overlay_roll.py
│   │   └── paper_3track_snapshot.py    # EOD cron — mark-to-market for 3 tracks
│   └── cc_calibration/             # NiftyBees lot-sizing probe (retire after 3 cycles)
│       ├── __init__.py
│       ├── paper_cc_entry.py
│       └── paper_cc_roll.py            # CC3 — not yet built
│
├── portfolio/              # live portfolio P&L — not paper, not strategy-specific
│   ├── __init__.py
│   ├── daily_snapshot.py           # EOD portfolio snapshot cron
│   ├── morning_nav.py              # pre-market NAV fetch
│   ├── paper_snapshot.py           # paper mark-to-market (standalone, non-3track)
│   └── roll_leg.py                 # live leg roll CLI
│
├── intraday/               # intraday monitoring crons (*/15 9-15 * * 1-5)
│   ├── __init__.py
│   ├── intraday_tracker.py         # combined Dhan+Nuvama orchestrator
│   ├── nuvama_intraday_tracker.py
│   └── dhan_intraday_tracker.py
│
├── seed/                   # one-time DB seeds; never in cron
│   ├── __init__.py
│   ├── seed_mf_holdings.py
│   ├── seed_nuvama_positions.py
│   ├── seed_portfolio.py
│   └── seed_trades.py
│
├── council/                # council workflow tooling; used during planning, not trading
│   ├── __init__.py
│   ├── ask_council.py
│   └── council_templates/
│
└── dev/                    # diagnostics, smoke tests, one-off migrations
    ├── __init__.py
    ├── send_test_telegram.py       # Telegram token/chat-id smoke test
    ├── validate_strategy_spec.py   # strategy spec linter
    ├── probe_nuvama_schema.py
    ├── migrate_strike_to_text.py
    ├── test_api_version.py
    └── paper_track_snapshot.py     # confirm superseded before moving (see SR0 below)
```

---

## SR0 — Open Questions (resolved 2026-05-29)

1. **`paper_track_snapshot.py`** — move to `dev/` pending confirmation it is superseded
   by `paper_3track_snapshot.py`. Confirm with `git log` + crontab before SR5.

2. **Cron path strategy** — clean cut per folder. Update crontab in the same commit as
   each folder move. No shim re-exports.

3. **`find_overlay_strikes.py` vs `find_strike_by_delta.py`** — both active; both go into
   `lookup/`. Overlap audit deferred to SR6 — resolve before moving.

4. **`paper_3track_overlay.py` vs `paper_3track_overlay_entry.py`** — both active. Confirm
   with `git log` before SR8. Move both.

5. **`src/` → `scripts/` imports** — `grep -r "from scripts\." src/` must return zero before
   any move. Run this check at SR1.

6. **`validate_strategy_spec.py`** — goes into `dev/` (not `council/`). It is a linting tool,
   not a workflow gate.

---

## Story Specs

---

### SR1 — Scaffold new directories + `__init__.py` files

**Files to create** (one `__init__.py` per directory, content: `# <package name>`):
```
scripts/pipeline/__init__.py
scripts/lookup/__init__.py
scripts/record/__init__.py
scripts/strategies/__init__.py
scripts/strategies/csp/__init__.py
scripts/strategies/three_track/__init__.py
scripts/strategies/cc_calibration/__init__.py
scripts/portfolio/__init__.py
scripts/intraday/__init__.py
scripts/seed/__init__.py
scripts/council/__init__.py
scripts/dev/__init__.py
```

**Before any code:**
- `grep -r "from scripts\." src/` — must return zero. If not, stop and report.
- `crontab -l` — save current cron state for reference throughout this task.

No file moves in SR1. Scaffold only.

**After:** `mcp__codebase-memory-mcp__index_repository` — re-index so graph sees new packages.

**Test gate:** `python -m pytest tests/unit/ --tb=no -q` — all green.

**Commit:** `chore(scripts): scaffold subdirectory structure with __init__.py files`

---

### SR2 — Move `pipeline/` scripts (chain + gamma + bhavcopy)

**Before any move:**
- `crontab -l | grep -E "chain|gamma|bhavcopy"` — note exact entries.
- `grep -r "upstox_chain\|gamma_daily\|bhavcopy" scripts/ src/` — find all callers.

**Files to move:**
- `scripts/upstox_chain_snapshot.py` → `scripts/pipeline/upstox_chain_snapshot.py`
- `scripts/upstox_chain_intraday.py` → `scripts/pipeline/upstox_chain_intraday.py`
- `scripts/gamma_daily_watch.py` → `scripts/pipeline/gamma_daily_watch.py`
- `scripts/bhavcopy_bootstrap.py` → `scripts/pipeline/bhavcopy_bootstrap.py`

Update cron entries in same commit.

**Test gate:** Full suite green.

**Commit:** `refactor(scripts): move pipeline scripts into scripts/pipeline/`

---

### SR3 — Move `lookup/` scripts

**Before any move:**
- `crontab -l | grep -E "find_strike|find_overlay|instrument_lookup"` — expect zero or minimal.
- `grep -r "find_strike_by_delta\|find_overlay\|instrument_lookup" scripts/ src/` — callers.
- Resolve SR0 question #3: confirm `find_overlay_strikes.py` and `find_strike_by_delta.py`
  are both active and non-overlapping before moving both.

**Files to move:**
- `scripts/find_strike_by_delta.py` → `scripts/lookup/find_strike_by_delta.py`
- `scripts/find_overlay_strikes.py` → `scripts/lookup/find_overlay_strikes.py`
- `scripts/instrument_lookup.py` → `scripts/lookup/instrument_lookup.py`

**Test gate:** Full suite green.

**Commit:** `refactor(scripts): move lookup scripts into scripts/lookup/`

---

### SR4 — Move `record/` scripts

**Before any move:**
- `crontab -l | grep -E "record_paper|record_trade"` — expect zero (human-invoked).
- `grep -r "record_paper_trade\|record_trade" scripts/ src/` — high caller count expected;
  update every reference in the same commit.

**Files to move:**
- `scripts/record_paper_trade.py` → `scripts/record/record_paper_trade.py`
- `scripts/record_trade.py` → `scripts/record/record_trade.py`

**Test gate:** Full suite green.

**Commit:** `refactor(scripts): move record CLIs into scripts/record/`

---

### SR5 — Move `seed/` and `dev/` scripts

**seed/ — no cron, no callers in src/:**
- `scripts/seed_mf_holdings.py` → `scripts/seed/seed_mf_holdings.py`
- `scripts/seed_nuvama_positions.py` → `scripts/seed/seed_nuvama_positions.py`
- `scripts/seed_portfolio.py` → `scripts/seed/seed_portfolio.py`
- `scripts/seed_trades.py` → `scripts/seed/seed_trades.py`

**dev/:**
- Resolve SR0 question #1: `git log --oneline -5 scripts/paper_track_snapshot.py` + check
  crontab. Delete if superseded; move to `dev/` if still referenced anywhere.
- `scripts/send_test_telegram.py` → `scripts/dev/send_test_telegram.py`
- `scripts/validate_strategy_spec.py` → `scripts/dev/validate_strategy_spec.py`
- `scripts/probe_nuvama_schema.py` → `scripts/dev/probe_nuvama_schema.py`
- `scripts/migrate_strike_to_text.py` → `scripts/dev/migrate_strike_to_text.py`
- `scripts/test_api_version.py` → `scripts/dev/test_api_version.py`

**Test gate:** Full suite green.

**Commit:** `refactor(scripts): move seed and dev scripts into scripts/seed/ and scripts/dev/`

---

### SR6 — Move `council/` scripts

**Files to move:**
- `scripts/ask_council.py` → `scripts/council/ask_council.py`
- `scripts/council_templates/` → `scripts/council/council_templates/`

**Test gate:** Full suite green.

**Commit:** `refactor(scripts): move council tooling into scripts/council/`

---

### SR7 — Move `intraday/` scripts

**High cron sensitivity — do post-market (Friday evening preferred).**

**Before any move:**
- `crontab -l | grep intraday` — note all three cron entries precisely.
- Smoke test new path before updating cron:
  `python -m scripts.intraday.intraday_tracker --help`

**Files to move:**
- `scripts/intraday_tracker.py` → `scripts/intraday/intraday_tracker.py`
- `scripts/nuvama_intraday_tracker.py` → `scripts/intraday/nuvama_intraday_tracker.py`
- `scripts/dhan_intraday_tracker.py` → `scripts/intraday/dhan_intraday_tracker.py`

Update cron in same commit.

**Test gate:** Full suite green. Smoke: `python -m scripts.intraday.intraday_tracker --dry-run`.

**Commit:** `refactor(scripts): move intraday tracker scripts into scripts/intraday/`

---

### SR8 — Move `strategies/three_track/` scripts

**High cron sensitivity — do post-market. `paper_3track_snapshot.py` is the canonical EOD cron.**

**Before any move:**
- `crontab -l | grep 3track` — note all entries.
- Resolve SR0 question #4: `git log --oneline -5 scripts/paper_3track_overlay.py` and
  `scripts/paper_3track_overlay_entry.py` — confirm both active.

**Files to move:**
- `scripts/paper_3track_entry.py` → `scripts/strategies/three_track/paper_3track_entry.py`
- `scripts/paper_3track_overlay.py` → `scripts/strategies/three_track/paper_3track_overlay.py`
- `scripts/paper_3track_overlay_entry.py` → `scripts/strategies/three_track/paper_3track_overlay_entry.py`
- `scripts/paper_3track_overlay_roll.py` → `scripts/strategies/three_track/paper_3track_overlay_roll.py`
- `scripts/paper_3track_snapshot.py` → `scripts/strategies/three_track/paper_3track_snapshot.py`

Update cron in same commit.

**Test gate:** Full suite green. Smoke: `python -m scripts.strategies.three_track.paper_3track_snapshot --no-save`.

**Commit:** `refactor(scripts): move 3-track strategy scripts into scripts/strategies/three_track/`

---

### SR9 — Move `strategies/csp/` and `strategies/cc_calibration/` scripts

**Before any move:**
- `crontab -l | grep -E "paper_csp|paper_cc"` — note entries.

**Files to move:**
- `scripts/paper_csp_roll.py` → `scripts/strategies/csp/paper_csp_roll.py`
- `scripts/paper_cc_entry.py` → `scripts/strategies/cc_calibration/paper_cc_entry.py`
- `scripts/paper_cc_roll.py` → `scripts/strategies/cc_calibration/paper_cc_roll.py`
  (move once CC3 is built)

**Test gate:** Full suite green.

**Commit:** `refactor(scripts): move csp and cc_calibration strategy scripts`

---

### SR10 — Move `portfolio/` scripts

**Before any move:**
- `crontab -l | grep -E "daily_snapshot|morning_nav|paper_snapshot|roll_leg"` — note entries.
- `grep -r "roll_leg\|daily_snapshot\|morning_nav\|paper_snapshot" scripts/ src/` — callers.

**Files to move:**
- `scripts/daily_snapshot.py` → `scripts/portfolio/daily_snapshot.py`
- `scripts/morning_nav.py` → `scripts/portfolio/morning_nav.py`
- `scripts/paper_snapshot.py` → `scripts/portfolio/paper_snapshot.py`
- `scripts/roll_leg.py` → `scripts/portfolio/roll_leg.py`

Update cron in same commit.

**Test gate:** Full suite green.

**Commit:** `refactor(scripts): move portfolio scripts into scripts/portfolio/`

---

### SR11 — Docs close

**Files to change** (targeted `Edit` only):
- `CONTEXT.md` — update scripts block to reflect new paths and folder taxonomy
- `DECISIONS.md` — one entry: pipeline/lookup/record axis decision + rationale
- `TODOS.md` — session log entry + mark scripts-restructure complete in build queue

**DECISIONS.md entry:**
```
| 2026-05-29 | scripts/ restructured from flat layout into functional axis:
  pipeline/ (cron, produces data), lookup/ (on-demand query), record/ (human write CLI),
  strategies/<name>/ (strategy-specific), plus portfolio/, intraday/, seed/, council/, dev/.
  Axis chosen because paper-backbone daemon and future strategies need to distinguish
  shared infra from strategy-owned scripts. New scripts must be classified by this axis
  before placement. | scripts-restructure |
```

**Commit:** `docs(scripts): update CONTEXT.md and DECISIONS.md for restructured scripts layout`

---

---

## `src/` Structure Stories (SS series)

> **Governing principle:** `src/` is the importable library package. The rule is simple:
> *anything you wouldn't ship in a `pip install` doesn't belong in `src/`.*
> Exploratory scripts, dev diagnostics, and test files are not library code.

---

### SS0 — Audit (closed 2026-05-29)

Full audit of `src/` against the above principle. Five issues identified:

1. `src/analytics/` and `src/sandbox/` — exploratory, non-importable; belong in `scripts/dev/`
2. `test_*.py` files inside `src/` — misnamed vs CONTEXT_TREE; picked up by pytest if run from root
3. Five files undocumented in CONTEXT_TREE: `src/backtest/{bhavcopy_loader.py,constants.py}`,
   `src/dhan/positions.py`, `src/portfolio/service.py`, `src/intraday/market_store.py`;
   plus `src/nuvama/mock_client.py` whose CONTEXT_TREE entry is stale (says it's in `protocol.py`)
4. `src/portfolio/service.py` — `SnapshotService` adds no protocol boundary over `PortfolioStore`;
   may be a dead layer; needs an import audit before deciding fold vs keep
5. `src/gamma/` and `src/nuvama/` missing CLAUDE.md; model placement convention never documented

---

### SS1 — Evict exploratory code from `src/`

**What and why:**
`src/analytics/` and `src/sandbox/` are not importable modules — they exist for manual exploration
and API probing. Keeping them in `src/` means codebase-memory-mcp indexes them as library code,
and `python -m pytest` (without `tests/unit/` scoped) collects the `test_*.py` files inside them.

**Before any move:**
- `grep -r "from src.analytics\|from src.sandbox\|import src.analytics\|import src.sandbox" .` — must return zero. If any caller exists, remove the import first.
- `crontab -l | grep -E "analytics|sandbox"` — expect zero.
- Confirm target exists: `scripts/dev/` is created in SR5. SS1 must run after SR5.

**Files to move:**
- `src/analytics/test_analytics_apis.py` → `scripts/dev/verify_analytics.py`
  (rename: drop `test_` prefix; align with CONTEXT_TREE documented name `verify_analytics.py`)
- `src/analytics/__init__.py` — delete after move (empty package gone)
- `src/analytics/` directory — remove once empty
- `src/sandbox/test_sandbox_order_lifecycle.py` → `scripts/dev/sandbox_order_lifecycle.py`
  (rename: drop `test_` prefix; align with CONTEXT_TREE documented name `order_lifecycle.py`)
- `src/sandbox/__init__.py` — delete after move
- `src/sandbox/` directory — remove once empty

**Test gate:** `python -m pytest tests/unit/ --tb=no -q` — all green.

**Commit:** `refactor(src): move exploratory scripts out of src/ into scripts/dev/`

---

### SS2 — Document the five undocumented src/ files

**What and why:**
Five files exist in `src/` that are not in CONTEXT_TREE.md — the authoritative module index.
One additional entry (`src/nuvama/mock_client.py`) exists on disk but CONTEXT_TREE wrongly says
`MockNuvamaClient` lives in `protocol.py`. No code changes in this task — documentation only.

**Files to document in CONTEXT_TREE.md (targeted `Edit` calls, one per module):**

1. `src/backtest/constants.py` — add entry: `constants.py — DEFAULT_DATA_DIR path constant; `_ROOT`-relative path to `data/offline/options_ohlcv/`; imported by `bhavcopy_loader.py`.`
2. `src/backtest/bhavcopy_loader.py` — add entry: `bhavcopy_loader.py — `load_options_ohlcv(underlying, start, end, data_dir, columns)`: reads options OHLCV Parquet from `DEFAULT_DATA_DIR`; returns `pd.DataFrame`; used by backtest engine.`
3. `src/dhan/positions.py` — add entry: `positions.py — Pure Dhan intraday options position parsing and formatting. `fetch_positions_raw` / `fetch_fund_limit_raw` (I/O). All parsers are pure functions. Decimal(str(v)) rule enforced. Maps Dhan's `availabelBalance` typo explicitly.`
4. `src/portfolio/service.py` — add entry: `service.py — `SnapshotService`: thin orchestration wrapper around `PortfolioStore` for daily snapshot persistence. No protocol boundary; under review (see SS3).`
5. `src/intraday/market_store.py` — add entry after confirming what it does (run `head -40` before writing).
6. `src/nuvama/mock_client.py` — fix stale CONTEXT_TREE entry in `protocol.py` description: remove "MockNuvamaClient provides offline testing (AR-9)" from `protocol.py` line; add separate `mock_client.py` entry: `mock_client.py — `MockNuvamaClient`: offline NuvamaClient implementation for unit tests (AR-9). Implements `protocol.NuvamaClient`.`

**Before editing:** `head -40 src/intraday/market_store.py` — read actual content before writing the description.

**No code changes. No test gate needed (docs only).**

**Commit:** `docs(src): add missing CONTEXT_TREE entries for 5 undocumented files; fix nuvama mock_client entry`

---

### SS3 — Audit and resolve `src/portfolio/service.py` and `src/intraday/market_store.py`

**What and why:**
Two modules have unclear ownership and no tests. Before deciding to keep or delete each,
run an import audit and confirm whether any production path uses them.

**Audit steps (run before any code change):**

For `src/portfolio/service.py`:
```bash
grep -r "from src.portfolio.service\|from src.portfolio import service\|portfolio\.service" . --include="*.py"
```
- If zero callers → delete the file; it's a dead layer that contradicts the tracker.py orchestration.
- If callers exist → elevate: add a `SnapshotServiceProtocol` to `protocol.py` or merge the logic into `tracker.py`.

For `src/intraday/market_store.py`:
```bash
grep -r "from src.intraday\|from src.intraday.market_store\|market_store" . --include="*.py"
```
- If zero callers → delete file + `src/intraday/__init__.py` + directory. Re-index graph.
- If callers exist → document fully in CONTEXT_TREE (SS2 entry will need update) and write tests.

**Test gate:** `python -m pytest tests/unit/ --tb=no -q` — all green after any deletion.

**Commit (if deleting both):** `refactor(src): delete dead service.py and market_store.py modules`
**Commit (if keeping either):** `refactor(src): <describe specific action> for <module>`

**After:** Re-index: `mcp__codebase-memory-mcp__index_repository`.

---

### SS4 — Write missing CLAUDE.md files; codify model placement convention

**What and why:**
`src/gamma/` and `src/nuvama/` both have significant invariants but no CLAUDE.md.
The model placement convention (shared types in `src/models/`, domain-local types in their module)
is followed but never documented — next person to add a module will guess wrong.

**Files to create:**

`src/gamma/CLAUDE.md` — must cover:
- Module purpose: Near-Expiry Gamma Buy scaffolding; `GammaChainSnapshot` + `GammaWatchlistEntry` frozen dataclasses
- `GammaStore` SQLite operations; table name; primary key / upsert semantics
- What does NOT yet exist: `gamma_daily_watch.py` script (planned, Phase A next)
- Any Decimal invariant or Greeks field constraints

`src/nuvama/CLAUDE.md` — must cover:
- `NuvamaClient` protocol + `MockNuvamaClient` (in `mock_client.py`, not `protocol.py`)
- `_EXCLUDE_ISINS` exclusion list in `reader.py` and why it exists
- `availabelBalance` Dhan API typo mapped in `positions_reader.py` (note: this is in dhan, not nuvama — double-check)
- `record_all_options_snapshots` atomicity guarantee (executemany in single transaction — AR-7)
- `get_cumulative_realized_pnl` — SQL GROUP BY aggregation, not in-memory

**`docs/plan/` addition — model placement convention (add to stories.md SR11 or DECISIONS.md):**

Convention to codify in DECISIONS.md:
```
| 2026-05-29 | src/ model placement rule: types shared across two or more modules go into
  src/models/ (portfolio.py, mf.py, options.py). Types used only within one domain stay
  in that domain's models.py (dhan, nuvama, paper, risk). New shared types must land in
  src/models/ from day one — do not create src/<module>/models.py and later migrate.
  | src-restructure SS4 |
```

**Test gate:** `python -m pytest tests/unit/ --tb=no -q` — all green (no code changes, but verify).

**Commit:** `docs(src): add CLAUDE.md for gamma and nuvama; codify model placement rule in DECISIONS.md`

---

### SS5 — CONTEXT_TREE.md sync after src/ restructure

**What and why:**
SS1 and SS3 move or delete files from `src/`. CONTEXT_TREE.md is the authoritative module index
and must reflect the post-restructure state exactly. This story is a dedicated docs-close pass
after both SS1 and SS3 are committed — do not run it mid-migration.

**Depends on:** SS1 closed + SS3 closed.

**Files to update (targeted `Edit` calls only — never `Write` on CONTEXT_TREE.md):**

After SS1 (evict analytics/ and sandbox/):
- Remove `├── analytics/` block entirely — files moved to `scripts/dev/`
- Remove `├── sandbox/` block entirely — files moved to `scripts/dev/`
- Verify `scripts/dev/` entry in the scripts section accurately reflects the two renamed files:
  `verify_analytics.py` (was `test_analytics_apis.py`) and `sandbox_order_lifecycle.py`
  (was `test_sandbox_order_lifecycle.py`)

After SS3 (resolve service.py and market_store.py):
- If `src/portfolio/service.py` was deleted: remove its `service.py` line from the portfolio block
- If `src/portfolio/service.py` was kept and refactored: update the description to reflect actual state
- If `src/intraday/` was deleted: remove the entire `├── intraday/` block
- If `src/intraday/` was kept: ensure `market_store.py` description is accurate

**Verification step — run before committing:**
```bash
# Every file in src/ must have a CONTEXT_TREE entry; every entry must match a real file
python -c "
import os, re
from pathlib import Path

tree = Path('CONTEXT_TREE.md').read_text()
src_files = {
    str(p.relative_to('src/')).replace(os.sep, '/')
    for p in Path('src').rglob('*.py')
    if '__pycache__' not in str(p)
}
missing = [f for f in sorted(src_files) if Path(f).name not in tree]
if missing:
    print('MISSING from CONTEXT_TREE:', *missing, sep='\n  ')
else:
    print('OK — all src/ files present in CONTEXT_TREE')
"
```

**No code changes. No test gate needed (docs only).**

**Commit:** `docs(src): sync CONTEXT_TREE.md after SS1 and SS3 src/ restructure`

---

---

## `docs/archive/` Restructure Stories (DA series)

> **Governing principle:** `docs/archive/` is a read-only graveyard — once a file lands
> here it is never edited, only read. The folder structure must make it obvious what type of
> content is in each subfolder without opening any file.
>
> **Two files are permanently pinned at archive root** — do not move them:
> - `BACKTEST_PLAN_ARCHIVE.md` — path-linked from `BACKTEST_PLAN.md` and `BACKTEST_PLAN_PHASE1.md`
> - `TODOS_ARCHIVE.md` — path-linked from `TODOS.md` and `.claude/skills/md-cleanup/SKILL.md`
> Moving either breaks live root-doc references and the md-cleanup skill.

---

### DA0 — Audit (closed 2026-05-29)

Full inventory of `docs/archive/` completed. Issues found:

1. **8 files loose at archive root** with no categorisation — workflow logs, plan docs,
   strategy guides, and a dead stub all mixed together.
2. **`docs/archive/plan/` has mixed content** — retired story folders (correct) alongside
   strategy research docs (`INVESTMENT_STRATEGY_RESEARCH.md`, `SWING_STRATEGY_RESEARCH.md`,
   `signal_pipeline_spec.md`) that belong in a `research/` folder.
3. **`docs/archive/reco_tracker.md`** is a dead stub ("renamed to MVP; see
   `docs/plan/mvp_tracker.md`" — that path no longer exists). Safe to delete.
4. **`docs/antigravity/gamma_implementation_plan.md`** (live folder) is a completed
   Antigravity task plan, not a workflow-collaboration doc. Belongs in archive.
5. **`docs/analysis/`** (live folder) is completely empty. Delete.
6. **Two new subfolders needed:** `process/` for workflow/session docs; `research/` for
   strategy research that never shipped into a spec.

**Final target layout:**
```
docs/archive/
├── BACKTEST_PLAN_ARCHIVE.md   ← PINNED — do not move (path-linked from root docs)
├── TODOS_ARCHIVE.md           ← PINNED — do not move (path-linked from root docs + md-cleanup skill)
├── analysis/                  # Quantitative analysis, tool probes, sizing studies
│   ├── overlay_lot_sizing_2026-05-12.md
│   └── tv_mcp_testing_framework.md        ← from archive root
├── antigravity/               # Completed Antigravity session plans
│   ├── audit_13_implementation_plan.md
│   └── gamma_implementation_plan.md       ← from docs/antigravity/ (live)
├── council/                   # Completed council decisions (research/risk/strategy subdirs)
│   ├── research/
│   ├── risk/
│   └── strategy/
├── plan/                      # Retired story folders + pre-story-folder plan docs
│   ├── README.md
│   ├── chain-data/            ← already correct
│   ├── 0_3_finideas_roll.md
│   ├── 1_10_dhan_chain_client.md
│   ├── 1_5b_analytics_module.md
│   ├── mvp_tracker.md                     ← from archive root
│   ├── PAPER_TRADING_PLAN.md
│   ├── paper_3track_overlay.md
│   ├── paper_3track_roll.md
│   ├── story_audit_remediation.md
│   ├── story_paper_impl_tasks.md          ← from archive root
│   ├── story_risk_gamma_phase_a.md
│   └── variance_gate.md
├── process/                   ← NEW: workflow docs, session logs, operator guides
│   ├── 2026-05-08_workflow-improvements.md  ← from archive root
│   └── paper_trading.md                     ← from archive root
├── research/                  ← NEW: strategy research that never shipped into a spec
│   ├── INVESTMENT_STRATEGY_RESEARCH.md    ← from archive/plan/
│   ├── SWING_STRATEGY_RESEARCH.md         ← from archive/plan/
│   └── signal_pipeline_spec.md            ← from archive/plan/
├── reviews/                   # Code and plan review outputs — no changes needed
│   ├── audit_2026-05-15.md
│   └── backtest_plan_pm_review_2026-04-27.md
└── strategies/                # Superseded strategy specs — no changes needed
    ├── covered_call_overlay_v1.md
    └── csp_v1_revision_prompt.md
```

**Files to delete:**
- `docs/archive/reco_tracker.md` — dead stub pointing to a path that no longer exists
- `docs/analysis/` — empty directory (live folder, not archive)

---

### DA1 — Implement archive restructure

**No code. No tests. Pure file moves and deletes.**
This is safe to run any time — archive files are never imported or path-referenced in code.
Exception: the two pinned root files — do not touch them.

**Before starting:** confirm pinned files are NOT in the move list:
```bash
grep -r "BACKTEST_PLAN_ARCHIVE\|TODOS_ARCHIVE" \
  /path/to/NiftyShield --include="*.md" | grep -v "^docs/archive/"
# Must show hits in BACKTEST_PLAN.md, TODOS.md, and the skill — confirms they are live-linked
```

**Step 1 — Create new subfolders:**
```bash
mkdir -p docs/archive/process
mkdir -p docs/archive/research
# antigravity/ already exists in archive
```

**Step 2 — Move loose root files:**
```bash
git mv docs/archive/tv_mcp_testing_framework.md  docs/archive/analysis/
git mv docs/archive/mvp_tracker.md               docs/archive/plan/
git mv docs/archive/story_paper_impl_tasks.md    docs/archive/plan/
git mv docs/archive/2026-05-08_workflow-improvements.md  docs/archive/process/
git mv docs/archive/paper_trading.md             docs/archive/process/
```

**Step 3 — Move misplaced plan/ files to research/:**
```bash
git mv docs/archive/plan/INVESTMENT_STRATEGY_RESEARCH.md  docs/archive/research/
git mv docs/archive/plan/SWING_STRATEGY_RESEARCH.md       docs/archive/research/
git mv docs/archive/plan/signal_pipeline_spec.md          docs/archive/research/
```

**Step 4 — Move live docs/antigravity/ plan into archive:**
```bash
git mv docs/antigravity/gamma_implementation_plan.md  docs/archive/antigravity/
```

**Step 5 — Delete dead files and empty directories:**
```bash
git rm docs/archive/reco_tracker.md
rmdir docs/analysis  # remove empty live directory (not tracked by git if empty)
```

**Step 6 — Verify final state:**
```bash
# Nothing loose at archive root except the two pinned files + README
ls docs/archive/*.md
# Should show: BACKTEST_PLAN_ARCHIVE.md  TODOS_ARCHIVE.md  (+ README.md if present)

# No broken internal links in archive (spot-check the dead stub is gone)
grep -r "reco_tracker\|mvp_tracker" docs/ --include="*.md"

# docs/antigravity/ should now have only 2 files
ls docs/antigravity/
# Expected: ai_collaboration_plan.md  antigravity_best_practices.md
```

**Commit:** `refactor(docs): restructure docs/archive/ — add process/ and research/ folders; evict gamma plan from live antigravity/`
