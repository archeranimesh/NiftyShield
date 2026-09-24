# MVP — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session. Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`. Full story spec for each
> task: `docs/plan/mvp/stories.md`.

---

## ⚠️ Design decisions — resolved 2026-09-18, apply before starting M1

> The story below predates the **capital-deployment** framing (2026-09-09 discussion). Each pick simulates a fixed notional (default ₹1,00,000) deployed in tranches, tracking average cost and rupee
> P&L over a holding period — not just a price-vs-target watch. M1 (schema/models), M2 (tracker), and M4 (watch) need rewriting against the decisions here before implementation. `schema.md` gains a
> `mvp_tranches` table and new `mvp_recommendations` columns (`capital_allotted`, `tranche_step_pct`, `deployed_capital`, `total_qty`, `avg_cost`, `realized_pnl`, `benchmark_entry`, `idle_cash`).

**Resolved (2026-09-09):**
- **Tranche ladder** — fixed, measured from the recommendation price (not the running average). `tranche_step_pct` default **6**. Four 25% tranches fill at 0%, −6%, −12%, −18% → 100% deployed by −18%.
- **Stop-loss semantics** — the averaging ladder *is* the strategy. The tipster's `stop_loss` is recorded but **not acted on**. Hard stop instead: full exit when the blended position is **−30% on
  fully deployed capital** (`max_drawdown_pct` default 30).

