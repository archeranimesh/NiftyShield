# MVP — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/mvp/mvp_stories.md`.

---

## ⚠️ Design decisions & open questions — resolve before starting M1

> The story below predates the **capital-deployment** framing (2026-09-09 discussion).
> Each pick simulates a fixed notional (default ₹1,00,000) deployed in tranches, tracking
> average cost and rupee P&L over a holding period — not just a price-vs-target watch.
> M1 (schema/models), M2 (tracker), and M4 (watch) need rewriting against the decisions
> here before implementation. `mvp_schema.md` gains a `mvp_tranches` table and new
> `mvp_recommendations` columns (`capital_allotted`, `tranche_step_pct`, `deployed_capital`,
> `total_qty`, `avg_cost`, `realized_pnl`, `benchmark_entry`).

**Resolved (2026-09-09):**
- **Tranche ladder** — fixed, measured from the recommendation price (not the running
  average). `tranche_step_pct` default **6**. Four 25% tranches fill at 0%, −6%, −12%, −18%
  → 100% deployed by −18%.
- **Stop-loss semantics** — the averaging ladder *is* the strategy. The tipster's
  `stop_loss` is recorded but **not acted on**. Hard stop instead: full exit when the
  blended position is **−30% on fully deployed capital** (`max_drawdown_pct` default 30).

**Open — pick up when the story is taken:**
1. **Whole shares + residual cash** — integer share qty per tranche (floor); track idle
   cash per pick and count it in the deployed-capital return. Does residual roll into the
   next tranche?
2. **Cost model** — single round-trip knob (~25 bps: brokerage + STT + charges) on each
   entry tranche and on exit. Confirm bps and per-tranche vs per-pick application.
3. **Benchmark alpha** — snapshot NIFTY 50 level at `pick_date`; report each pick's return
   vs NIFTY over the identical holding window; provider rollup = aggregate alpha. Confirm
   the source table / fetcher for the index level.
4. **Time stop** — mark-to-market exit at N months if neither target nor −30% hit. N = 6?
5. **Capital-efficiency metric** — track max % deployed per pick (target-hit on one tranche
   ≠ same on four). Reported metric, not a gate — confirm.
6. **Portfolio mode** — independent ₹1L notional per pick (default, pick-quality view) vs a
   shared pool with a concurrent-position cap (realism). Is shared mode in MVP scope?
7. **Phasing** — implement lump-sum (single fill `qty = capital / price` at recommendation)
   as M-A first, staggered ladder as M-B? Delivers the benchmark-alpha table earlier.
8. **Schema council (Step 2b)** — tranche ladder + stop semantics sit on the
   trading-strategy / data-model boundary and are costly to reverse once tables hold data.
   Council call on the schema before M1?
9. **Dividends** — out of scope; note in the model.

**Infra corrections already identified (see chat 2026-09-09):**
- M4.1 LTP path: use `BrokerClient.get_ltp()` via `factory.create_client` (as
  `src/paper/tracker.py` does) — **not** the non-existent `src/dhan/ltp_fetcher.py`.
- M2.2 / M4.2 Telegram: use `parse_mode=MarkdownV2` via `src/notifications/formatting.py`
  + `markdown.py` escaping per `FORMATTING.md` — the HTML framing is stale (migration
  archived 2026-09-06).

---

- [ ] **M1.1** — `src/mvp/models.py`: Provider, Category, Pick, MVPSnapshot Pydantic models + tests
- [ ] **M1.2** — `src/mvp/store.py`: init_db + provider/category CRUD + tests
- [ ] **M1.3** — `src/mvp/store.py`: pick CRUD + snapshot methods + tests
- [ ] **M2.1** — `src/mvp/tracker.py`: MVPEvent + check_prices pure logic + tests
- [ ] **M2.2** — `src/mvp/tracker.py`: format_telegram_summary + tests
- [ ] **M3.1** — `scripts/mvp.py`: provider + category subcommands
- [ ] **M3.2** — `scripts/mvp.py`: add + update + close subcommands (with instrument resolution)
- [ ] **M3.3** — `scripts/mvp.py`: list + summary subcommands
- [ ] **M4.1** — `scripts/mvp_watch.py`: LTP fetch + snapshot recording + auto-close
- [ ] **M4.2** — `scripts/mvp_watch.py`: Telegram per-alert + consolidated hourly summary
- [ ] **M5** — Docs close: CONTEXT.md tree, DECISIONS.md entry, TODOS.md session log
