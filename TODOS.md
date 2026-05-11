# NiftyShield — TODOs

> Open work only. Completed items and session history:
> - 2026-04-30 and earlier: [docs/archive/TODOS_ARCHIVE_2026-05-01.md](docs/archive/TODOS_ARCHIVE_2026-05-01.md)
> - 2026-05-01 to 2026-05-09: [docs/archive/TODOS_ARCHIVE_2026-05-10.md](docs/archive/TODOS_ARCHIVE_2026-05-10.md)

---

## Sequential Queue — Next 6 Months

Tasks 0–3 run in this order. Do not start the next until the current ships and tests are green.
Ongoing paper-trading tasks (Animesh) run in parallel and are listed separately below.

| # | Task | Owner | Hard Deadline | Status |
|---|---|---|---|---|
| **0** | Fix bhavcopy UDiFF format (Dec 2024+) | Cowork | ASAP | Unblocked |
| **1** | India VIX ingestion + IVR calculation | Cowork | Jun 2026 | Unblocked |
| **2** | PortfolioDeltaTracker (`src/risk/`) | Cowork | Jun 2026 | Unblocked |
| **3** | June 2026 Finideas roll cycle | Animesh + Cowork | **2026-06-30** | Awaiting Finideas instructions |

---

## Task 0 — Fix bhavcopy pipeline for NSE UDiFF format (Dec 2024+)

**Discovered 2026-05-03 during smoke test.** NSE migrated F&O bhavcopy to UDiFF format in
late 2024. Old URL and CSV schema only cover 2016 → ~Nov 2024. Full column mapping and fix
spec in `DECISIONS.md → "NSE Bhavcopy Format Migration"`.

**File to change:** `src/backtest/bhavcopy_ingest.py` only. No schema or model changes.

**Exact cutover date:** TBD. Confirmed working: `2024-04-25` (legacy). Confirmed broken:
`2024-12-02` (legacy). Binary search needed to pin the exact month boundary.

**Safe bootstrap range until fix ships:** `--end 2024-11-01`. Covers 2016–Oct 2024 (~8.5
years), including all critical stress windows: IL&FS Sep 2018, COVID Mar 2020,
rate-hike Jan–Jun 2022, Jun 2024 election day.

**Changes required:**

1. `download_bhavcopy`: try UDiFF URL first (`/content/fo/BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip`); fall back to legacy URL on 404.
2. `parse_bhavcopy`: detect format by checking `'TradDt' in reader.fieldnames`. Route to `_parse_legacy()` or `_parse_udiff()` accordingly. `BhavRecord` model unchanged.
3. `_parse_udiff()`: map UDiFF columns. Key differences: ISO date strings (no strptime); `FinInstrmTp` → instrument (`IDO`→OPTIDX, `STO`→OPTSTK, `IDF`→FUTIDX, `SDF`→FUTSTK); filter by `TckrSymb == underlying`.
4. Tests: add one UDiFF fixture row (NIFTY `IDO` option). Test format detection and routing.

---

## Task 1 — India VIX ingestion + IVR calculation

**Prerequisite for Phase 0.8 gate criteria C and D (regime completeness + regime-matched Z-score).**

IVR (IV Rank) at entry is required to: (1) enforce R3 entry filter (IVR 25–50), (2) flag high-IVR
regime cycles (IVR > 50) for criterion C, (3) filter backtest for regime-matched Z-score comparison
in task 1.11. Currently, India VIX is not ingested — R3 enforcement and regime completeness checks
are blocked.

**Scope (implements the VIX daily sub-path of BACKTEST_PLAN_PHASE1.md task 1.3a):**

- `src/backtest/ohlc_ingest.py` (or new `src/backtest/vix_ingest.py`): daily India VIX ingest from
  `NSE_INDEX|India VIX` via Upstox `/v2/historical-candle/` (free, existing `UPSTOX_ANALYTICS_TOKEN`).
  Store as Parquet: `data/historical/ohlc/india_vix/`. Resumable — skip dates already present.
- IVR formula: `ivr = (vix_today − vix_252d_low) / (vix_252d_high − vix_252d_low)`. Clamp to `[0.0, 1.0]`.
  Already implemented in `src/backtest/ivr.py` (`compute_ivr`) — wire at entry-log time.
- Log IVR at entry for every paper trade: add `ivr_at_entry: float | None` field to `PaperTrade` model
  or `paper_nav_snapshots` (confirm canonical location in `src/paper/CLAUDE.md` before changing schema).
- Enable R3 gate check in `scripts/record_paper_trade.py`: compute IVR from ingested data; warn (do not
  block) when IVR < 25 or > 50.
- Tests: VIX Parquet resumability (skip if already present); IVR boundary tests (already in `test_ivr.py`);
  R3 warning path in `record_paper_trade.py` (mock IVR fetch).

**Owner:** Cowork. Unblocks R3, criterion C, and BACKTEST_PLAN_PHASE1.md task 1.11 regime-matched comparison.

---

## Task 2 — PortfolioDeltaTracker (`src/risk/`)

**Source: `docs/council/2026-05-02_multi-strategy-portfolio-risk-allocation.md` §7.3.**

Cowork code task — unblocked. Implements the aggregate portfolio-delta guard that prevents net long bias
from compounding across all open paper positions and the NiftyBees ETF holding.

**Exact scope (from BACKTEST_PLAN.md task 0.6c):**

- `src/risk/__init__.py` — package stub with one comment line (required for codebase-memory-mcp indexing).
- `src/risk/models.py` — `PortfolioDelta` frozen dataclass: `options_delta_lots: Decimal`,
  `niftybees_delta_lots: Decimal`, `total_delta_lots: Decimal`, `warning_breached: bool`,
  `cap_breached: bool`, `as_of: datetime`.
- `src/risk/delta_tracker.py` — `PortfolioDeltaTracker`:
  - `aggregate_delta(paper_positions: list[PaperPosition], nifty_spot: Decimal, lot_size: int) → PortfolioDelta`
  - Options-only cap: +1.0 lots (warning +0.75). Options + NiftyBees cap: +2.0 lots (warning +1.5). Constants parameterised.
  - NiftyBees delta: `niftybees_qty × niftybees_ltp / (nifty_spot × lot_size)` (beta = 1.0).