**Resolved (2026-09-18):**
1. **Whole shares + residual cash** — floor to integer qty on each tranche fill. Leftover cash from the floor tracked as `idle_cash` on the pick and counted in the deployed-capital return denominator
   (so rounding residue doesn't distort return %). Residual does **not** roll into the next tranche — each tranche fills independently off its own fixed 25% slice.
2. **Cost model** — flat **25 bps** round-trip knob applied per transaction: on each tranche entry fill and again on exit. Not a single per-pick charge.
3. **Benchmark alpha** — `benchmark_entry` (NIFTY 50 level) captured via a **live** spot fetch at pick add-time (reuse the `_fetch_nifty_spot` pattern from
   `scripts/strategies/three_track/paper_3track_overlay_entry.py`), so M1/M2 have no historical-data dependency. Historical alpha and the M6 backfill path both need historical NIFTY index + equity
   closes, which **do not exist yet**: `src/backtest/bhavcopy_ingest.py` only ingests F&O derivatives records (strikes, expiries, OI) — no equity cash-market close, no index level. A new equity +
   index bhavcopy ingest is a prerequisite for **M6 only** (see new **M0** task below); it does not block M1–M5.
4. **Time stop** — mark-to-market exit at **N = 6 months** if neither target nor the −30% drawdown hard stop has hit.
5. **Capital-efficiency metric** — max % deployed per pick, reported only, not a gate. No schema fields beyond what the tranche table already carries.
6. **Portfolio mode** — independent ₹1L notional per pick only (pick-quality view). Shared pool with a concurrent-position cap is explicitly **out of MVP scope**.
7. **Phasing** — **M-A** (lump-sum: single fill `qty = capital / price` at recommendation price) ships first to deliver the benchmark-alpha table sooner; **M-B** (staggered 4-tranche ladder) ships
   after. `mvp_tranches` table exists from M1 onward, but M2's `check_prices`/tracker logic only handles the single M-A fill until M-B lands — M-B tasks are appended to this checklist once M-A is
   complete.
8. **Schema council (Step 2b)** — resolved **without** a real council call. This is a personal paper-tracking tool with no live capital or `BrokerClient` execution path; the schema is
   migration-reversible, and the load-bearing strategy decisions (tranche ladder, hard-stop semantics) were already settled in the 2026-09-09 discussion above.
9. **Dividends** — out of scope for MVP; note this in the `Pick`/tranche model docstring.

**Infra corrections already identified (see chat 2026-09-09):**
- M4.1 LTP path: use `BrokerClient.get_ltp()` via `factory.create_client` (as `src/paper/tracker.py` does) — **not** the non-existent `src/dhan/ltp_fetcher.py`.
- M2.2 / M4.2 Telegram: use `parse_mode=MarkdownV2` via `src/notifications/formatting.py`
  + `markdown.py` escaping per `FORMATTING.md` — the HTML framing is stale (migration archived 2026-09-06).

---

- [x] **M1.1** — `src/mvp/models.py`: Provider, Category, Pick, MVPSnapshot Pydantic models + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 90fa0af
- [x] **M1.2** — `src/mvp/store.py`: init_db + provider/category CRUD + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 14700c3
- [x] **M1.3** — `src/mvp/store.py`: pick CRUD + snapshot methods + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 44c8408
- [x] **M2.1** — `src/mvp/tracker.py`: MVPEvent + check_prices pure logic + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: af5ea2a
- [x] **M2.2** — `src/mvp/tracker.py`: format_telegram_summary + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 77e9d53
- [x] **M3.1** — `scripts/mvp.py`: provider + category subcommands | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: e89f205
- [x] **M3.2** — `scripts/mvp.py`: add + update + close subcommands (with instrument resolution) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 74b84c8
- [x] **M3.3** — `scripts/mvp.py`: list + summary subcommands | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 731529b
- [x] **M4.1** — `scripts/mvp_watch.py`: LTP fetch + snapshot recording + auto-close | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 8fbe496
- [x] **M4.2** — `scripts/mvp_watch.py`: Telegram per-alert + consolidated hourly summary | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 6ed6aa9
- [x] **M0** — Equity + NIFTY index bhavcopy ingest (prerequisite for M6/M8 — not M1–M5). `src/backtest/bhavcopy_ingest.py` is F&O-only today; add equity cash-market daily close + NIFTY 50 index level
  ingest. **Storage — resolved 2026-09-23: Parquet, not portfolio.sqlite** (`equity_ohlcv/` and `nifty_index/` dirs under `data/offline/`, same `write_to_parquet` idempotent-append pattern and
  `year/month` partitioning already used for `options_ohlcv/`/`futures_ohlcv/`), consistent with the existing F&O ingest — bulk historical time-series stays out of the transactional/state SQLite DB.
  Two new NSE fetchers (mirroring `fetch_bhavcopy`/`download_bhavcopy`): equity daily close from the CM bhavcopy (`scratch/2026-09-23_mvp_m0_data_source_probe.py`,
  `BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip`), NIFTY 50 index daily close from the index-close bhavcopy (`scratch/2026-09-23_mvp_m0_nifty_index_probe.py`, `ind_close_all_DDMMYYYY.csv`). **Equity
  scope — resolved 2026-09-23: watchlist-filtered, not the full NSE universe.** Mirrors the F&O ingest's own `underlying="NIFTY"` filter in `parse_bhavcopy` — parse each day's CM CSV but keep only
  rows whose symbol is in `MVPStore`'s distinct `mvp_recommendations.symbol` set at ingest time (a `symbols: set[str]` param threaded from the CLI, not a live query inside the parser). Keeps the
  Parquet tiny; adding a new tipster pick later just means re-running the backfill CLI for that one symbol's date range, same manual-CLI shape as M0 itself. The NIFTY 50 index file has no equivalent
  filter — it's one row per day, always ingested whole. M8 reads these Parquet files directly (not via `MVPStore`) for its backfill walk and `benchmark_close` lookup. **Scheduling — resolved
  2026-09-23: manual `--start`/`--end` CLI only, no cron**, mirroring `scripts/pipeline/bhavcopy_bootstrap.py` (which itself has no cron entry — confirmed via `crontab -l`, F&O bhavcopy is backfilled
  by hand today, not scheduled). Nothing in current MVP scope needs daily-fresh closes: live-forward entry/watch use intraday `BrokerClient.get_ltp`, and day-by-day `benchmark_close` is backfill-only
  (open point 5 — live-watch snapshots stay `NULL`). A daily cron only becomes necessary if day-by-day alpha is later extended to live picks (that follow-on, not this task) — noted here so it isn't
  lost, not drafted as a task. **Broken into M0.1–M0.4 below (2026-09-23), each its own commit — mirrors the M1.1–M1.3/M4.1–M4.2 split.**

- [x] **M0.1** — `src/mvp/store.py`: `MVPStore.get_distinct_symbols() -> set[str]` (SELECT DISTINCT `symbol` from `mvp_recommendations`) + happy-path test (multiple picks, some duplicate symbols) +
  edge test (empty table → empty set). Threaded into M0.4's bootstrap CLI as the equity-ingest symbol filter — not queried live inside the parser (decision above). | Owner: Claude | Model:
  claude-sonnet-5 | Review: code-reviewer | SHA: 86bdd0b
- [x] **M0.2** — `src/backtest/equity_bhavcopy_ingest.py` (new module): `EquityBhavRecord` frozen Pydantic (`trade_date`, `symbol`, `close: Decimal`); `download_equity_bhavcopy(trade_date, dest_dir)
  -> Path` (CM UDiFF zip, same session/cookie pattern as `download_bhavcopy`, `FileNotFoundError` on 404); `parse_equity_bhavcopy(csv_path, symbols: set[str]) -> list[EquityBhavRecord]` (filters to
  the given symbol set); `write_equity_to_parquet(records, month_date, dest_dir)` (idempotent append, `year/month` partitioning, `decimal128(18,4)` schema for `close`, mirrors `write_to_parquet`). New
  fixture `tests/fixtures/responses/bhavcopy/synthetic_equity_bhavcopy.csv` (UNIPARTS + 1–2 other symbols). Tests mirror `test_bhavcopy_ingest.py`'s structure (parse happy-path + filter-excludes +
  Decimal-fields + write idempotency, download mocked via `unittest.mock.patch`). No CLI wiring yet (M0.4). | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 5322a2d
