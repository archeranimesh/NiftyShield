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
- [ ] **M0** — Equity + NIFTY index bhavcopy ingest (prerequisite for M6/M8 — not M1–M5). `src/backtest/bhavcopy_ingest.py` is F&O-only today; add equity cash-market daily close + NIFTY 50 index level
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
- [ ] **M0.3** — same module, `src/backtest/equity_bhavcopy_ingest.py`: `IndexBhavRecord` frozen Pydantic (`trade_date`, `close: Decimal`); `download_index_bhavcopy(trade_date, dest_dir) -> Path`
  (plain unzipped `ind_close_all_DDMMYYYY.csv`, same session pattern); `parse_index_bhavcopy(csv_path) -> IndexBhavRecord | None` (extracts the `Nifty 50` row only, `None` if absent);
  `write_index_to_parquet(records, month_date, dest_dir)` (`data/offline/nifty_index/`, `decimal128(18,4)` schema). New fixture `tests/fixtures/responses/bhavcopy/synthetic_index_close.csv`. Tests:
  happy-path parse, no-`Nifty 50`-row edge case, write idempotency. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **M0.4** — `scripts/pipeline/equity_bhavcopy_bootstrap.py` (new script): manual `--start`/`--end`/`--dest` CLI (default `data/offline`), no cron entry (decision above). Pulls the equity symbol
  filter via `MVPStore.get_distinct_symbols()` at startup (once, not per-day). Walks calendar days from `--start` to `--end`, skips weekends + `get_nse_holidays()` (same pattern as
  `bhavcopy_bootstrap.py`), calls `download_equity_bhavcopy`/`parse_equity_bhavcopy`/`write_equity_to_parquet` and `download_index_bhavcopy`/`parse_index_bhavcopy`/`write_index_to_parquet` per trading
  day, `FileNotFoundError` → log-and-skip (holiday), other exceptions logged not raised (per-day resilience, mirrors `bhavcopy_bootstrap.py`). Tests (in
  `tests/unit/backtest/test_equity_bhavcopy_ingest.py`, mirroring how `bootstrap_main` is tested alongside `bhavcopy_ingest.py`): happy-path over a 2–3 day mocked range, holiday-skip edge case. M0
  fully done once this lands — no separate M0 checklist tick needed beyond M0.4's. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **M5** — Docs close: CONTEXT.md tree, DECISIONS.md entry, TODOS.md session log | Owner: Claude | Model: n/a | Review: none | SHA: —
- [ ] **M6** — see full spec below (Good-to-Have, blocked on M0) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **M7** — `src/mvp/models.py` + `src/mvp/store.py`: add `reco_price: Decimal | None` to `Pick` (recommendation-quoted price, distinct from `entry_price`, the price we actually recorded entering
  at). `scripts/mvp.py`: `add` gains `--reco-price` (settable at creation, not only via later `update`, so fresh picks always carry it); `update` also accepts `--reco-price` for correction.
  `summary`/`list` show entry-vs-reco deviation (`(entry_price - reco_price) / reco_price`) computed on read — no stored deviation column. No migration needed — DB is freshly seeded, so every pick
  from here on is created with both fields. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **M8** — Backfill entry + walk-forward for a past reco (blocked on M0 landing; full spec is the canonical Uniparts worked example above — implement and run that pick end-to-end as this task's
  acceptance test, do not derive a separate one). New `src/mvp/backfill.py`: `enter_backfill_pick(pick, closes)` — the backfill half of the entry rule only (next trading day's close after `reco_date`;
  enter at that close if it's above `reco_price`, else the pick stays unentered, no re-check). `run_backfill(pick, closes)` — walk daily equity closes (M0's ingested table) from entry date to today,
  one `MVPSnapshot` per trading day via `store.record_snapshot`, auto-exit (`store.close_pick`) on the first day a close crosses `target_price` or `stop_loss`, no snapshots past the exit day. Resolves
  stories.md open point 5 (day-by-day alpha, not entry/exit-only): each `MVPSnapshot` also carries that day's `benchmark_close` (NIFTY 50 index close from M0's ingested table, same trading-day walk) —
  `src/mvp/models.py` `MVPSnapshot` gains `benchmark_close: Decimal | None = None`, `src/mvp/store.py` `record_snapshot` persists it (`schema.md` `mvp_snapshots.benchmark_close`, nullable — `NULL` for
  existing/live-watch snapshots, populated only by M8's backfill path for now). The live-watch path (M4.1, already shipped) is **not** touched by this task — wiring `benchmark_close` into
  `scripts/mvp_watch.py`'s hourly snapshots is a separate follow-on if day-by-day alpha is wanted for live picks too. The live-forward half of the entry rule (poll `BrokerClient.get_ltp`, enter at
  first tick above `reco_price`) is **not** part of this task — `scripts/mvp_watch.py`'s existing hourly cron already covers live picks once entered; M8 is backfill-only. `scripts/mvp.py` gains a
  `backfill` subcommand wiring `pick_date` to `reco_date` (not "now", unlike `add`). Depends on M0 (equity daily-close table) and M7 (`reco_price` field). | Owner: Claude | Model: claude-sonnet-5 |
  Review: code-reviewer | SHA: —
- [ ] **M9** — M-A lump-sum fill math (resolves stories.md open point 2). `src/mvp/store.py`: `update_pick`'s existing PENDING→OPEN auto-advance (on `entry_price` being set) also computes and persists
  the fill in the same call: `total_qty = floor(capital_allotted / entry_price)`, `deployed_capital = total_qty * entry_price`, `avg_cost = entry_price`, `idle_cash = capital_allotted -
  deployed_capital` (2026-09-18 decision #1 — residual does not roll into a later tranche, M-A has only one fill). Apply the 25 bps round-trip cost knob (decision #2) on this entry fill, capitalized
  into `avg_cost` (not `deployed_capital`, so `idle_cash` stays the untouched residual). `close_pick`: compute `realized_pnl = (close_price * (1 - 25bps) - avg_cost) * total_qty` on the terminal
  transition. `scripts/mvp.py`: `summary`/`list` surface `deployed_capital`, `avg_cost`, `realized_pnl`, and return% (`realized_pnl / deployed_capital` when closed, unrealized `(ltp - avg_cost) *
  total_qty / deployed_capital` when open — unrealized needs an `ltp_map` param threaded through, same as `check_prices`). Out of scope: `mvp_tranches` table population (M-B), `benchmark_entry`/alpha
  display (separate, decision #3). | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