- `src/risk/entry_gate.py` — `check_entry_allowed(current_delta: PortfolioDelta, trade_delta_lots: Decimal, is_protective: bool) → tuple[bool, str]`. Protective entries always `(True, "")`.
- Tests: `tests/unit/risk/test_delta_tracker.py` — happy path, warning boundary, hard cap breach,
  protective bypass, zero-position base case. `tests/unit/risk/__init__.py` required.
- `python -m pytest tests/unit/ --tb=no -q` green.
- Commit: `feat(risk): add PortfolioDeltaTracker with entry gate`.

**Owner:** Cowork. Unblocks the entry guard for 0.6b paper trades.

---

## Task 3 — June 2026 Finideas Roll Cycle

**Hard deadline: 2026-06-30** (NIFTY_JUN 23000 CE and PE legs expire, per `REFERENCES.md`).

Invoke `roll-validator` agent ≥1 week before deadline. Steps:

- [ ] Invoke `roll-validator` agent ≥1 week before 2026-06-30 to pre-check position state, Trade model integrity, and DB atomicity.
- [ ] Receive Finideas roll instructions (strike, expiry, quantity for each leg).
- [ ] Run `python -m scripts.roll_leg --dry-run ...` with all four `--old-*/--new-*` flags filled. Verify output.
- [ ] Run without `--dry-run`. Verify both Trade rows inserted atomically.
- [ ] Run `python -m scripts.daily_snapshot` same day. Confirm P&L continues uninterrupted; new JUL/SEP leg prices reflected in mark-to-market.
- [ ] Session log entry in `TODOS.md` with date, old/new instrument keys, and any anomalies.
- [ ] If any bug surfaces: file a separate fix commit before moving on.

**Owner:** Animesh (receives instructions) + Cowork (executes scripts).

---

## Ongoing Paper Trading (Animesh — parallel to Tasks 0–3)

These run continuously throughout Phase 0, independent of the code queue above.

### 0.6 — CSP v1 Paper Trading

- [ ] Each month at entry date: observe live chain, decide strike (22-delta target per `csp_nifty_v1.md`). Log via `record_paper_trade.py` with mid − 0.25 INR slippage haircut.
- [ ] Monitor daily via `daily_snapshot.py`. Log exit when profit target / time stop / loss stop hits.
- [ ] Never override the spec in real time. If urge to override: log it in `TODOS.md` with reason, then follow spec anyway.
- [ ] Minimum: **6 full monthly cycles (~6 months)**, with at least one cycle triggering each exit type.

### 0.6a — NiftyShield Integrated v1 Paper Trading

- [ ] At each CSP entry: also enter Leg 2 (put spread, 4 lots) via `--strategy paper_niftyshield_v1`.
- [ ] Each quarter (Jan/Apr/Jul/Oct): enter Leg 3 (tail puts, 2 lots).
- [ ] Leg 2 enters even when Leg 1 is skipped (R3/R4 filters) — protection is unconditional.
- [ ] **Implementation Task**: Create `scripts/paper_csp_roll.py` to automate roll-over of Leg 1 (CSP) positions, mirroring the `paper_3track_overlay_roll.py` workflow.
- [ ] `paper_3track_overlay.py:243` — migrate `lookup._instruments` loop to `get_expiry_candidates` public API, same pattern as the Phase 1 fix in `paper_3track_entry.py`.
- [ ] Minimum: 6 monthly cycles for Legs 1+2; 2 quarterly cycles for Leg 3.

### 0.6b — 3-Track Nifty Instrument Comparison Paper Trading

**Unblocked (0.4b done 2026-05-03). Source: `docs/strategies/nifty_track_comparison_v1.md`.**

- [ ] Enter Spot base leg (long NiftyBees) via `--strategy paper_nifty_spot --leg base_etf`.
- [ ] Enter Futures base leg (long Nifty Futures notional) via `--strategy paper_nifty_futures --leg base_futures`.
- [ ] Enter Proxy base leg (Deep ITM Call, delta ≈ 0.90) via `--strategy paper_nifty_proxy --leg base_ditm_call`.
- [ ] For each approved overlay per track, record as a separate leg within the same strategy namespace.
- [ ] Do NOT record Futures + standalone Covered Call — blocked per council ruling.
- [ ] On each expiry: roll all base legs; document delta at roll time for Proxy.
- [ ] Minimum 6 monthly cycles before cross-track conclusions. Include ≥1 high-VIX event (India VIX >18).

### Stockmock Calibration Backtests (Animesh only — prerequisite for Phase 1.7)

Run CSP + IC backtests on Nifty options in Stockmock UI across four stress windows. No code required.

- [ ] COVID crash (Feb–Apr 2020): monthly CSP at 20-delta. Record strikes hit, premium, max M2M loss, breach frequency.
- [ ] IL&FS crisis (Sep–Oct 2018): same metrics.
- [ ] 2022 rate-hike selloff (Jan–Jun 2022): same metrics.
- [ ] Stable baseline (Jan–Dec 2023): establishes expected exit-type distribution in normal markets.
- [ ] Summarise in `docs/strategies/csp_nifty_v1.md` → "Calibration Backtest Results (Stockmock)" section.
- [ ] Commit: `docs(strategies): CSP v1 Stockmock calibration backtest results`.

**Note:** Canonical strategy file is `csp_nifty_v1.md` (underlying changed from NiftyBees to Nifty 50 per 2026-04-25 decision).

---

## Paper Trading CLI & UX Refactor

Discovered 2026-05-11 via full CLI audit of all six paper trading scripts. Issues are independent
and can be worked in any order unless otherwise noted. Issue 9 (shared formatting module) should be
completed before issues 6–8 (output fixes) to avoid duplicating work.

Each issue includes a self-contained Antigravity handoff prompt.

---

### CLI-1 — Unify dry-run flag across all scripts

**Problem:** Three incompatible conventions for "don't write to DB":
`--dry-run/--no-dry-run` (BooleanOptionalAction, paper_snapshot + record_paper_trade + find_strike_by_delta),
`--no-save` (store_true, paper_3track_snapshot), and `--yes` used as the write flag
(paper_3track_overlay_roll — no explicit dry-run flag at all).