- [x] **M0.3** — same module, `src/backtest/equity_bhavcopy_ingest.py`: `IndexBhavRecord` frozen Pydantic (`trade_date`, `close: Decimal`); `download_index_bhavcopy(trade_date, dest_dir) -> Path`
  (plain unzipped `ind_close_all_DDMMYYYY.csv`, same session pattern); `parse_index_bhavcopy(csv_path) -> IndexBhavRecord | None` (extracts the `Nifty 50` row only, `None` if absent);
  `write_index_to_parquet(records, month_date, dest_dir)` (`data/offline/nifty_index/`, `decimal128(18,4)` schema). New fixture `tests/fixtures/responses/bhavcopy/synthetic_index_close.csv`. Tests:
  happy-path parse, no-`Nifty 50`-row edge case, write idempotency. | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: 27ff5f8
- [x] **M0.4** — `scripts/pipeline/equity_bhavcopy_bootstrap.py` (new script): manual `--start`/`--end`/`--dest` CLI (default `data/offline`), no cron entry (decision above). Pulls the equity symbol
  filter via `MVPStore.get_distinct_symbols()` at startup (once, not per-day). Walks calendar days from `--start` to `--end`, skips weekends + `get_nse_holidays()` (same pattern as
  `bhavcopy_bootstrap.py`), calls `download_equity_bhavcopy`/`parse_equity_bhavcopy`/`write_equity_to_parquet` and `download_index_bhavcopy`/`parse_index_bhavcopy`/`write_index_to_parquet` per trading
  day, `FileNotFoundError` → log-and-skip (holiday), other exceptions logged not raised (per-day resilience, mirrors `bhavcopy_bootstrap.py`). Tests (in
  `tests/unit/backtest/test_equity_bhavcopy_ingest.py`, mirroring how `bootstrap_main` is tested alongside `bhavcopy_ingest.py`): happy-path over a 2–3 day mocked range, holiday-skip edge case. M0
  fully done once this lands — no separate M0 checklist tick needed beyond M0.4's. | Owner: Antigravity | Model: Gemini | Review: code-reviewer | SHA: d85523a
- [x] **M6** — generic historical-backfill primitives (`MVPStore.backfill_snapshots`, `src/mvp/backfill.py:fetch_historical_closes`, `scripts/mvp.py backfill` for already-entered picks); **rewritten
  2026-09-23** against M0's real `data/offline/equity_ohlcv/` Parquet layout, explicitly scoped apart from M8 (M6 = snapshot backfill + breach detection for a known `entry_price`; M8 = entry
  *determination* for an unresolved `entry_price`, Uniparts flow). Unblocked — depends only on M0, not M7. See full spec: `stories.md`. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer
  | SHA: 499d382
