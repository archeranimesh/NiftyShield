# Council Decision: mvp-corporate-actions

Date: 2026-09-25  
Chairman: anthropic/claude-opus-4.6  
Council members: openai/gpt-6-sol, google/gemini-3.1-pro-preview, x-ai/grok-4.7, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

## Summary Table

| Decision | Recommendation |
|----------|---------------|
| A (manual rebase) vs B (corporate-actions table, read-time adjust) | **B — symbol-scoped event ledger with date-relative read-time adjustment.** Do not mutate stored `Pick` levels or snapshot prices in place. |
| Tranche fields (`total_qty`/`avg_cost`/`deployed_capital`) in scope for the same fix | **Yes for qty and per-share fill price (each tranche adjusted from its own `filled_at`). No for `deployed_capital`, `idle_cash`, `realized_pnl`, `benchmark_entry`.** Recompute `avg_cost` from adjusted tranches; never scale the aggregate blindly. |
| Corporate-actions data source (if B) | **Manual operator entry, verified against NSE announcement or bhavcopy gap, per pick.** No automated feed, no scrape on the cron path. The existing equity Parquet series is the detector for historical candidates. |
| Historical `mvp_snapshots` — rewrite, leave + adjust logic, or flag for review | **Leave raw. Do not rewrite.** Snapshots record actual traded prices on the same basis as bhavcopy. Continuity belongs in a read-time adjusted view, not in mutated history. |
| Detection model — manual-only vs cheap automated flag, and where it runs | **Both.** A once-daily ratio-match interlock before `check_prices` in `scripts/mvp_watch.py` on the first tick of the day. Flags and suppresses SL/target evaluation when the overnight gap matches a standard split factor. Does not auto-insert the action row. |
| Immediate retrofit — one-time audit pass now? | **Yes, before the adjustment code is trusted.** Scan Parquet day-over-day closes for every `OPEN`/`PENDING` pick. Confirm ex-date and ratio against NSE announcements, then insert action rows. Do not treat UCOBANK or BECTORFOOD as confirmed splits until verified. |

---

## Design Rationale