**Fix:** All six scripts use `--dry-run / --no-dry-run` (BooleanOptionalAction). Rename
`--no-save` → `--dry-run` in `paper_3track_snapshot.py`. Add `--dry-run` /`--no-dry-run`
to `paper_3track_overlay_roll.py`; `--yes` retains its current meaning (skip interactive
confirmation prompt) which is a separate concern.

**Files:** `scripts/paper_3track_snapshot.py`, `scripts/paper_3track_overlay_roll.py`

**Antigravity handoff:**
> Read `CONTEXT.md` and `src/paper/CLAUDE.md`. Two scripts have inconsistent dry-run flags
> versus the rest of the paper trading CLI family.
>
> **`scripts/paper_3track_snapshot.py`:** rename `--no-save` → `--dry-run` (BooleanOptionalAction,
> default True). Update all internal references (`args.no_save` → `args.dry_run`). Update
> docstring usage examples. The confirmation footer already prints "no records written" — keep
> wording, just change the flag check.
>
> **`scripts/paper_3track_overlay_roll.py`:** add `--dry-run / --no-dry-run`
> (BooleanOptionalAction, default True) as the primary write gate. Keep `--yes` as a separate
> "skip interactive confirmation prompt" flag (it already exists for that purpose). `--yes`
> without `--no-dry-run` should warn and exit: "Use --no-dry-run --yes to write." Update
> the script docstring and usage examples accordingly.
>
> Tests: update any unit/integration tests that pass `--no-save` to pass `--dry-run`.
> Grep for `no_save` and `no-save` to catch all call sites. Run `python -m pytest tests/unit/ --tb=no -q` green.
> Commit: `fix(scripts): unify dry-run flag across paper trading CLI`

---

### CLI-2 — Unify spot price flag (`--underlying-price` → `--spot`)

**Problem:** `paper_snapshot.py` uses `--underlying-price` for the Nifty spot price input.
Every other script that accepts a spot price (`paper_3track_snapshot.py`) uses `--spot`.
Same concept, two names, different internal dest names.

**Fix:** Rename `--underlying-price` → `--spot` in `paper_snapshot.py`. Keep
`dest="underlying_price"` to minimise internal churn (or rename to `dest="spot"` — either
is fine, just pick one and stay consistent).

**Files:** `scripts/paper_snapshot.py`

**Antigravity handoff:**
> Read `CONTEXT.md`. In `scripts/paper_snapshot.py`, the arg `--underlying-price` is the odd
> one out — every other paper trading script uses `--spot` for the same purpose.
>
> Rename `--underlying-price` to `--spot` in `_parse_args()`. Update `dest` to `spot` for
> clarity. Update all internal `args.underlying_price` references to `args.spot`. Update the
> docstring usage examples at the top of the file.
>
> No model or DB change — this is a CLI surface rename only. Grep for `underlying.price`
> and `underlying_price` to catch all arg references within this file.
>
> Run `python -m pytest tests/unit/ --tb=no -q` green.
> Commit: `fix(scripts): rename --underlying-price to --spot in paper_snapshot`

---

### CLI-3 — Add `--index` to `paper_3track_overlay_roll.py`

**Problem:** `paper_3track_overlay_roll.py` uses the same internal candidate-ranking
algorithm as `paper_3track_overlay.py` and `find_strike_by_delta.py` to select the
replacement strike. It silently takes rank 1 with no way to override. `--index N` exists
on both other scripts that use this ranking.

**Fix:** Add `--index` (type=int, default=1, metavar="N") to `paper_3track_overlay_roll.py`.
Thread it through to the replacement-leg candidate selection. Mirror the clamping/warning
behaviour from `find_strike_by_delta.py` (warn on out-of-range, clamp to last rank).

**Files:** `scripts/paper_3track_overlay_roll.py`