- [x] **M7** — `src/mvp/models.py` + `src/mvp/store.py`: add `reco_price: Decimal | None` to `Pick` (recommendation-quoted price, distinct from `entry_price`, the price we actually recorded entering
  at). `scripts/mvp.py`: `add` gains `--reco-price` (settable at creation, not only via later `update`, so fresh picks always carry it); `update` also accepts `--reco-price` for correction.
  `summary`/`list` show entry-vs-reco deviation (`(entry_price - reco_price) / reco_price`) computed on read — no stored deviation column. No migration needed — DB is freshly seeded, so every pick
  from here on is created with both fields. | Owner: Antigravity | Model: Gemini | Review: code-reviewer | SHA: d2f60d2
- [x] **M8** — Backfill entry + walk-forward for a past reco (blocked on M0 landing; full spec is the canonical Uniparts worked example above — implement and run that pick end-to-end as this task's
  acceptance test, do not derive a separate one). Uniparts acceptance run passed clean 2026-09-23: entry ₹659.70 (2026-06-12 close, next trading day after reco > reco_price 640.10), TARGET_HIT at
  ₹873.15, +3.06% entry-vs-reco deviation, `mvp summary`/`summary -p/-c`/`list --all` all show a single clean pick. Three duplicate/orphan picks created during Antigravity's earlier failed attempts
  were found and deleted from the live DB (pick_ids 58a62b12/3c4e4e56/06057ce7) — the no-duplicate-pick-guard WARNING flagged in Phase D review materialized for real; a dedup/idempotency guard on the
  `backfill` CLI is deferred, not fixed. New `src/mvp/backfill.py`: `enter_backfill_pick(pick, closes)` — the backfill half of the entry rule only (next trading day's close after `reco_date`; enter at
  that close if it's above `reco_price`, else the pick stays unentered, no re-check). `run_backfill(pick, closes)` — walk daily equity closes (M0's ingested table) from entry date to today, one
  `MVPSnapshot` per trading day via `store.record_snapshot`, auto-exit (`store.close_pick`) on the first day a close crosses `target_price` or `stop_loss`, no snapshots past the exit day. Resolves
  stories.md open point 5 (day-by-day alpha, not entry/exit-only): each `MVPSnapshot` also carries that day's `benchmark_close` (NIFTY 50 index close from M0's ingested table, same trading-day walk) —
  `src/mvp/models.py` `MVPSnapshot` gains `benchmark_close: Decimal | None = None`, `src/mvp/store.py` `record_snapshot` persists it (`schema.md` `mvp_snapshots.benchmark_close`, nullable — `NULL` for
  existing/live-watch snapshots, populated only by M8's backfill path for now). The live-watch path (M4.1, already shipped) is **not** touched by this task — wiring `benchmark_close` into
  `scripts/mvp_watch.py`'s hourly snapshots is a separate follow-on if day-by-day alpha is wanted for live picks too. The live-forward half of the entry rule (poll `BrokerClient.get_ltp`, enter at
  first tick above `reco_price`) is **not** part of this task — `scripts/mvp_watch.py`'s existing hourly cron already covers live picks once entered; M8 is backfill-only. `scripts/mvp.py` gains a
  `backfill` subcommand wiring `pick_date` to `reco_date` (not "now", unlike `add`). Depends on M0 (equity daily-close table) and M7 (`reco_price` field). | Owner: Antigravity | Model: n/a | Review:
  code-reviewer | SHA: cc42392
