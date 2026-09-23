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
- [ ] **M5** — Docs close: CONTEXT.md tree, DECISIONS.md entry, TODOS.md session log | Owner: Claude | Model: n/a | Review: none | SHA: —
- [ ] **M0** — Equity + NIFTY index bhavcopy ingest (prerequisite for M6 only — not M1–M5). `src/backtest/bhavcopy_ingest.py` is F&O-only today; add equity cash-market daily close + NIFTY 50 index
  level ingest before M6's historical backfill can be implemented. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **M6** — see full spec below (Good-to-Have, blocked on M0) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