**Antigravity handoff:**
> Read `CONTEXT.md` and `src/paper/CLAUDE.md`. `scripts/paper_3track_overlay_roll.py`
> internally ranks replacement leg candidates but always picks rank 1. The user has no way
> to select a different candidate.
>
> Add `--index` argument (type=int, default=1, metavar="N", help="Select Nth-ranked
> replacement candidate (1-based). Default: 1.") to `_parse_args()`.
>
> Trace where the replacement candidate is selected inside `_run()` (look for the candidate
> list construction and the index used to pick from it). Pass `args.index - 1` as the
> selection offset. Add clamping: if `args.index - 1 >= len(candidates)`, print a warning
> to stderr and clamp to the last candidate (same pattern as `find_strike_by_delta.py`
> lines ~253–258).
>
> Test: one happy-path test (index=2 picks second candidate when available), one edge case
> (index out of range clamps and warns). No network in tests — use fixture data.
>
> Run `python -m pytest tests/unit/ --tb=no -q` green.
> Commit: `feat(scripts): add --index to paper_3track_overlay_roll`

---

### CLI-4 — Consistent `--date` type parsing (use `type=date.fromisoformat`)

**Problem:** `paper_3track_overlay_roll.py` correctly declares `--date` with
`type=date.fromisoformat` giving immediate validation at parse time. All other scripts
accept `--date` as a raw string and either parse it later inline or defer validation —
meaning a bad date string produces a confusing runtime error deep in `_run()` rather
than an argparse error at the boundary.

**Fix:** Apply `type=date.fromisoformat` to `--date` in `paper_snapshot.py`,
`paper_3track_snapshot.py`, `paper_3track_overlay.py`, and `find_strike_by_delta.py`.
Remove the manual `date.fromisoformat()` / `date.fromisoformat(args.date)` calls inside
`_run()` where they duplicate the now-redundant parse step.

**Files:** `scripts/paper_snapshot.py`, `scripts/paper_3track_snapshot.py`,
`scripts/paper_3track_overlay.py`, `scripts/find_strike_by_delta.py`

**Antigravity handoff:**
> Read `CONTEXT.md`. Four paper trading scripts accept `--date` as a raw string and parse
> it manually inside `_run()`. `paper_3track_overlay_roll.py` already does it correctly
> with `type=date.fromisoformat` in `add_argument()`.
>
> For each of the four files listed above: change the `--date` argument to add
> `type=date.fromisoformat`. Then find the corresponding `date.fromisoformat(args.date)`
> or `date.fromisoformat(args.snapshot_date)` calls inside `_run()` and remove them —
> `args.date` will now be a `datetime.date` directly (or `None` if not provided). Update
> the `default=None` so that `None` is still the sentinel for "use today".
>
> Watch out for: `args.snapshot_date` dest alias in `paper_snapshot.py` — the dest name
> differs from the flag name there.
>
> Run `python -m pytest tests/unit/ --tb=no -q` green.
> Commit: `fix(scripts): use type=date.fromisoformat for --date across paper CLI`

---

### CLI-5 — Add track shortcuts to `find_strike_by_delta.py`

**Problem:** `find_strike_by_delta.py` takes `--underlying` as a raw instrument key
(e.g. `NSE_INDEX|Nifty 50`). All 3-track scripts accept `--tracks spot|futures|proxy`
as shortcuts. In practice `find_strike_by_delta.py` is used primarily in the 3-track
workflow to select overlay strikes, so users must look up the underlying key manually
every time.

**Fix:** Add an optional `--track` argument (choices: `spot`, `futures`, `proxy`) that
maps to the canonical underlying key via the same `_TRACK_MAP` dict used in the 3-track
scripts. Mutually exclusive with `--underlying`. When `--track` is given, derive the
underlying key from the map; when neither is given, default to existing behaviour
(`UNDERLYING_DEFAULT`).

**Files:** `scripts/find_strike_by_delta.py`

**Antigravity handoff:**
> Read `CONTEXT.md`. `scripts/find_strike_by_delta.py` is used in the 3-track overlay
> workflow but requires the user to pass the raw instrument key via `--underlying`.
> All 3-track scripts accept `--tracks spot|futures|proxy` shortcuts.
>
> Add a `--track` argument (single value, choices=["spot", "futures", "proxy"], default=None)
> to `_parse_args()`. Define a `_TRACK_UNDERLYING_MAP` that maps the three short names to
> their instrument keys (look up the canonical keys in `REFERENCES.md` or from the existing
> `_TRACK_MAP` pattern in `paper_3track_overlay.py`).
>
> Make `--track` and `--underlying` mutually exclusive (use `parser.add_mutually_exclusive_group()`).
> In `_run()`: if `args.track` is set, override `args.underlying` with the mapped key before
> proceeding. When neither is supplied, keep existing `UNDERLYING_DEFAULT` behaviour.
>
> Update the argparse description and docstring examples to show `--track proxy` usage.
>
> Tests: one test per track shortcut resolves to the correct underlying key. One test
> that `--track` and `--underlying` together raises an error.
>
> Run `python -m pytest tests/unit/ --tb=no -q` green.
> Commit: `feat(scripts): add --track shortcut to find_strike_by_delta`

---

### UX-6 — `paper_snapshot.py` output → compact P&L table (depends on UX-9)

**Problem:** Output is a text block with `label: value` per line per strategy. Does not
scale beyond one strategy and is not scannable. Requested format: a table with columns
Strategy | Unrealized | Realized | Total P&L, one row per strategy.

**Prerequisite:** Complete UX-9 (shared `src/paper/formatting.py`) first and use
`format_pnl_table()` from there.

**Files:** `scripts/paper_snapshot.py`, `src/paper/formatting.py` (read-only dependency)

**Antigravity handoff:**
> Read `CONTEXT.md` and `src/paper/CLAUDE.md`. `scripts/paper_snapshot.py` prints P&L
> as a text block (label: value). Replace with a compact table using `format_pnl_table()`
> from `src/paper/formatting.py` (UX-9 must be complete first — verify the function exists
> before starting).
>
> The table has four columns: Strategy (left-aligned, 30 chars), Unrealized (right 14),
> Realized (right 14), Total P&L (right 14). Monetary values formatted as `₹{val:>+,.0f}`
> (sign-always, no decimals for compactness, comma separator). Add a header row and a
> separator line. For `--dry-run` mode, prefix the table header with `[DRY RUN] {date}`.
> For write mode, prefix with `{date} — written to DB`.
>
> Remove the old per-strategy print blocks inside the `for name in strategy_names` loop.
> Collect all rows first, then render the table once at the end.
>
> Tests: mock `tracker.compute_pnl` to return fixed values; assert table output contains
> the strategy name and correct P&L values. Test with one strategy and with multiple.
>
> Run `python -m pytest tests/unit/ --tb=no -q` green.
> Commit: `feat(scripts): compact P&L table output in paper_snapshot`

---

### UX-7 — `paper_3track_snapshot.py` — summary table first, verbose blocks after

**Problem:** The cross-track summary table (5 lines, highest signal) is printed last,
after three verbose per-track blocks (~35 lines total). Users must scroll past all the
detail to read the summary. In EOD cron output or a terminal session this is backwards.

**Fix:** Print `_print_summary_table()` first (immediately after the spot price header),
then the per-track verbose blocks. No content change — only print order.

**Files:** `scripts/paper_3track_snapshot.py`

**Antigravity handoff:**
> Read `CONTEXT.md`. In `scripts/paper_3track_snapshot.py`, `_print_summary_table()` is
> called at line ~415, after the per-track `_print_track_block()` loop. Move the
> `_print_summary_table(results, snap_date)` call to immediately after the spot-price
> header print block (around line 344, after the `═══` header) and before the
> `for track_name, snapshot, ... in results` loop.
>
> The `results` list must be fully populated before `_print_summary_table()` is called, so
> the loop that builds `results` must complete first. Check whether `results` is built
> separately from the print loop or inline — if inline, split it: first pass builds the
> list, second pass prints verbose blocks.
>
> No logic change. No model change. Output content identical, only ordering changes.
>
> Run `python -m pytest tests/unit/ --tb=no -q` green.
> Commit: `fix(scripts): print summary table before verbose blocks in paper_3track_snapshot`

---

### UX-8 — `paper_3track_snapshot.py` — gate verbose track blocks behind `--verbose`

**Problem:** The per-track verbose block (Greeks, MaxDD, Ret/NEE, per-leg delta arrows)
is ~10 lines per track, 30+ lines total. For daily EOD use the cross-track summary is
sufficient. The verbose block is useful for debugging and deep inspection but should be
opt-in.

**Fix:** Add `--verbose` / `-v` flag (store_true, default False). When not set, print
only the summary table. When set, also print the full per-track blocks after the summary.

**Files:** `scripts/paper_3track_snapshot.py`

**Antigravity handoff:**
> Read `CONTEXT.md`. In `scripts/paper_3track_snapshot.py`, add a `--verbose` / `-v`
> flag (action="store_true", default=False) to `_parse_args()`. Update the description to
> note that verbose shows per-track Greek and delta detail.
>
> In `_run()`, gate the `_print_track_block(...)` loop behind `if args.verbose:`. The
> summary table (`_print_summary_table()`) always prints (this depends on UX-7 being done
> first — verify summary-first ordering is already in place).
>
> Update the docstring usage block to show `--verbose` example.
>
> Tests: assert that without `--verbose`, output does not contain the per-track separator
> line (e.g. `"─" * 84`). With `--verbose`, assert it does. Mock all DB + broker calls.
>
> Run `python -m pytest tests/unit/ --tb=no -q` green.
> Commit: `feat(scripts): add --verbose flag to paper_3track_snapshot`

---

### UX-9 — Extract `src/paper/formatting.py` (shared output utilities)

**Problem:** Each script hand-rolls its own output with hardcoded column widths, separator
chars, and `₹` formatting. There is no shared layer — future scripts will continue to
diverge. `find_strike_by_delta.py` has a proper `format_table()` that is not reused
anywhere.

**This is the prerequisite for UX-6, UX-7, and UX-8.**

**Fix:** Create `src/paper/formatting.py` with at minimum:
- `format_pnl_table(rows, title, is_dry_run) → str` — renders Strategy | Unrealized | Realized | Total P&L
- `format_track_summary(rows) → str` — renders the 3-track cross-comparison summary (Base | Overlay | Net | Ret/NEE)
- `fmt_inr(value: Decimal, sign_always: bool) → str` — canonical `₹` formatter

**Files:** `src/paper/formatting.py` (new), `src/paper/__init__.py` (re-export)

**Antigravity handoff:**
> Read `CONTEXT.md`, `src/paper/CLAUDE.md`, and `src/paper/constants.py`. Create a new
> module `src/paper/formatting.py` with shared output helpers used by all paper trading
> scripts.
>
> Implement these three functions (Google-style docstrings, full type hints):
>
> `fmt_inr(value: Decimal, sign_always: bool = False) -> str`
> — Returns `₹{value:+,.0f}` (sign_always=True) or `₹{value:,.0f}` (False). Zero is `₹0`.
>
> `format_pnl_table(rows: list[dict], title: str = "", is_dry_run: bool = False) -> str`
> — `rows` is a list of dicts with keys: `strategy` (str), `unrealized` (Decimal),
>   `realized` (Decimal), `total` (Decimal). Returns a formatted string with header,
>   separator, data rows, and optional `[DRY RUN]` prefix on the title line.
>   Column widths: strategy 30, each monetary column 14 (right-aligned, sign-always).
>
> `format_track_summary(rows: list[dict], snap_date: date) -> str`
> — `rows` is a list of dicts with keys: `label` (str), `base_pnl` (Decimal),
>   `overlay_pnl` (Decimal), `net_pnl` (Decimal), `return_on_nee` (float).
>   Returns a formatted string matching the existing summary table in
>   `paper_3track_snapshot.py` `_print_summary_table()`.
>
> All functions return `str` — callers do `print(format_pnl_table(...))`. Do not call
> `print()` inside the formatters.
>
> Add `src/paper/formatting.py` to `src/paper/__init__.py` re-exports.
>
> Tests in `tests/unit/paper/test_formatting.py`: happy path for each function, Decimal
> sign behaviour, empty-rows case for both table functions.
>
> Run `python -m pytest tests/unit/ --tb=no -q` green.
> Commit: `feat(paper): add shared formatting.py with fmt_inr + table helpers`

---

### CLI-10 — Add `--overlay` filter to `paper_3track_overlay_roll.py`

**Problem:** `paper_3track_overlay_roll.py` rolls all open overlay legs across all tracks
simultaneously. If you have a collar active and want to roll only the PE leg (e.g. after
a directional move), there is no way to target it — the script is all-or-nothing.
`paper_3track_overlay.py` requires `--overlay pp|cc|collar` for exactly this targeting.

**Fix:** Add `--overlay` (choices: `pp`, `cc`, `collar`, default: None = roll all)
to `paper_3track_overlay_roll.py`. When supplied, restrict the roll to legs whose
`leg_role` matches the overlay type pattern (e.g. `overlay_put` for `pp`,
`overlay_call` for `cc`, both for `collar`).

**Files:** `scripts/paper_3track_overlay_roll.py`

**Antigravity handoff:**
> Read `CONTEXT.md` and `src/paper/CLAUDE.md`. `scripts/paper_3track_overlay_roll.py`
> currently rolls all open overlay legs. Add an optional `--overlay` argument
> (choices=["pp", "cc", "collar"], default=None) to filter which overlay type is rolled.
>
> Define a mapping from overlay type to leg_role prefixes:
> `pp → ["overlay_put"]`, `cc → ["overlay_call"]`, `collar → ["overlay_put", "overlay_call"]`.
> When `args.overlay` is set, filter the list of open legs to roll using this mapping before
> passing to the roll logic. When `args.overlay` is None, roll all overlay legs (existing
> behaviour).
>
> Update the `_parse_args()` description and docstring usage block.
>
> Tests: one test with `--overlay pp` only rolls put legs; one test with `--overlay cc`
> only rolls call legs; one test without `--overlay` rolls all. Use fixture trades with
> both put and call overlay legs open.
>
> Run `python -m pytest tests/unit/ --tb=no -q` green.
> Commit: `feat(scripts): add --overlay filter to paper_3track_overlay_roll`

---

### CLI-11 — Clarify `--yes` semantics: confirmation skip vs write gate

**Problem:** `--yes` means two different things across scripts:
- `paper_3track_overlay.py`: "skip interactive confirmation prompt" (write is gated by
  `--no-dry-run` separately).
- `paper_3track_overlay_roll.py`: "write to DB" (the write gate itself — no interactive
  prompt exists in that script).

Same flag name, materially different semantics. After CLI-1 lands (dry-run unification),
`paper_3track_overlay_roll.py` will have `--no-dry-run` as the write gate. At that point
`--yes` in the roll script should be aligned to mean "skip confirmation prompt" only.

**Prerequisite:** CLI-1 must be complete first.

**Files:** `scripts/paper_3track_overlay_roll.py`

**Antigravity handoff:**
> Read `CONTEXT.md`. This task requires CLI-1 (dry-run unification) to be complete first —
> verify `--dry-run / --no-dry-run` already exists in `paper_3track_overlay_roll.py` before
> starting.
>
> Currently in `paper_3track_overlay_roll.py`, `--yes` is used as the write gate
> (i.e. `if not args.yes: return` style guard). After CLI-1, `--no-dry-run` is the write gate.
>
> Refactor `--yes` in `paper_3track_overlay_roll.py` to mean "skip interactive confirmation
> prompt" only, consistent with `paper_3track_overlay.py`. Add a minimal interactive
> confirmation prompt (print proposed changes, ask "Proceed? [y/N]") that `--yes` bypasses.
> The write gate is `--no-dry-run`; `--yes` only controls whether the prompt appears.
>
> This means `--no-dry-run` alone (without `--yes`) should print the prompt and wait.
> `--no-dry-run --yes` skips the prompt and writes immediately.
>
> Update the argparse help text and docstring usage examples.
>
> Tests: assert that `--no-dry-run` without `--yes` triggers the prompt path (mock stdin).
> Assert `--no-dry-run --yes` skips the prompt and proceeds.
>
> Run `python -m pytest tests/unit/ --tb=no -q` green.
> Commit: `fix(scripts): align --yes to mean confirmation-skip in overlay_roll`

---

### CLI-12 — Surface `--notes` in snapshot output

**Problem:** `record_paper_trade.py` records a `--notes` field to the DB on every trade,
but no snapshot script reads or displays it. The field is write-only in the toolchain —
useful context (e.g. "entered at high IVR, slight slippage") is invisible during review.

**Fix:** In `paper_snapshot.py`, when printing per-strategy P&L, append a `Notes:` line
for any open trade that has a non-empty notes field. Pull via
`PaperStore.get_trades(strategy_name)` (already available) and filter for open legs.

**Files:** `scripts/paper_snapshot.py`, optionally `src/paper/store.py` if a
`get_trade_notes(strategy)` helper is warranted.

**Antigravity handoff:**
> Read `CONTEXT.md` and `src/paper/CLAUDE.md`. `PaperTrade` has a `notes: str | None`
> field stored in `paper_trades`. No snapshot script reads it. Surface it in
> `scripts/paper_snapshot.py`.
>
> In `_run()`, after computing P&L for a strategy, call `store.get_trades(name)` and
> collect all non-empty `trade.notes` from open trades (where `trade.closed_at is None`).
> If any notes exist, add a `Notes:` row to the output table (or a footer line below the
> table if UX-6 is already implemented). Format: `Notes: [leg_role] {notes}` per leg,
> deduplicated.
>
> Do not add a `get_trade_notes()` helper unless the logic is non-trivial — inline is fine
> given `get_trades()` already returns the full list.
>
> Tests: mock `store.get_trades()` returning one trade with notes and one without. Assert
> notes line appears in output for the trade with notes. Assert no notes line when all
> trades have null/empty notes.
>
> Run `python -m pytest tests/unit/ --tb=no -q` green.
> Commit: `feat(scripts): surface trade notes in paper_snapshot output`

---

## Phase 1 — Backtest Engine (Aug–Dec 2026, after Phase 0.8 gate)

*Load `BACKTEST_PLAN_PHASE1.md` when Phase 0.8 gate clears. Tasks below are summaries only.*

### Historical Replay Harness for Exit-Path Validation

**Prerequisite for Phase 0.8 gate criterion B (delta/mark-stop and time-stop validation).**

When live paper trading doesn't produce a delta-stop or time-stop exit during the paper window,
the council-approved alternative is a deterministic historical replay against a known stress episode
(COVID week of 2020-03-16 or IL&FS week of 2018-09-21) injected into staging.

**Scope (design doc first — code depends on Phase 1 bhavcopy pipeline):**

- Replay harness injects historical option chain snapshots into `PaperTracker` monitoring loop.
- Must use same strategy logic, data schema, cost model, and P&L attribution code as live paper.
- Output: confirms monitoring daemon correctly identifies the trigger, queues the exit, records P&L.
- Do not build until Phase 1.3a (NSE Bhavcopy pipeline + VIX) data is available.
- Design doc: `docs/plan/replay_harness.md`. No code until Phase 0.8 gate passes.

**Owner:** Animesh + Cowork.

### Underlying OHLC Ingest — Nifty 50, India VIX, NiftyBees (task 1.3a)

Full spec in `BACKTEST_PLAN_PHASE1.md`. Parquet under `data/historical/ohlc/`. Resumable async fetcher.
Derived fields: 14-day ATR, 50-day regression slope, 10-month SMA, 252-day VIX percentile rank.

*Note: the VIX daily sub-path is pulled forward into Task 1 above (IVR gate unblock). The full
1.3a task (Nifty 50 15-min + NiftyBees) remains a Phase 1 item.*

### TrueData 1-min Options Ingestion (task 1.3b)

Full spec in `BACKTEST_PLAN_PHASE1.md`. Start only after TrueData delivers zip files (₹7,999/year, 3-year purchase recommended). Hive-partitioned Parquet at `data/historical/parquet/options/`. ~1.5 GB for 2022–2024.

### Backtest Engine + CSP Calibration (tasks 1.4–1.12)

Full task list in `BACKTEST_PLAN_PHASE1.md`. Key milestones:

- **1.4:** `BacktestEngine` core (Strategy Protocol + DayContext + run loop). Port from `quant-4pc-local`.
- **1.5:** `BacktestStore` — SQLite results storage (separate from `portfolio.sqlite`).
- **1.6a:** BS IV reconstruction from `settle_price` + Nifty Futures forward.
- **1.7:** `CSPStrategy` with `CSPConfig` — thresholds from Stockmock calibration results.
- **1.8:** Full bootstrap run 2016–2024; distribution analysis.
- **1.11:** Regime-matched Z-score (full distribution + stress-window subset). Gate: `|Z| ≤ 1.5` on both.
- **1.12:** Phase 1 gate — paper vs backtest distributions match; Animesh sign-off to start Phase 2.

---

## Phase 2 — Research Pipelines & Integrations (2027+)

*Start only after Phase 1.12 gate. Detailed specs in `PLANNER.md` and `docs/plan/`.*

### P&L Visualization (Cowork artifact)

Deferred until 4+ weeks of snapshot data available (was late May 2026, now at ~6 weeks — revisit).

Deliver as a persistent Cowork artifact (self-contained HTML, re-opens with fresh data via live DB queries). Four panels: MF (`mf_nav_snapshots`), Dhan ETFs (`dhan_holdings_snapshots`), Nuvama Bonds (`nuvama_holdings_snapshots`), Nuvama Options (`nuvama_options_snapshots`). Chart.js or Recharts. Panel 5 (Zerodha) blocked until Kite Connect integration.

**Note:** Now that ~6 weeks of data exists, this is buildable. Move to Task 4 if Animesh confirms priority.

### Zerodha / Kite Connect Integration

Deferred until FinRakshak/ILTS P&L visibility becomes a priority. Hybrid approach: Zerodha free API for position state + Upstox Analytics token for LTP (same pattern as `src/dhan/`). Evaluate Kite MCP server (2025) before writing `src/zerodha/` from scratch.

### Swing Strategy Research Pipeline (Phase 2 Track A)

Full methodology: `docs/plan/SWING_STRATEGY_RESEARCH.md`. Stages 2.S0–2.S7 (regime engine → signal generators → points backtester → option spread backtester → walk-forward → paper → live). Starts after Phase 1.12 gate.

### Investment Strategy Research Pipeline (Phase 2 Track B)

Full methodology: `docs/plan/INVESTMENT_STRATEGY_RESEARCH.md`. Stages 2.I0–2.I5 (SMA / Dual Momentum / PE Band strategies on NiftyBees, ₹5L pool). Zero paid data. Starts after Phase 1.12 gate.

### Order Execution Layer (`src/execution/`)

Blocked: static IP not provisioned. Unblocked when IP is confirmed. `place_order`, `modify_order`, `cancel_order` on `UpstoxLiveClient`; GTT orders; pre-order margin validation via `src/risk/`. All logic already designed against `BrokerClient` protocol.

### paper_snapshot.py → Telegram notification

Wire `build_notifier` from `src/notifications/` into `paper_snapshot.py`. Add `[DRY RUN]` label. Non-fatal, fire-and-forget. Defer until `paper_snapshot.py` is touched for another reason.

### Telegram — Paper Trade Roll Alert (all tracks)

Single unified alert per leg. Fires when **either** condition is met first, then escalates in frequency as DTE shrinks. Not two independent alerts.

---

**Trigger conditions (first one to fire starts the alert cycle):**

- **Condition A — DTE:** `(expiry_date − today).days <= 5`. Applies to all open legs (short and long).
- **Condition B — Decay:** short/sell legs only; `current_premium ≤ entry_premium × 0.25` (≥ 75% of premium captured). Entry premium from `PaperTrade.entry_price`; current premium from daily snapshot LTP.

Whichever fires first determines the alert reason in the message body. If both are true simultaneously, lead with DTE since that's the action-forcing constraint.

---

**Escalating frequency schedule (DTE-driven once alert cycle starts):**

| DTE | Frequency |
|-----|-----------|
| 5–4 | Every other day |
| 3–2 | Daily |
| 1   | Daily, message prefixed with `⚠️ URGENT` |

If Condition B (decay) fires at DTE > 5: send once at the decay trigger date, then go quiet until DTE 5 when the normal escalation schedule kicks in.

Alert cycle ends when `PaperStore` records a close for the leg (roll completed). Re-arms on the replacement leg after a roll.

---

**Message content (minimum):**
- Alert reason: `ROLL DUE (DTE N)` or `DECAY TARGET HIT (X%)` — whichever triggered
- Strategy name, leg label, instrument key, expiry date, current DTE
- For decay alerts: entry premium, current premium, decay %
- Suggested command: `paper_3track_overlay_roll.py` or `paper_csp_roll.py` invocation

---

**Implementation notes:**
- Lives in `paper_snapshot.py` / `paper_3track_snapshot.py`, part of the daily EOD cron.
- Frequency gating requires persisted state: a `paper_alerts` table keyed on `(trade_id, alert_type)` storing `last_sent_date`. Check this before firing to enforce the every-other-day cadence.
- Use `build_notifier` from `src/notifications/`. Non-fatal — log warning on Telegram failure, do not abort snapshot.
- Idempotent: if cron runs twice in a day, alert fires at most once (guard on `last_sent_date == today`).

---

### `paper_alerts` Table — Schema + Audit Trail

New table in `portfolio.sqlite` (shared DB via `src/db.py`). Required before the alert cron logic can be built.

**DDL:**

```sql
CREATE TABLE IF NOT EXISTS paper_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT        NOT NULL,          -- FK to paper_trades.trade_id
    alert_type      TEXT        NOT NULL,          -- 'ROLL_DTE' | 'DECAY_TARGET'
    triggered_by    TEXT        NOT NULL,          -- 'DTE' | 'DECAY' (which condition fired this cycle)
    dte_at_fire     INTEGER,                       -- DTE on the day alert was sent
    decay_pct       REAL,                          -- % decay at fire time (NULL for pure DTE alerts)
    entry_premium   TEXT        NOT NULL,          -- Decimal as TEXT (snapshot of entry_price at fire time)
    current_premium TEXT        NOT NULL,          -- Decimal as TEXT (LTP at fire time)
    last_sent_date  TEXT        NOT NULL,          -- ISO date YYYY-MM-DD (UTC); gate for idempotency + cadence
    sent_count      INTEGER     NOT NULL DEFAULT 1,-- total times this alert has fired for this trade_id + alert_type cycle
    telegram_ok     INTEGER     NOT NULL DEFAULT 1,-- 1 = delivered, 0 = Telegram call failed (logged but non-fatal)
    created_at      TEXT        NOT NULL,          -- ISO datetime UTC; set on first INSERT
    updated_at      TEXT        NOT NULL           -- ISO datetime UTC; updated on every re-fire
);

CREATE INDEX IF NOT EXISTS idx_paper_alerts_trade
    ON paper_alerts (trade_id, alert_type);

CREATE INDEX IF NOT EXISTS idx_paper_alerts_last_sent
    ON paper_alerts (last_sent_date);
```

**Row lifecycle:**
- **First fire:** `INSERT` with `sent_count = 1`, `created_at = updated_at = now`.
- **Re-fire (same cycle):** `UPDATE` — increment `sent_count`, refresh `last_sent_date`, `current_premium`, `dte_at_fire`, `decay_pct`, `telegram_ok`, `updated_at`. Never insert a second row for the same `(trade_id, alert_type)`.
- **Roll / leg close:** do NOT delete the row — it is the audit trail. The alert re-arms on the replacement leg's `trade_id`, which will have its own fresh row.

**Cadence gate logic (pseudo-code):**

```python
row = store.get_alert(trade_id, alert_type)
if row is None:
    fire_alert(); store.insert_alert(...)
elif row.last_sent_date == today:
    pass  # already fired today — idempotent guard
elif dte <= 2 or (dte <= 4 and (today - row.last_sent_date).days >= 2):
    fire_alert(); store.update_alert(...)
# else: too soon, skip
```

**`PaperStore` methods to add:**
- `get_alert(trade_id, alert_type) → PaperAlert | None`
- `upsert_alert(alert: PaperAlert) → None` — insert on first fire, update on re-fire

**`PaperAlert` model:** frozen `dataclass` (same pattern as `PaperNavSnapshot`). Monetary fields (`entry_premium`, `current_premium`) as `Decimal`, stored as TEXT. `last_sent_date` as `datetime.date`. `created_at` / `updated_at` as UTC `datetime`.

**Tests (`tests/unit/paper/test_paper_alerts.py`):**
- Happy path: first fire inserts row, re-fire increments `sent_count` and refreshes `last_sent_date`.
- Idempotency: second call on same day does not update.
- Cadence gate: at DTE 4, skips if `last_sent_date` was yesterday; fires if 2 days elapsed.
- Cadence gate: at DTE ≤ 2, fires regardless of gap.
- Telegram failure: `telegram_ok = 0` recorded, snapshot continues without exception.
- Roll re-arm: closing a leg does not delete the alert row; new leg gets its own fresh row.

---

## Technical Debt

Fix alongside adjacent refactoring only. Never a standalone commit.

### DEBT-3: Missing license boilerplate

License decision needed before automation. Every file should carry a header once the license is chosen.

### DEBT-4: `find_strike_by_delta.py` — `DEFAULT_LOT_SIZE = 75` vs `constants.LOT_SIZE = 65`

`scripts/find_strike_by_delta.py` line 40 defines `DEFAULT_LOT_SIZE = 75`. All 3-track scripts use
`LOT_SIZE = 65` (centralised in `src/paper/constants.py`). Running `find_strike_by_delta.py` without
`--qty` produces dry-run commands with the wrong quantity.

**Fix when touching `find_strike_by_delta.py` next:**
1. Confirm correct lot size against NSE circular.
2. Replace `DEFAULT_LOT_SIZE = 75` with `from src.paper.constants import LOT_SIZE as DEFAULT_LOT_SIZE`.
3. Update the `--qty` help string.

---

## Session Log

| Date | What Changed |
|---|---|
| 2026-05-11 | **Paper Trading CLI & UX audit.** Full audit of 6 paper trading scripts (paper_snapshot, paper_3track_snapshot, paper_3track_overlay, paper_3track_overlay_roll, record_paper_trade, find_strike_by_delta). 12 CLI/UX issues catalogued with Antigravity handoff prompts: CLI-1 (dry-run flag unification), CLI-2 (--spot rename), CLI-3 (--index for roll), CLI-4 (--date type), CLI-5 (--track shortcuts), UX-6 (compact P&L table), UX-7 (summary-first ordering), UX-8 (--verbose flag), UX-9 (shared formatting.py), CLI-10 (--overlay filter for roll), CLI-11 (--yes semantics), CLI-12 (--notes surface). No code changed. |
| 2026-05-10 | **Auto-expiry for CSP entry scripts (SHA 21cd505).** `src/instruments/lookup.py`: added `get_expiry_candidates(underlying, today, preference)` — enumerates NIFTY expiries from BOD JSON into monthly (DTE 15–45) / quarterly (46–200) / yearly (201–420) buckets; default preference `["monthly","quarterly","yearly"]` (CSP income); accepts custom order for hedge use. `scripts/find_strike_by_delta.py`: `--expiry` now optional; when omitted, fetches chains for all candidate expiries and cross-ranks strikes by delta→round-100→spread→OI across the merged pool. `scripts/record_paper_trade.py`: wires same auto-expiry path; `--expiry` now an optional override. 6 unit tests in `tests/unit/instruments/test_expiry_candidates.py`. 58 targeted tests passing. |
| 2026-05-10 | **Markdown sweep.** Archived 2026-05-01 to 2026-05-09 session log + completed bhavcopy P1-NEXT section to `docs/archive/TODOS_ARCHIVE_2026-05-10.md`. Restructured TODOS.md (Task 0–3 sequential queue + Phase 1/2 buckets). Updated BACKTEST_PLAN.md completion log. Updated PLANNER.md completed section. Updated CONTEXT.md date + test count. |

Full log (2026-05-01 → 2026-05-09): [docs/archive/TODOS_ARCHIVE_2026-05-10.md](docs/archive/TODOS_ARCHIVE_2026-05-10.md)
Full log (2026-04-01 → 2026-04-30): [docs/archive/TODOS_ARCHIVE_2026-05-01.md](docs/archive/TODOS_ARCHIVE_2026-05-01.md)