- [x] **M9** — M-A lump-sum fill math (resolves stories.md open point 2). `src/mvp/store.py`: `update_pick`'s existing PENDING→OPEN auto-advance (on `entry_price` being set) also computes and persists
  the fill in the same call: `total_qty = floor(capital_allotted / entry_price)`, `deployed_capital = total_qty * entry_price`, `avg_cost = entry_price`, `idle_cash = capital_allotted -
  deployed_capital` (2026-09-18 decision #1 — residual does not roll into a later tranche, M-A has only one fill). Apply the 25 bps round-trip cost knob (decision #2) on this entry fill, capitalized
  into `avg_cost` (not `deployed_capital`, so `idle_cash` stays the untouched residual). `close_pick`: compute `realized_pnl = (close_price * (1 - 25bps) - avg_cost) * total_qty` on the terminal
  transition. `scripts/mvp.py`: `summary`/`list` surface `deployed_capital`, `avg_cost`, `realized_pnl`, and return% (`realized_pnl / deployed_capital` when closed, unrealized `(ltp - avg_cost) *
  total_qty / deployed_capital` when open — unrealized needs an `ltp_map` param threaded through, same as `check_prices`). Out of scope: `mvp_tranches` table population (M-B), `benchmark_entry`/alpha
  display (separate, decision #3). | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 56f38e2
- [ ] **M5** — Docs close: CONTEXT.md tree, DECISIONS.md entry, TODOS.md session log. **Reordered 2026-09-23 (Animesh): moved to after M6–M9** so the docs-close reflects the fuller shipped state
  (backfill, `reco_price`, and the M-A fill-math/P&L surfacing) rather than closing docs against the bare M1–M5 ship bar before those land. **2026-09-24 addition to M5's scope:** register the
  already-coded `scripts/mvp_watch.py` hourly cron in the live crontab — M4.1/M4.2 shipped the script (its own docstring documents `Cron schedule: 0 9-15 * * 1-5`) but `crontab -l` was found to have
  no MVP entry at all; the watch loop has never actually run on a schedule. Add the entry (with a comment block matching the style of the other `# NEW`/dated cron comments) and note it in
  `CONTEXT.md`'s "Live Data" cron list as part of this task's docs update. | Owner: Claude | Model: n/a | Review: none | SHA: —

## Follow-on tasks — surfaced 2026-09-24 reviewing `scripts/mvp_watch.py`'s Telegram messages against `exit_message.py`'s IC-close format

> Comparing MVP's alert message to the richer IC v2 close message (headline → kv line → fenced Act/Instrument/Entry/Exit/P&L table → `━━━` separator → Inception/win-rate footer,
> `src/notifications/exit_message.py`) surfaced a real gap, not just a style mismatch: M9 (`SHA: 56f38e2`) added real ₹ P&L math (`realized_pnl`, `total_qty`, `deployed_capital`, `avg_cost`) to
> `close_pick`/`scripts/mvp.py summary`/`list`, but M4.2's alert message (`SHA: 6ed6aa9`, predates M9) was never updated to use it — `_format_alert_message` in `scripts/mvp_watch.py` still only shows
> raw entry/exit price and a price-only percent, not the actual rupee P&L the pick realized. Both items below are new, unscoped work — not part of the M1–M9 ship bar already delivered.

- [x] **M10** — Real ₹ P&L in the MVP alert message. `close_pick` (`src/mvp/store.py`) currently computes `realized_pnl` but discards it (writes to DB, returns `None`) — change it to return the
  computed `realized_pnl` (and thread back `total_qty`/`deployed_capital`/`avg_cost`, already columns on the row it reads) so `mvp_watch.py` can use them without a second read. Redesign
  `_format_alert_message` to match the IC exit-message visual language at MVP's smaller scale (single instrument, no legs, no cycles): headline → `Provider / Category Held: Nd` kv line → fenced `Entry
  / Exit / P&L` table (use `format_money`/`FORMATTING.md`'s confirmed fence-safe `₹`) → `━━━` separator → a footer line with return %, qty, deployed capital. `held_days` computed from `pick_date` to
  now. No new store aggregate query needed — every value already exists on the `Pick` row at close time. | SHA: b812d82
- [x] **M11 (Good-to-Have, blocked on M10 — M10 now signed off, unblocked)** — IC-style stats footer: win-rate and inception P&L per provider/category, appended under M10's alert footer the way
  `exit_message.py` appends `📈 Inception` / `🎯 Win rate` under its cycle line. Needs a **new** `MVPStore` aggregate query across a category's closed picks (win count / loss count / sum of
  `realized_pnl` / avg win / avg loss) that does not exist today — bigger scope than M10, deliberately not bundled into it. Design open point: whether "inception" scopes to the category, the provider,
  or all MVP picks combined — resolved 2026-09-24 with Animesh: **per category** (`CategoryStats`, `MVPStore.get_category_stats(category_id)`), matching M13's planned per-category columns most
  directly. **Now also feeds M13's per-category `Win%`/`Incep%` columns** — both were prototyped with fixture placeholder values (2026-09-24) since this query doesn't exist yet; building M11 for real
  is a prerequisite for M13's table to show live numbers instead of fixtures. Gated to categories with >=5 closed picks, matching `exit_message._win_rate_line`'s precedent. | SHA: 3c331b8
- [x] **M12 (design re-finalized 2026-09-24 — column set settled and confirmed on-device against the 50-char budget, ready to implement)** — Rewrite of the consolidated hourly summary message. |
  Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 2b8d75d Original problem: `_format_row` (`src/mvp/tracker.py:81`) space-joins variable-width parts (symbol, `T:1500 (7.1% away)`
  as one compound cell) that never line up into columns despite sitting in a fence — violates `FORMATTING.md` §2 ("every cell in a column carries the same precision and the same width, or it stops
  being a column"). It also renders in-fence Chg% via bare `format_pct()`, which drops the trailing `.0` on whole numbers, violating §3's "fenced percent: always 1dp, always signed" rule.

**Design finalized 2026-09-24** in `scratch/2026-09-24_mvp_telegram_message_survey.py`, function `format_hourly_summary` and helpers:
  - **Single flat table**, no provider/category grouping (Animesh's explicit call over the original per-category-fenced-blocks structure).
  - **Broker-holdings-style columns**, inspired by a pasted Upstox holdings screenshot: `[badge] Instrument Qty Avg cost LTP P&L Chg%`. Column widths computed per-group, same pattern as
    `build_close_leg_table` (`src/notifications/formatting.py`). **`Day chg%` deliberately excluded** — MVP has no previous-close baseline stored anywhere today (checked: `mvp_snapshots` is hourly
    ticks only, no day-open row); revisit only if that data need becomes real. **`Cur val` also dropped** (mobile-width sign-off, same session) — it's just Qty × LTP, recoverable from the other
    columns, and was the single widest cell; cutting it took the table from 80 chars to 65.
  - **Final column set, re-settled 2026-09-24 against the confirmed 50-char budget**: `[badge] Sym LTP P&L Next` — 48 chars, confirmed rendering correctly on-device via `--send --send-only Hourly`.
    Core `badge`/`Sym`/`LTP`/`P&L` alone is 38 chars; every 2-optional-column combination that also keeps `Next` (target/SL proximity) — `Svc`+`Next`, `Qty`+`Next` — comes out at 53 chars, over
    budget, so only one optional column could be kept alongside the core four. Measured every 0/1/2-column combination of `Svc`/`Qty`/`Avg cost`/`Chg%`/`Next` against the real fixture data in
    `scratch/2026-09-24_mvp_telegram_message_survey.py`; `Next` alone (48 chars) and `Svc`+`Qty` (48 chars) tied for the widest combo that still fit — Animesh chose `Next` alone, since it's the
    regression-restore column (see the `_next_level_str` note below) rather than a nice-to-have, over `Svc` (provider disambiguation) and `Qty`/`Avg cost`/`Chg%`. `Svc`, `Qty`, `Avg cost`, and `Chg%`
    are all dropped from the final table.
  - **`[O]`/`[P]` status badge folded into the table itself** (leftmost column) instead of a separate trailing "Unassigned (PENDING)" block — a PENDING row shows `—` for every value column (no fill
    yet).
  - **Headline**: `{emoji} *MVP Open positions* | {run_time}` — emoji is a net-P&L color signal (🟢 positive / 🔴 negative / ⚪ zero) computed over OPEN picks only. Fence-width alignment concerns that
    reject 🔴 elsewhere (`FORMATTING.md` §7, ROLL-2a) don't apply here since this sits outside any fence. Emoji/wording set signed off as-is 2026-09-24 — no changes requested.
  - **Footer**: `Invested` / `Current` / `P&L` each on their own bold-labeled line (💰/📊/📈), IC-`exit_message.py`-style bold `*Label:*` prefixes — **explicitly scoped to currently OPEN picks only**
    (unrealized, mark-to-market). Confirmed 2026-09-24: does **not** fold in `realized_pnl` from already-closed picks — that stays a separate, deferred "Inception" line (folds into **M11** if built,
    not this task). Trailing plain line: `Open: n Pending: m`.
  - Two intentional departures from `FORMATTING.md` as currently written, both documented inline in the prototype: (1) `Away%`-style distance metrics (not used in the final v4 shape, but noted for any
    future column) stay unsigned rather than following §3's fenced "always signed" literally — same exception class §3 already grants IVR; (2) the footer's signed-percent prose value is built with a
    manual `+`/`-` prefix, not `FORMATTING.md`'s documented `format_pct_signed()` — **that function doesn't exist anywhere in `src/notifications/formatting.py`**, a doc/code mismatch worth fixing
    separately (either implement it or correct the doc), not blocking this task.
  - **Ships as its own commit, separate from M10** — confirmed 2026-09-24, per Step 5c's rule against bundling separate-phase changes into one commit.
- [x] **M13 — design signed off 2026-09-24** (see "M12 design closed out" note below; M11 shipped, so the Win%/Incep% blocker is cleared). New end-of-day summary message, distinct from M12's hourly
  view. Groups by provider → sub-type category (e.g. DSIJ: Value Picks / Multibagger / TAS; FinnovationZ: Ikashi), one aggregated row per category, plus an all-recommendations footer. **Scoped
  2026-09-24 into four sub-tasks** (all three data gaps below to be shipped in this pass, not deferred):
  - [x] **M13.1** — `src/mvp/store.py`: extend the category rollup to produce `inception_pct` (realized + unrealized, since the category's first pick) — combine M11's `get_category_stats` realized P&L
    with a new invested/current sum over that category's open picks. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: df9001a
  - [x] **M13.2** — `src/mvp/store.py`: `MVPStore.get_category_day_change(category_id)` — diff each pick's latest snapshot vs. its prior-trading-day snapshot, invested-weighted roll-up per category
    (also feeds the all-recs footer's `Day chg`). | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 1a5d9dd
  - [x] **M13.3** — `src/mvp/store.py`: `MVPStore.get_category_high_low(category_id)` — cumulative-return time series per category from snapshot history, running high-water-mark / max-drawdown →
    `high_pct`/`low_pct`. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 0b63904
  - [x] **M13.4** — Port `format_eod_summary`/`build_eod_table`/`CategoryRollup`/`ProviderRollup` from `scratch/2026-09-24_mvp_telegram_message_survey.py` into `src/mvp/tracker.py`, wire real data
    from M13.1–13.3 into `scripts/mvp_watch.py`'s EOD path (new cron entry — `mvp_watch.py` today only runs hourly 9-15, no EOD invocation exists). Each sub-task ships as its own commit (Model → Store
    → wiring boundary, Step 5c) with its own tests. `Category.slug` has no dedicated short-code column — `category_short_code()` derives one (multi-word initials / single-word 3-char truncation, not
    guaranteed unique — Animesh's call, 2026-09-24) rather than adding a schema migration. `run_eod()` itself is integration-only, untested (same precedent as `run()`, M4.1); the pure builders it
    calls are fully unit-tested. New cron entry (`45 15 * * 1-5`, `mvp_watch.py --eod`) not yet added to the actual crontab — code-only this session. | Owner: Claude | Model: claude-sonnet-5 | Review:
    code-reviewer | SHA: 71bca0a, e7cdda0

**Design finalized 2026-09-24** in `scratch/2026-09-24_mvp_telegram_message_survey.py`, function `format_eod_summary` + `build_eod_table` + `CategoryRollup`/`ProviderRollup`:
  - **Headline**: `{emoji} *MVP EOD Summary* | {date}` — same net-P&L color-emoji convention as M12's headline.
  - **One shared fenced table across every provider** (`build_eod_table`), columns `Cat / P&L / Win% / Incep% / High / Low`, no `Prv`/provider column — category short_codes (`VP`/`MB`/`TAS`/`IKA`)
    don't collide across providers, so a separate provider tag wasn't needed. `Invested`/`Current` deliberately dropped (Animesh's call) — this is a per-service scorecard, not a position-level view
    (M12 already covers that). `Win%` shows the closed-picks sample size inline (`67% (3)`, or `— (0)` when there are none yet) since a bare percentage/dash hides the sample size behind it.
  - **Design evolved through two structural changes, both on-device-driven**: first pass used one fenced table *per provider*; Animesh's phone showed a single-category provider's own short 3-line
    block (header/separator/1 row) rendering in a visibly larger font than a longer multi-row block, wrapping despite having fewer characters per line — looks like Telegram auto-scales very short code
    blocks. Fix: merged every provider's categories into one shared table (removes the short-block case entirely), then dropped the `Prv` column it briefly needed, closing the remaining gap to the
    confirmed mobile-safe width. Confirmed rendering correctly on-device 2026-09-24.
  - **Mobile-safe width empirically confirmed at 50 chars** (not the ~55-65 estimate used earlier this session) via a calibration probe (`_width_ruler()` in the same scratch file, sent with `--send
    --send-only Width`) — a ruled block from 30 to 80 chars in steps of 5; the longest line that renders without wrapping on the actual device is the real number. The final merged table is 49 chars,
    under this limit. **M12's hourly table was re-measured against this confirmed 50-char number** (2026-09-24, later same day) — the final column set (`badge`/`Sym`/`LTP`/`P&L`/`Next`) came in at 48
    chars, confirmed rendering correctly on-device. See M12's entry for the column-selection tradeoff.
  - **All-recommendations footer**: `💰 All recs P&L` / `📅 Day chg` / `🚀 Since inception`, rolled up across every category row (day-chg is invested-weighted across categories).
  - **P&L scope confirmed 2026-09-24: realized + unrealized combined**, not M12's open-only scope. Both the per-category `P&L` column and the footer's `All recs P&L` use `_rollup_pnl` = `(current −
    invested) + realized_pnl` — category rows sum exactly to the footer total. No signed `%` is shown next to `All recs P&L` (unlike M12's open-only P&L, which has a clean `pnl / invested` base) —
    once realized capital returned by closed picks is folded in, `total_invested` stops being the right denominator; `Since inception %` is the relative-return figure for this combined scope instead.
  - **`High`/`Low` columns** — the category's since-inception running high-water-mark / max-drawdown return% (Animesh's call: NOT today's best/worst individual pick — a strategy-level equity-curve
    metric).
  - **Three data gaps, now scoped into M13.1–13.3 above (2026-09-24)** — `Win%`/`Incep%`/`realized_pnl`/`High`/`Low` per category and the overall `Day chg`/`Since inception` footer are all prototyped
    with **fixture placeholder values**, not live data: (1) per-category `win_rate` and realized `P&L` already come from M11's `get_category_stats` (`src/mvp/store.py:496`) — M13.1 adds the missing
    unrealized leg (open-pick invested/current) to turn that into `inception_pct`; (2) day-over-day change needs a yesterday's-EOD-vs-today's-EOD snapshot diff per pick, invested-weighted per category
    — `get_snapshots()` returns the raw rows but nothing aggregates the diff yet, hence M13.2; (3) `High`/`Low` need a running cumulative-return time series per category (high-water-mark /
    max-drawdown), not just current state — the heaviest of the three, hence its own M13.3.
  - **`vs Nifty` alpha line and Open/Pending/Closed counts added** (co-investor review pass, 2026-09-24) — `vs Nifty` is fixture-only: `MVPSnapshot.benchmark_close` exists on the model but
    `scripts/mvp_watch.py` never populates it on a live run today, so no real index-return series exists to diff against; wiring that up is new work, not sized. Open/Pending/Closed counts are pure
    arithmetic over existing `Pick.status` — no new query needed, real whenever M13 is implemented.

**M12 design closed out 2026-09-24 (resumed session)**: all three of M10/M12/M13 are now fully signed off and confirmed rendering correctly on-device. M12's final column set
(`badge`/`Sym`/`LTP`/`P&L`/`Next`, 48 chars) is documented in M12's entry above. **Next up: implement M10/M12/M13 for real** — `src/mvp/tracker.py` (`_format_row`) and `scripts/mvp_watch.py` currently
ship none of this; the scratch prototype functions are the reference shape to port over, per each entry's DoD.