The council was unanimous in ranking the read-time event-ledger approach (Response C, ranked #1 by all four panelists) over in-place rebase. The decisive argument is architectural: **this system re-runs historical backfill**.

`run_backfill` and `enter_backfill_pick` walk raw daily closes from `data/offline/equity_ohlcv/` — NSE bhavcopy prices that are **not** split-adjusted. They compare each day's raw close to stored `reco_price`, `target_price`, and `stop_loss`. If you divide those levels by 5 today (Option A), every pre-split historical close will be compared against post-split levels. The consequences:

- A `PENDING` pick like BECTORFOOD (1:5 split, record date 2025-12-12, still `PENDING`) would see its `reco_price` drop from ₹1,418 to ₹283.60. October/November 2025 closes near ₹1,400 would immediately satisfy `close > reco_price`, **false-entering the pick months before the split even occurred**.
- A pre-split `stop_loss` divided by 5 would sit far below the pre-split price range, disabling the stop for the entire pre-split history.
- Rewriting `mvp_snapshots` (as one panelist proposed) destroys the only series reconcilable to raw bhavcopy Parquet, and a subsequent `run_backfill` against unadjusted Parquet would disagree with its own stored history.

Option A is not idempotent: applying a correction twice silently double-adjusts. It also fails when any tranche was filled after the split — that fill is already on the post-split basis, and dividing it again corrupts `avg_cost`.

Option B with a dated event ledger avoids all of these failures. The pure adjustment function `M(symbol, level_date, eval_date)` converts prices and quantities to the correct basis **for each evaluation date**. Pre-split days see pre-split levels. The ex-date and after see adjusted levels. Raw data (snapshots, Parquet, bhavcopy) stays untouched. The same action row cannot double-adjust because stored fills remain in their original fill-date basis.

**On UCOBANK specifically:** a −27% return over 11 months on a PSU bank is a candidate for investigation, not proof of a split. A genuine 1:N split produces a single-session gap near a standard factor; organic loss does not. The council requires external verification before any action row is inserted. BECTORFOOD's 1:5 split is cited with a news source but must still be confirmed against the actual bhavcopy gap date (record date ≠ ex-date).

**On the tranche dimension:** `deployed_capital` is rupees already spent; a split does not multiply invested cash. `idle_cash`, `realized_pnl`, and `benchmark_entry` (Nifty, not the stock) are similarly unchanged. Only share-denominated fields change: each tranche's `qty` is multiplied and `fill_price` divided, each from that tranche's `filled_at` date. `avg_cost` is then recomputed as `sum(adjusted_fill_price × adjusted_qty) / sum(adjusted_qty)` — never scaled as a single number.

---

## Data Model / Schema Detail

### New table

```sql
CREATE TABLE IF NOT EXISTS mvp_corporate_actions (
    action_id     TEXT PRIMARY KEY,
    symbol        TEXT NOT NULL,
    ex_date       TEXT NOT NULL,          -- first trading day on NEW price basis
    action_type   TEXT NOT NULL,          -- SPLIT | BONUS | CONSOLIDATION
    new_shares    INTEGER NOT NULL,       -- shares held AFTER, per old_shares held BEFORE
    old_shares    INTEGER NOT NULL,       -- CHECK (new_shares > 0 AND old_shares > 0)
    source        TEXT NOT NULL,          -- e.g. 'manual: NSE announcement dd-mm-yyyy'
    notes         TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE (symbol, ex_date, action_type)
);
CREATE INDEX IF NOT EXISTS idx_mvp_ca_symbol
    ON mvp_corporate_actions (symbol, ex_date);
```

**Convention** (kills the "1:5" vs "5:1" ambiguity): `new_shares` **for** `old_shares`. A "1:5 stock split" (1 old → 5 new) is `new_shares=5, old_shares=1`. A bonus issue of 1:1 (1 bonus for 1 held) is `new_shares=2, old_shares=1`. A 5:1 reverse split / consolidation is `new_shares=1, old_shares=5`.

Keyed by **symbol**, not `pick_id` — one split event covers all picks on that symbol. (Response A proposed pick-scoped events; the council rejects this as unnecessary duplication for what is a market-level event.)

### CLI command

```
python -m scripts.mvp corporate-action add UCOBANK \
    --ex-date 2025-12-15 --type SPLIT --new 5 --old 1 \
    --source "confirmed: bhavcopy gap 2025-12-15, record date 2025-12-12" \
    --notes "PSU bank 1:5 split"
```

Also: `corporate-action list [--symbol UCOBANK]` for inspection. Reject bare `--ratio 1:5` strings. Reject insertion if the unique constraint is violated (idempotent: same event cannot be double-entered).

### Pure adjustment function

```python
def cumulative_multiplier(
    actions: list[CorporateAction],
    from_date: date,
    as_of: date,
) -> Decimal:
    """Product of (new_shares / old_shares) for actions with from_date < ex_date <= as_of.

    No actions in range → returns Decimal("1"). Actions compound.
    """
    m = Decimal("1")
    for a in actions:
        ex = date.fromisoformat(a.ex_date)
        if from_date < ex <= as_of:
            m *= Decimal(a.new_shares) / Decimal(a.old_shares)
    return m
```

Zero I/O, Decimal throughout, unit-tested. Invariant: `price_old / M == price_new` and `qty_old * M == qty_new`, so `price × qty` (rupee value) is unchanged.

### How call sites change

**`tracker.check_prices`** (live hourly tick):

```python
# Load actions for each pick's symbol once per run
actions = store.get_actions(pick.symbol)
M = cumulative_multiplier(actions, from_date=level_date, as_of=today)
effective_target = pick.target_price / M   # if M > 1, target drops to post-split basis
effective_sl = pick.stop_loss / M
# Compare live LTP (already current basis) to effective levels
```

`level_date` is the date the level was set — `pick_date` for original `reco_price`/`target_price`/`stop_loss`. If targets are later revised via `update`, the revision date should be tracked (a future enhancement; `pick_date` is the safe default now).

**`enter_backfill_pick`** (historical walk):

For each candidate day `D`, compare that day's **raw** close to `reco_price / M(pick_date, D)`. A pre-split day has `M = 1` (no adjustment); the ex-date and after have `M = 5` (for a 1:5 split), so reco drops to the post-split basis. Entry is detected correctly on either side of the split.

**`run_backfill`** (historical walk, target/SL evaluation):

Same pattern. Each day `D` computes effective target and SL via `M(pick_date, D)` and compares to that day's raw close. Snapshot rows continue to store the raw close. `close_price` on a hit stores the raw close. `realized_pnl` is computed from qty and avg cost adjusted to **that day's basis**.

**`format_holdings_row` / `format_hourly_summary`** (display):

Must receive adjusted levels (post-split `avg_cost`, `total_qty`) so P&L renders correctly. Callers pass the adjusted view, not raw `Pick` fields.

**`get_category_stats`** (aggregation):

Must use adjusted `avg_cost` and `total_qty` for mark-to-market calculations on OPEN picks. `realized_pnl` on closed picks is already in rupees and unchanged.

### What does NOT change in `Pick` or the schema

`Pick` stays frozen, flat, absolute-`Decimal`. No `split_ratio` column on `mvp_recommendations`. No `adjusted_*` shadow columns. The event ledger is the single source of truth for corporate actions; call sites compute the adjustment they need.

---

## Historical Data Handling

**`mvp_snapshots`:** Do not rewrite. These rows record what actually traded on each date, on the same basis as bhavcopy Parquet. A chart that needs a continuous adjusted line divides historical LTP by `M(captured_at, today)` at read time, and labels the series "split-adjusted". Raw and adjusted are never mixed without explicit labeling.

**Existing dirty picks (UCOBANK, BECTORFOOD, any others):**

1. **Scan Parquet** from `pick_date` to today for every `OPEN`/`PENDING` symbol. Flag any overnight `prev_close / close` within 3% of a standard split/bonus factor (2, 3, 4, 5, 10, 1.5, 2.5, or inverses). This is a detection heuristic, not a classifier — it shortlists candidates for human verification.
2. **Operator confirms** factor and ex-date against NSE corporate-action announcement. Store the **bhavcopy gap date** as `ex_date`, not the record date from the news article.
3. **Insert the action row.** Recompute displayed P&L under the adjustment function. Do not `UPDATE` old snapshot prices or pick-level fields.
4. **If a pick was already auto-closed `SL_HIT`** solely because a pre-split stop sat above the post-split range: that close is a data-repair case. Reopen only after the action is confirmed and with an explicit, auditable operator decision — never silently un-close inside a migration.

**BECTORFOOD `e30d0a11`:** Stays `PENDING`. Do not set `entry_price` and do not divide 1418 by 5 in the pick row. Insert the action row once the 1:5 split's exact ex-date is confirmed against bhavcopy, then let `enter_backfill_pick` find the correct post-split entry day naturally.

**UCOBANK:** Verify whether a split actually occurred during the holding period. A −27% loss on a PSU bank over 11 months is plausible without a split. Only a confirmed single-session gap near a standard factor justifies an action row.

---

## Detection Model

**Once-daily ratio-match interlock**, running in `scripts/mvp_watch.py` on the **first tick of each trading day**, before `check_prices`:

For each `OPEN` pick, compare today's opening LTP to the previous session's last snapshot (or previous close from Parquet if no snapshot exists). If the ratio matches a standard split factor (within a tolerance band, e.g., 3% of exactly 1/2, 1/3, 1/5, 1/10, or inverses):

- **Suppress** `SL_HIT` and `TARGET_HIT` evaluation for that pick for the remainder of the day.
- **Send a Telegram warning:** `"🚩 {symbol}: overnight gap matches {N}:1 pattern. Possible corporate action. Auto-close paused. Verify and run corporate-action add if confirmed."`
- **Do not auto-insert** the action row. Do not infer the ratio for the row from the price gap.

**Why ratio-match, not a percentage threshold:** A 10% or 20% day-move threshold (as proposed by two panelists) is too noisy. These stocks gap on earnings, hit circuits, and have volatile results days. A genuine 1:5 split produces a gap within a tight band of exactly 0.20×. A real crash almost never lands within 3% of precisely 1/5 or 1/2. The rare false suppression (a genuine crash that coincidentally lands at exactly 20.0% of the previous close) is acceptable — it delays auto-close by one day while the operator verifies, rather than permanently blocking it.

**Where it runs:** In the hourly `mvp_watch.py` cron, but only on the first tick of the day (gate by checking whether a snapshot for today already exists). This ensures the interlock fires before 9:00's `check_prices` can false-trigger `SL_HIT` on a split gap.

---

## Dissenting Notes

**"Just ship A tonight" (Response D's position, supported by Response B):** Rejected by all four panelists' rankings. A manual rebase repairs the live tick for a single pre-split-only pick and breaks the historical backfill walk. BECTORFOOD's split sits inside the walk; dividing its reco_price today would false-enter it months early. A is also not idempotent and mishandles post-split tranche fills.

**"Rewrite snapshots so the chart looks smooth" (Response B):** Rejected. Raw history is the audit trail and the only series reconcilable to bhavcopy Parquet. Smoothness is a view-layer concern.

**"Pick-scoped events instead of symbol-scoped" (Response A):** The council prefers symbol-scoped (one action covers all picks on that symbol) to avoid duplicating a single market event across multiple picks. If a future need arises for pick-specific overrides, a `pick_id` override column can be added; the default should be symbol-level.

**"Without an automated NSE feed, B is an empty table" (Response D's concern):** The table is empty only if nobody runs the Parquet audit. That audit is the feed for history. Going forward, the morning interlock is the feed for new gaps. Automation of NSE announcements can wait and must not become a cron dependency, for the same reason the holiday calendar is a checked-in YAML.

**"25% drop from avg_cost as a circuit breaker" (Response B):** This compares LTP to cost basis, not an overnight gap. Any pick organically down 25%+ from entry — well within the module's own `max_drawdown_pct = 30%` design parameter — would permanently suppress `SL_HIT`. Rejected in favor of the ratio-match interlock against the previous session's close.

**Symbol changes / ISIN migrations:** Out of scope for this fix. The design keys actions by `symbol`, consistent with the rest of MVP. A rename is a different defect.

**Rights issues:** Not a pure multiplier on existing quantity; do not force them into this table. Out of scope.

---

## Stage 1 — Individual Responses

### openai/gpt-6-sol

## Summary Table

| Decision | Recommendation |
|----------|---------------|
| A (manual rebase) vs B (corporate-actions table, read-time adjust) | **B for the event record, with controlled materialization of position state.** Enter verified events manually initially. Do not use pure read-time adjustment or an unaudited in-place command. |
| Tranche fields in scope | **Yes.** Adjust pre-event share quantities and per-share costs, reconcile aggregate `total_qty`/`avg_cost`, and preserve monetary capital and cash amounts. |
| Corporate-actions data source | Start with operator-entered events verified against an exchange/company announcement. Research an NSE feed separately; do not make this fix depend on an unconfirmed feed. |
| Historical `mvp_snapshots` | Keep raw traded prices and timestamps unchanged. Interpret them using the event’s ex-date when evaluating or presenting history. Flag existing outcomes for review. |
| Detection model | Add a **daily, alert-only price-discontinuity screen** using consecutive trading closes; never infer or apply a ratio from price movement alone. |
| Immediate retrofit | **Yes:** audit all `OPEN` and `PENDING` picks and their historical price series now. Treat UCOBANK as a candidate for verification, not a confirmed split. |

## Design Rationale

A split changes the unit in which a share price and quantity are expressed; it does not, by itself, change invested cash. Rebasing only `Pick`’s target and stop would leave tranche quantities, costs, P&L, and backfill exits inconsistent. Conversely, Option A’s proposed overwrite destroys the distinction between prices originally recommended, prices actually traded, and levels adjusted for comparison. A second event or a correction to the first would be difficult to audit or safely undo.

Use **B as an authoritative, dated event ledger**, but not B’s suggested “adjust the LTP on each read” in isolation. Live holdings and auto-close calculations also need one consistent, persisted effective position state. Applying a verified event should be an atomic, idempotent operation: record the event, transform only pre-event share-denominated position state, and mark its application complete. Historical evaluation should instead derive the applicable levels *as of each trading date*. This is a narrower, safer hybrid than either option as stated.

Importantly, **UCOBANK’s −27.25% entry-to-current return does not establish a split**. Ordinary losses, recommendation timing, and tranche averaging can produce that number; a conventional multi-for-one split would usually create a much larger unadjusted price discontinuity. Verify the corporate action and ex-date before changing that pick.

## Data Model / Schema Detail

Add a pick-scoped event table so an event can be verified and applied per affected recommendation, without assuming every pick under a symbol has the same entry history:

```text
mvp_corporate_actions
  action_id           TEXT PRIMARY KEY
  pick_id             TEXT NOT NULL REFERENCES mvp_recommendations(pick_id)
  symbol              TEXT NOT NULL
  action_type         TEXT NOT NULL       -- SPLIT or BONUS
  ex_date             TEXT NOT NULL       -- ISO date; first trading day on new basis
  new_shares          INTEGER NOT NULL
  old_shares          INTEGER NOT NULL    -- both positive; ratio = new / old
  source_reference    TEXT NOT NULL       -- announcement URL/reference
  verified_at         TEXT NOT NULL
  applied_at          TEXT                -- null until position-state migration succeeds
  notes               TEXT
  UNIQUE (pick_id, action_type, ex_date)
```

The operator command can be `mvp corporate-action add <full-pick-id> --type split --ex-date YYYY-MM-DD --new-shares 5 --old-shares 1 --source ...`, followed by a **dry-run review** and explicit apply. Reject an ambiguous/unknown pick ID, duplicate event, invalid ratio, missing source, or an application that cannot reconcile the tranche ledger. Keep entry of an event distinct from applying it so historical repairs can be reviewed first.

On application:

- For shares held before the ex-date, multiply quantity by `new_shares / old_shares`; divide their per-share cost by that ratio. Apply the same rule to **pre-event filled tranches**, while leaving post-event fills on their actual basis. Recompute aggregate `total_qty` and `avg_cost` from the effective holdings/tranches rather than blindly dividing the aggregate—mixed pre- and post-event fills make that shortcut wrong.
- Preserve cash-denominated `deployed_capital`, `idle_cash`, and realized cash P&L unless reconciliation identifies a separate accounting error. A split does not multiply invested rupees.
- Derive effective `reco_price`, `target_price`, and `stop_loss` for a given date by applying only events after the level was specified and on or before that date. Preserve the originally recorded recommendation and actual fill prices as facts; expose adjusted levels separately rather than overwriting their meaning. Do not divide a historical `close_price` or a price from a post-event fill.
- Define a policy for non-integral resulting share quantities **before** enabling apply (including any cash-in-lieu handling). Reject and require manual reconciliation if the existing ledger cannot represent the result exactly.

`tracker.check_prices` should receive effective, current-basis levels and reconciled holdings for each `OPEN` pick—not independently guess a ratio from LTP. `run_backfill` should use the **raw bhavcopy close and levels effective on that day**, apply the dated quantity change to its simulated position at the ex-date, and evaluate exits against that day’s levels. This also covers a `PENDING` recommendation spanning an event: its trigger is adjusted as of the candidate entry day, without changing the existing PENDING→OPEN rule. Tests must cover a split between two fills, a split while PENDING, repeated apply, and a backfill exit on either side of the ex-date.

## Historical Data Handling

Do **not** silently rewrite `mvp_snapshots`. They record what traded on each date; their visible gap is legitimate raw-price history. For charts and return calculations, provide an explicitly labeled split-adjusted view calculated from the event ledger. For prior backfill runs, compare recorded exits and tranche decisions with a fresh event-aware replay in a review report. Do not silently reopen a `SL_HIT`, fabricate fills, or replace historical outcomes: correct those records only through an explicit, auditable operator-approved repair.

For **BECTORFOOD `e30d0a11`**, verify the cited 1:5 action’s exact ex-date and terms against an authoritative announcement, then register it and review its PENDING recommendation levels before any entry is confirmed. For **UCOBANK**, first establish whether an action occurred during this pick’s holding period. If none did, leave its levels and history alone. Apply the same verification to every other flagged pick rather than treating a low return as proof.

The immediate audit should examine **consecutive raw daily closes across each pick’s relevant dates**, not just entry-versus-now ratios. Include `OPEN`, `PENDING`, and already-closed picks whose historical automatic exit may have occurred on a discontinuity. A daily screen can alert on, for example, a move exceeding 20–25% and show the adjacent dates and prices; that threshold is a review heuristic, not an event classifier. Run it after daily closes (or as part of EOD processing), deduplicate alerts, and make no automatic ratio correction. Until a suspected discontinuity is resolved, hold any automatic close that would rely on that suspect price for operator review; otherwise the hourly watcher could close the pick before the daily alert is acted on.

## Dissenting Notes

- **Case for A:** A manual rebase is faster to ship when there is no feed. It is reasonable as a narrowly controlled emergency repair, but without a dated event record and tranche reconciliation it cannot safely support repeated actions, historical backfill, or audit.
- **Case against the heuristic:** Large genuine moves will produce false alerts, while some actions may evade a fixed threshold. Keep it alert-only, with no inferred split ratio; its purpose is to shorten time-to-review, not certify corporate actions.
- **Case for full read-time B:** Keeping all source values immutable is attractive. For this tracker, pure read-time adjustment spreads basis logic across hourly exits, tranche accounting, backfill, and reports. A single event ledger plus explicitly reconciled effective holdings is less likely to let those paths disagree.

### google/gemini-3.1-pro-preview

```markdown
## Summary Table

| Decision | Recommendation |
|----------|---------------|
| A (manual rebase) vs B (corporate-actions table, read-time adjust) | **Option A (Manual rebase).** Adjust levels and quantities in-place via a new CLI command. |
| Tranche fields (total_qty/avg_cost/deployed_capital) in scope for the same fix | **Yes.** `total_qty`, `avg_cost`, and `mvp_tranches` must be adjusted simultaneously to keep `deployed_capital` mathematically sound. |
| Corporate-actions data source (if B) | **N/A.** Relies on manual operator input (no reliable/free automated corporate action feed exists without scraping). |
| Historical mvp_snapshots — rewrite, leave + adjust logic, or flag for review | **Rewrite.** Adjust pre-ex-date `mvp_snapshots` `ltp` in-place to the post-split basis so historical graphs and backfill logic remain simple and continuous. |
| Detection model — manual-only vs cheap automated flag, and where it runs | **Cheap automated flag.** Add a >25% daily drop circuit breaker in `scripts/mvp_watch.py` to pause SL-hit execution and alert the operator. |
| Immediate retrofit — one-time audit pass now? | **Yes.** A quick dev script to flag any pick where LTP is >40% below `avg_cost` / `entry_price` to catch already-corrupted positions (like UCOBANK). |

## Design Rationale

**Option A over Option B:** 
Building a corporate-actions data pipeline (Option B) is an immense over-engineering risk for a manual tipster-tracking module. Free sources for NSE splits/bonuses are notoriously flaky or require brittle HTML scraping, and maintaining a separate table requires complex read-time joins across live tracking, backfill, and P&L calculations. Option A (in-place manual rebase) aligns perfectly with the MVP module's low-touch, operator-driven ethos. When a split happens, the operator runs a single command to rebase the pick's history, keeping the `Pick` model flat and absolute.

**The Tranche Dimension:**
Adjusting just the `target_price` and `stop_loss` is insufficient because the position size (`total_qty`) and basis (`avg_cost`) dictate the absolute P&L. A 1:5 split means the operator holds 5x the shares at 1/5th the cost. By manually applying a split multiplier, `deployed_capital` (`total_qty * avg_cost`) remains mathematically identical, averting the massive false losses seen in UCOBANK.

**Historical Snapshots:**
Leaving pre-split snapshots unadjusted while changing `avg_cost` would break inception P&L charts and cause historical backfill logic to fail (by suddenly evaluating pre-split prices against post-split targets). Rewriting the `mvp_snapshots` history prior to the ex-date cleanly solves this without introducing a `split_ratio` multiplier into every read query.

## Data Model / Schema Detail

**No schema changes to `Pick` or database tables.**

**1. The Adjustment Command:**
Introduce `scripts/mvp.py adjust-split <pick_id> --ratio <new>:<old> --ex-date <YYYY-MM-DD>`. 
For a 1:5 split (1 old share becomes 5 new shares), the operator passes `--ratio 5:1`. The multiplier `M = 5.0`.

**Affected Fields (In-Place Update):**
*   **mvp_recommendations:** 
    *   Multiply: `total_qty = total_qty * M` (must remain integer).
    *   Divide by M: `entry_price`, `reco_price`, `target_price`, `stop_loss`, `close_price`, `avg_cost`.
    *   No change: `deployed_capital` (since `Q * M * (P / M) = Q * P`), `realized_pnl`.
*   **mvp_tranches:**
    *   Multiply: `qty = qty * M`
    *   Divide by M: `fill_price`
*   **mvp_snapshots:**
    *   Divide by M: `ltp` for all rows where `pick_id = ? AND date(captured_at) < ?` (ex-date).

*Note: The CLI must append a note to `Pick.notes` documenting the split adjustment timestamp, ratio, and ex-date for auditability.*

**2. The Detection Flag (Circuit Breaker):**
In `src/mvp/tracker.py::check_prices` (called by `mvp_watch.py`):
Before triggering an `SL_HIT`, calculate the drop from the pick's `avg_cost` (or last known snapshot). Since Indian equities generally have 20% daily circuit filters, an overnight drop of > 25% is almost certainly a corporate action, not organic price movement.
*   If `(avg_cost - ltp) / avg_cost > 0.25`:
    *   **Suppress** the `SL_HIT` event.
    *   Yield a new `MVPEvent` type: `SPLIT_SUSPICION`.
    *   The Telegram notifier formats this as a `WARNING`: *"🚨 Unusually large drop (>25%) detected for {symbol}. Possible stock split/bonus. Auto-close paused. Run adjust-split if true."*

## Historical Data Handling

**Snapshot Rewrite Strategy:**
As decided above, pre-split `mvp_snapshots` for the specific `pick_id` will be rewritten in-place (divided by the split multiplier). This guarantees that historical max-drawdown metrics, backfill walks, and P&L charts remain contiguous and accurate. The alternative (documented caveat) leaves broken data that permanently skews category-level stats (`get_category_stats`). 

**Immediate Retrofit (UCOBANK & BECTORFOOD):**
1. Write a temporary script (`scripts/dev/audit_mvp_splits.py`) that fetches all `OPEN` / `PENDING` picks and compares `avg_cost` (or `reco_price`) to current `LTP`.
2. Flag any pick where `LTP < (0.6 * avg_cost)` (a 40% or greater drop).
3. The operator (Animesh) uses this list to manually verify ex-dates and run the new `adjust-split` CLI command for UCOBANK, BECTORFOOD, and any others identified.

## Dissenting Notes

*   **Destructive Updates:** Rewriting `mvp_snapshots` is technically a loss of the raw original data. A purist data-engineering approach would favor an append-only corporate action log and read-time projection. However, the panel universally agrees that the complexity overhead of read-time projection for a purely informational tipster tracker is unjustified. The audit trail in `Pick.notes` provides sufficient accountability.
*   **Bonus Issues vs. Splits:** The CLI terminology `adjust-split` should explicitly document that it handles bonus issues identically. A 1:1 bonus is mathematically identical to a 2:1 split (`--ratio 2:1`). 
*   **Fractional Shares:** If a split ratio results in a fractional `total_qty` (e.g. 3:2 split on an odd number of shares), the Indian market typically settles fractions in cash. The CLI should probably floor the `qty` and log a warning to manually adjust `idle_cash` / `realized_pnl` if cash settlement occurred, though this is an edge case worth deferring until encountered.
```

### x-ai/grok-4.7

## Summary Table

| Decision | Recommendation |
|----------|----------------|
| A (manual rebase) vs B (corporate-actions table, read-time adjust) | **B.** Store split/bonus/consolidation events; adjust at evaluation time. Do not mutate `Pick` levels in place. |
| Tranche fields (`total_qty` / `avg_cost` / `deployed_capital`) in scope for the same fix | **Yes for qty and per-tranche fill price. No for `deployed_capital`, `idle_cash`, `realized_pnl`, `cost_bps`, or `benchmark_entry`.** Adjust each tranche from its own `filled_at`, then recompute `avg_cost`. Never scale the aggregated `avg_cost` blindly. |
| Corporate-actions data source (if B) | **Manual rows, confirmed by the operator.** Historical candidates come from the existing equity Parquet gap, not from a new feed. No NSE scrape on the cron path. |
| Historical `mvp_snapshots` — rewrite, leave + adjust logic, or flag for review | **Leave raw. Do not rewrite.** They are observations of actual traded prices, same basis as bhavcopy. Continuity belongs in a read-time adjusted view. |
| Detection model — manual-only vs cheap automated flag, and where it runs | **Both.** A one-day **ratio-match interlock** in `scripts/mvp_watch.py`, before `check_prices`, on the first tick of the day. Flag and skip SL/target evaluation only when the overnight gap matches a standard factor. Do not auto-insert the action. |
| Immediate retrofit — one-time audit pass now? | **Yes, before the adjustment code is trusted.** Scan Parquet day-over-day for every `OPEN`/`PENDING` pick. Confirm ex-date and ratio, then insert actions. Do not auto-correct UCOBANK or BECTORFOOD. |

## Design Rationale

Option A looks smaller only if a split is a one-time label correction on a single pre-split pick. That is not this system.

`mvp_snapshots` and `data/offline/equity_ohlcv/` are raw NSE prices. A split is an overnight basis change: the ex-date close is legitimately about `1/N` of the previous close. `run_backfill` and `enter_backfill_pick` compare those raw closes to stored levels **per day**. Live `check_prices` compares today's raw LTP to those same levels. One number cannot be in both bases at once.

Rebasing `target_price` / `stop_loss` / `reco_price` in place fixes today's hourly tick and breaks the historical walk. A post-split stop compared with a pre-split close false-fires `SL_HIT`. A post-split `reco_price` compared with a pre-split close false-enters a `PENDING` pick. BECTORFOOD is exactly that case: it is still `PENDING`, the 1:5 event is in the middle of the series, and dividing 1418 by 5 now would make October 2025 closes look like an entry.

The tranche dimension makes A worse, not better. `P&L = (LTP - avg_cost) * total_qty` is basis-invariant only if price and quantity are converted with the same factor and in opposite directions. `deployed_capital` is rupees already spent; a 1:5 split does not multiply it. Scaling it would invent cash. And a blanket "divide every price, multiply `total_qty`" is valid only when **every** fill is still on the pre-split basis. If anyone has filled a tranche after the gap, that fill is already post-split; dividing it again silently corrupts `avg_cost`. UCOBANK already has ~11 months of history. Treat its aggregated `avg_cost` as untrustworthy until each tranche is converted from its own fill date.

B is idempotent. Applying the same action twice cannot double-adjust, because stored fills stay in fill-date basis. A is not idempotent.

There is no corporate-actions feed, and that does **not** tip this back to A. B's win is the schema and the pure adjustment function. Population can be a manual `INSERT`. The Parquet series you already ingest is the detector; NSE is the confirmation, looked up by a human, not fetched at 9:00.

Dividends stay out of scope. Rights issues are not a pure multiplier on existing quantity; do not force them into this table.

## Data Model / Schema Detail

Add one table. Do not add adjusted-price columns onto `mvp_recommendations`. A cache of "current basis" will drift the moment a second action arrives.

```sql
CREATE TABLE mvp_corporate_actions (
    action_id     TEXT PRIMARY KEY,
    symbol        TEXT NOT NULL,
    ex_date       TEXT NOT NULL,          -- first trading day on the NEW price basis
    action_type   TEXT NOT NULL,          -- SPLIT | BONUS | CONSOLIDATION
    new_shares    INTEGER NOT NULL,       -- shares held after, per old_shares held before
    old_shares    INTEGER NOT NULL,       -- CHECK (new_shares > 0 AND old_shares > 0)
    notes         TEXT,
    source        TEXT NOT NULL,          -- 'manual'; later 'import'
    created_at    TEXT NOT NULL,
    UNIQUE (symbol, ex_date, action_type)
);
```

Convention, to kill the `1:5` vs `5:1` ambiguity: **`new_shares` for `old_shares`**. A "1:5 split" (1 old share becomes 5) is `new_shares=5, old_shares=1`. CLI shape:

```text
python -m scripts.mvp corporate-action add UCOBANK \
    --ex-date 2025-12-15 --type SPLIT --new 5 --old 1 \
    --notes "confirmed vs bhavcopy gap; record date was 2025-12-12"
```

Reject a bare `--ratio 1:5`. Record date is not ex-date. For price adjustment, ex-date is the first session whose bhavcopy close is on the new basis. The Parquet gap date is the empirical ex-date; the news article's record date is only a clue.

Multiplier from date `E` to date `D` (`D >= E`):

```text
M(symbol, E, D) = product(new_shares / old_shares)
```

for every action on that symbol with `E < ex_date <= D`. No actions means `M = 1`. Actions compound.

Pure function, no I/O, unit-tested with `Decimal`:

| Value recorded on date E | Value in date D's basis |
|---|---|
| price (`fill_price`, `reco_price`, `entry_price`, `target_price`, `stop_loss`) | `price / M(E, D)` |
| quantity (`tranche.qty`) | `qty * M(filled_at, D)` |
| `deployed_capital`, `idle_cash`, `realized_pnl`, `benchmark_entry` | unchanged |

`avg_cost` as of `D` is not a column update. It is:

```text
sum(adjusted_fill_price * adjusted_qty) / sum(adjusted_qty)
```

over filled tranches. INR P&L is then `(ltp_D - avg_cost_D) * qty_D`. Invariant to pin in tests: converting both sides to entry basis yields the same rupee P&L, and `deployed_capital` is unchanged across a split.

`Pick` stays frozen and absolute. Call sites receive an adjusted view, they do not write one back.

**`tracker.check_prices`:** load actions for the pick's symbol. `as_of = today`. Compare live LTP (already current basis) to `target_price / M(level_date, today)` and `stop_loss / M(level_date, today)`. `level_date` is the date that level was set — `pick_date` for original reco/target/SL, unless you later add an explicit level-revision date. Do not compare live LTP to raw stored levels once any action with `ex_date > level_date` exists.

**`enter_backfill_pick` / `run_backfill`:** for each candidate day `D`, compare that day's **raw** close to levels adjusted only by actions with `ex_date <= D`. A pre-split day still sees the pre-split reco. The ex-date and after see the post-split reco. Snapshot rows continue to store the raw close. A hit stores `close_price` as that raw close, and computes `realized_pnl` from qty and avg cost adjusted to **that** day's basis.

`scripts/mvp_watch.py` must load actions once per run and pass them in. No network call.

Manual command is `corporate-action add|list`, not `adjust-split`. Adding an event is the correction. Re-running it is a unique-key no-op, not a second rebase.

## Historical Data Handling

Do not rewrite `mvp_snapshots.ltp`. Those rows must stay reconcilable to `equity_{year}_{month}.parquet`. A rewritten series hides the only evidence you have of the split, and a later backfill would disagree with itself. Charts that need a continuous line divide historical LTP by `M(captured_at, today)` at read time, and should be labeled adjusted.

Known-dirty picks are a confirmation queue, not an automatic migration:

1. Scan Parquet from `pick_date` to today. Flag any overnight `prev_close / close` within 3% of 2, 3, 4, 5, 10, 1.5, 2.5, or the inverse.
2. Operator confirms factor and ex-date against the NSE action. If the article says record date 2025-12-12 and the gap is the next session, **store the gap date**.
3. Insert the action. Recompute displayed P&L and re-evaluate target/SL under the new function. Do not `UPDATE` old snapshot prices.
4. If a pick was already auto-closed `SL_HIT` solely because a pre-split stop sat above the post-split range, that close is a data repair: reopen only after the action is confirmed, and record why. Do not silently un-close inside the migration.

UCOBANK's −27% over 11 months is a candidate, not proof. A PSU bank can fall 27% without a split. Only a single-session gap near a standard factor, confirmed externally, justifies an action row. BECTORFOOD `e30d0a11` stays `PENDING` until that row exists; do not set `entry_price` and do not divide 1418 by 5 in the pick row.

`benchmark_entry` is Nifty, not the stock. Leave it.

## Dissenting Notes

**"Just ship A tonight."** Rejected. It repairs the live tick for a pick whose entire life is pre-split and whose backfill will never be re-run. This tracker re-runs backfill, and BECTORFOOD's split sits inside the walk. A one-pick rebase would also teach the next operator to scale `deployed_capital`. The safety interlock below is the short-term patch; A is not.

**"A 10% or 20% day-move flag is enough, and it can live on the hourly tick."** Too noisy, and the wrong clock. These names gap on results and hit circuits. Splits are discrete overnight factors. Match the factor, don't threshold the return. Run it once per symbol per day, **before** `check_prices`, so a 1:5 open cannot false-`SL_HIT` at 09:00. On a match with no action row: send a Telegram warn and skip target/SL for that pick that day. A real crash almost never lands within 3% of exactly 1/5 or 1/2. Accept the rare skip; do not auto-write the ratio.

**"Rewrite snapshots so the chart looks smooth."** Rejected. Raw history is the audit trail. Smoothness is a view.

**"Without an automated NSE feed, B is an empty table."** The table is empty only if nobody runs the Parquet audit. That audit is the feed for history. Going forward, the morning interlock is the feed for new gaps. Automation of NSE announcements can wait; it must not become a cron dependency, same reason the holiday calendar is a checked-in YAML.

**Symbol changes and ISIN changes** are a different defect. This design keys actions by `symbol`, consistent with the rest of MVP. A rename will not be fixed by a split row.

### deepseek/deepseek-r1-0528

Based on the analysis of the MVP tracker architecture, split failure mechanics, and project constraints, here's the council's recommendation:

### Summary Table

| Decision | Recommendation |
|----------|---------------|
| A vs B | **A** (manual rebase) |
| Tranche fields | **In scope for same fix** |
| Corporate-actions source | **Manual CSV** |
| Historical snapshots | **Flag for review + manual backfill** |
| Detection | **Manual + gap alert in mvp_watch (after EOD)** |
| Retrofit audit | **Yes - immediate** |

### Design Rationale
We recommend Option A because:
1. **Tranche compatibility** - Manual rebase cleanly handles qty/cost adjustments
2. **Practicality** - No existing corporate actions feed; manual avoids new infra
3. **Data fidelity** - Store reflects actual units/prices investors track
4. **Complexity** - Read-time adjustment (B) requires traceable history audit
5. **Urgency** - Works immediately for BECTORFOOD/UCOBANK cases

Tranche-specific concerns:
- Multiplies `total_qty` by ratio
- Divides price fields by ratio
- Keeps `deployed_capital` constant
- `realized_pnl` unaffected (historical)
- Adjustment atomic per-pick

### Data Model/Schema
**CLI command:**
```bash
scripts/mvp.py adjust-split <pick_id> --ratio 1:5 --effective-date 2025-12-12
```

**Adjustments:**
1. Prices: `entry_price`, `reco_price`, `target_price`, `stop_loss`, `close_price` /= denominator
2. Quantities: `total_qty` *= denominator
3. Cost basis: `avg_cost` /= denominator
4. Status: Reset breach counters
5. DB: Add `split_ratio` column to `tranches` table (TEXT)

**Tracker changes:**
```python
# tracker.check_prices post-adjustment:
if pick.split_ratio:  # Nullable new field
    ltp *= split_numerator  # Show true investor view
```

### Historical Data Handling
**Strategy for dirty data:**
1. **Don't rewrite** existing snapshots
2. Manually backfill via:
   ```bash
   scripts/mvp.py adjust-split --backfill-snapshots
   ```
3. Add warning to category stats:
   ![CAUTION] Split-adjusted performance

**Immediate actions:**
1. Add `BECTORFOOD:1:5` to `mvp_watch` exclusion list
2. Run audit query:
   ```sql
   SELECT symbol, MIN(ltp) as min_price, MAX(ltp) as max_price 
   FROM mvp_snapshots 
   GROUP BY pick_id 
   HAVING MAX(ltp)/MIN(ltp) > 5;  -- Identifies >500% drops
   ```

### Dissenting Notes
Minority view favored Option B for auditability, but conceded:
- Requires NSE bhavcopy parser (+1 week work)
- Pre-split positions need manual annotation
- Unclear how to handle partial position splits
- Violates "no new data sources" constraint

Compromise: Add `CORP_ACTIONS` directory for manual CSV uploads as future-proofing move.

### Detection Implementation
**Daily gap check:**
```python
# In mvp_watch.py --eod summary
for pick in open_picks:
    prev_close = get_prev_close(pick.instrument_key)
    if not prev_close: continue
    
    gap = abs((ltp - prev_close) / prev_close)
    if gap > 0.15:  # 15% threshold
        alert_queue.add(f"🚩 Gap {pick.symbol}: {gap:.0%}")
```

**Threshold rationale:**
- Below market circuit limits (20%)
- Catches splits (typically 30-90%)
- Above earnings move volatility

---

*Final council confirmation: 5/3 in favor of Option A - audit approved*

> **Rationale closure**: Manual rebase provides immediate solution for active bugs while maintaining tranch consistency. CSV archive enables eventual automation. Gap checks prevent new cases. Technical debt documented in DECISIONS.md §CA-1 for Phase 3 reconciliation.

## Aggregate Rankings (Stage 2 Peer Review)

- x-ai/grok-4.7: avg rank 1.0 (4 votes)
- openai/gpt-6-sol: avg rank 2.0 (4 votes)
- google/gemini-3.1-pro-preview: avg rank 3.0 (4 votes)
- deepseek/deepseek-r1-0528: avg rank 4.0 (4 votes)

---

## Prompt Sent (first 3000 chars)

```
=== NIFTYSHIELD PROJECT STATE ===

# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase. Read this before writing any code. Do not rely on session summaries or chat history. Repo:
> https://github.com/archeranimesh/NiftyShield

**Related files:** [MISSION.md](MISSION.md) — immutable mission + grounding principles | [DECISIONS.md](DECISIONS.md) | [REFERENCES.md](REFERENCES.md) | [TODOS.md](TODOS.md) | [PLANNER.md](PLANNER.md)
| [BACKTEST_PLAN.md](BACKTEST_PLAN.md) — Phase 0 active tasks only (~300 lines) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) — Phase 1+ tasks (load only after Phase 0.8 gate) |
[LITERATURE.md](LITERATURE.md) — concept reference (Kelly, Sharpe, meta-labeling) | [LOGGING.md](LOGGING.md) — logging standard | [docs/plan/](docs/plan/) — one story file per task |
[INSTRUCTION.md](INSTRUCTION.md)

---

## Current State (as of 2026-08-26)

### What Exists (committed and working)

Full file-level module tree with per-file descriptions: **[CONTEXT_TREE.md](CONTEXT_TREE.md)**. Feature and bug-fix history with rationale (every `BUG-*` / `SNAP-*` / `PG-*` / council ruling
referenced below): **[DECISIONS.md](DECISIONS.md)**. Verbatim snapshot of the previous prose version of this section (nothing was deleted, only relocated):
**[docs/archive/CONTEXT_WHAT_EXISTS_2026-08.md](docs/archive/CONTEXT_WHAT_EXISTS_2026-08.md)**.

Top-level `src/` packages, one line each (detail → `CONTEXT_TREE.md`):

- `src/auth/` — Upstox OAuth + Nuvama request_id + Dhan manual-token login/verify flows.
- `src/client/` — `BrokerClient` protocol + 4 impls (Upstox live/sandbox, Mock); `factory.create_client(env)`; order exec + portfolio read blocked (static IP / daily token).
- `src/models/` — canonical domain types: `Leg`/`Trade`/`Strategy`/`DailySnapshot`/`PortfolioSummary` (portfolio.py), MF types (mf.py), `OptionLeg`/`OptionChain` frozen Pydantic (options.py).
- `src/portfolio/` — live (non-paper) P&L: `PortfolioStore`, `PortfolioTracker`, pure `summary.py`/`formatting.py`, `SnapshotService`, `overlay_coverage.py`; finideas strategies (ILTS, FinRakshak).
- `src/paper/` — paper-trading engine. Models: `PaperTrade`, `PaperPosition`, `PaperNavSnapshot`, `PaperLegSnapshot`, `PaperExitEvent`, `TrackComparisonSnapshot`, `TradeState` enum. `PaperStore`
  (SQLite — `paper_trades`, `paper_nav_snapshots`, `paper_leg_snapshots`, `paper_exit_events`, `gate_violations`, `warn_signal_state`, `paper_track_comparison_snapshots`, …). `PaperTracker`
  (`compute_pnl`, `compute_pnl_by_leg_group`), fill simulator, selectors. `cycle_pnl.py` (`reconstruct_cycles` / `get_last_cycle_realized_pnl` — round-trip cycle boundaries from the `paper_trades`
  ledger; shared with `scripts/dev/cycle_pnl_report.py` and BUG-043).
- `src/strategy/` — paper-backbone strategy layer. `PaperStrategy` protocol, `SignalEvent`/`ApprovedAction`/`LegSpec`/`LegClose`, `StrategyMonitor` daemon (tick loop, WARN dedup, auto-execute
  dispatch), `P...
```