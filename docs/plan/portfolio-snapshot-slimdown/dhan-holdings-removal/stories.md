# Dhan holdings removal — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, flip this sub-story's row in the epic `README.md` **Stories** table, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

Sub-story 2 (last) of the `portfolio-snapshot-slimdown/` epic. Depends on `finideas-decommission/` — rebase onto the shape FD-3 / FD-4 left `_build_portfolio_summary` and `_format_combined_summary`
in. No `schema.md` — no table is dropped; the Dhan tables are retained and simply stop being written. DHR-4 is the epic close.

**This sub-story lands the epic README *Target message format*.** Read that section before DHR-1 — it is the authoritative spec for the final layout, the field sources, the degraded states, and the
four confirmed decisions (fenced block · options P&L out of `Total` value · `Realized month` MTD-inclusive · `Nifty H/L` when available). DHR-1 = the summary-model side, DHR-2 = the formatter side,
DHR-3 = the send-path (fence, not escape).

Commit order = task order: DHR-1 (summary model) → DHR-2 (formatter) → DHR-3 (orchestration) → DHR-4 (docs + epic archive).

---

## DHR-1 — Remove Dhan from the summary model

**Files to change:**
- `src/portfolio/summary.py` — `PortfolioSummary`, `_build_portfolio_summary`
- (`src/models/portfolio.py` if `PortfolioSummary` lives there instead — grep to confirm which module is canonical after `finideas-decommission/` FD-3)
- `tests/unit/portfolio/` — summary tests

**Before any code (graph queries):**
- `get_code_snippet("PortfolioSummary")` — the field list as FD-3 left it.
- `trace_path("_build_portfolio_summary")` — every caller and every field consumer, so DHR-2 and DHR-3 cover them.
- `search_graph("DhanPortfolioSummary")` — confirm the only summary-layer consumer is here (the `src/dhan/` producers stay).

**What to implement (target: epic README *Target message format*, field-sources paragraph):**

1. Remove the `dhan` field from `PortfolioSummary` and the `dhan_summary` parameter from `_build_portfolio_summary`.
2. Drop every Dhan term: `dhan_eq_value` / `dhan_eq_basis` / `dhan_bd_value` / `dhan_bd_basis` locals; the `dhan_summary.equity_pnl` / `.bond_pnl` additions in `total_pnl`; the
   `dhan_summary.equity_day_delta` / `.bond_day_delta` additions in `total_day_delta` and the `any_delta` guard; the Dhan additions in `total_value` / `total_invested`.
3. **Move Nuvama options out of the portfolio-value terms** (decision 2): `total_value` = MF value + Nuvama bond value; `total_pnl` = `mf_pnl.total_pnl` + `nuvama_bonds.total_pnl` — **remove** the
   `nuvama_options_summary.net_pnl` term from both. `total_invested` = MF invested + Nuvama bond basis.
4. **Add a true Nuvama-options daily delta** (decision 5). `_build_portfolio_summary` takes a new `prev_nuvama_options_unrealized: Decimal | None` param (a scalar, like `prev_mf_pnl` — DHR-3 computes
   it in `daily_snapshot.py` from `NuvamaStore.get_options_snapshot_for_date(prev_trading_day(snap_date))`, summing `unrealized_pnl`). Then: `nuvama_options_day_delta =
   (nuvama_options.total_unrealized_pnl − prev_unrealized) + nuvama_options.total_realized_pnl_today` — `None` when either `nuvama_options` or the prior snapshot is missing.
5. `total_day_delta` = `mf_day_delta` + `nuvama_bonds.total_day_delta` + `nuvama_options_day_delta` (each term `or Decimal("0")`). Add `nuvama_options_day_delta` presence to the `any_delta` /
   `has_deltas` guard. Store `nuvama_options_day_delta` on `PortfolioSummary` (the formatter reads it for the `📊 Today` row); do **not** touch the model's `net_pnl` property — other callers may use
   it, it is just no longer used here.
6. `strategies` / `strategy_pnls` / `prices` params of `_build_portfolio_summary` are dead after `finideas-decommission/` FD-3 — if FD-3 did not already remove them, do it here and fix the
   `daily_snapshot.py` + `SnapshotService` callers.

**Tests (no network, no real DB):**
- `test_build_summary_mf_and_bonds_only` — MF + Nuvama bonds input → `total_value` / `total_pnl` = MF + bond sums, no `dhan` attribute.
- `test_total_excludes_options_pnl` — with a non-zero `nuvama_options.net_pnl`, `total_value` and `total_pnl` are unchanged vs. the options-absent case.
- `test_options_day_delta_true_delta` — with `prev_nuvama_options_unrealized` set, `nuvama_options_day_delta` = `(unrealized_now − prev) + realized_today`, and `total_day_delta` includes it; an
  options-only move still sets `has_deltas` true.
- `test_options_day_delta_none_without_prev` — no prior options snapshot → `nuvama_options_day_delta` is `None`, the `📊 Today` `Nuvama options` row is omitted.
- `test_build_summary_all_none` — every source `None` → zeros, `has_deltas` false path holds.

**Commit:** `refactor(portfolio): drop Dhan + reshape totals for the slimmed snapshot`

---

## DHR-2 — Rewrite the formatter to the Target message format

`_format_combined_summary` is rebuilt to emit the single layout in the epic README *Target message format* — this replaces the waterfall / fallback split, drops all Dhan lines, and adds the `📦
Holdings` + promoted `📈 Nuvama options` sections. The fence characters are added here (the string starts with ```` ``` ```` and ends with ```` ``` ````); DHR-3 stops `daily_snapshot.py` from escaping
it.

**Files to change:**
- `src/portfolio/formatting.py` — `_format_combined_summary` (rewrite; `_delta` / `_pnl_str` / `fmt_inr` helpers reused), delete `_format_protection_stats` if `finideas-decommission/` FD-4 somehow
  left it
- `scripts/portfolio/daily_snapshot.py` — `_print_combined_summary` helper: drop the `dhan_summary` param (full Dhan-fetch removal is DHR-3)
- `tests/unit/portfolio/test_formatting*.py` — replace the golden strings wholesale

**Before any code:**
- Re-read the epic README *Target message format* — the layout, the field-sources paragraph, and the degraded-state rules are the spec.
- `get_code_snippet("_format_combined_summary")` — as `finideas-decommission/` FD-4 left it.

**What to implement:**

1. **One layout.** Build the three sections in order: `📊 Today` (omit the whole block when `not has_deltas`), `📦 Holdings`, `📈 Nuvama options` (omit when `nuvama_options` is `None`). No
   waterfall/fallback branch.
2. `📊 Today` — rows for Mutual funds (`mf_day_delta`), Nuvama bonds (`nuvama_bonds.total_day_delta`), Nuvama options (`summary.nuvama_options_day_delta` — the true delta from DHR-1, **not**
   `net_pnl`), then a rule and `Net` (`total_day_delta`). Omit a row whose delta is `None`. No `▲/▼` arrow, no weight-percent.
3. `📦 Holdings` — `Mutual funds` and `Nuvama bonds` rows with `₹value +pnl +pct%` (right-aligned columns), a rule, then `Total` = `total_value` / `total_pnl` / `total_pnl_pct`. A failed source →
   `[fetch failed]` in place of its numbers, excluded from `Total`, plus one `⚠ <source> excluded` line under `Total`.
4. `📈 Nuvama options` — `Open M2M` (`total_unrealized_pnl`); `M2M today H/L` (`intraday_high` / `intraday_low`); `Nifty H/L` (`nifty_high` / `nifty_low`) — omit this line when either is `None`;
   `Realized today` (`total_realized_pnl_today`); `Realized month (MTD)` (`monthly_realized_pnl + total_realized_pnl_today`); `Realized total` (`total_realized_pnl_today + cumulative_realized_pnl`).
5. Header line `🟢 NiftyShield · {date}` as the first line inside the fence; 🟢/🔴 from the sign of `total_day_delta` (or `total_pnl` when `not has_deltas`).
6. Wrap the whole body in ```` ``` ```` fences. Column widths: pick fixed widths that fit the realistic magnitudes (crores for MF value, lakhs for P&L) and lock them with the golden tests.

**Tests (replace the old golden strings):**
- `test_format_all_three_sources` — MF + Nuvama bonds + Nuvama options → exact-string match against the Target format; fenced; `Total` excludes options; `Today` includes options.
- `test_format_no_prior_day` — `has_deltas=False` → no `📊 Today` block, leads with `📦 Holdings`.
- `test_format_options_unavailable` — no `📈 Nuvama options` section, no `Nuvama options` row in `📊 Today`.
- `test_format_mf_fetch_failed` — `[fetch failed]` on the MF rows, `⚠ Mutual funds excluded` under `Total`, `Total` = bonds only.
- `test_format_nifty_hl_absent` — `Nifty H/L` line omitted when `nifty_high` is `None`.

**Commit:** `refactor(portfolio): rebuild snapshot message to the slimmed 3-source format`

---

## DHR-3 — Strip Dhan fetches from daily_snapshot.py

**Files to change:**
- `scripts/portfolio/daily_snapshot.py`
- `tests/unit/` / `tests/integration/` snapshot-orchestration tests

**Before any code:**
- `grep -n -i "dhan" scripts/portfolio/daily_snapshot.py` — the full hit list (there are ~6 blocks: the `_print_combined_summary` param, the historical Dhan portfolio block, the historical Dhan
  options block, the live pre-fetch/piggyback, the live Dhan portfolio snapshot enrich/record, the live Dhan options block, plus the two `_format_combined_summary` call sites).
- Confirm with `search_graph` that nothing else in `scripts/` imports the Dhan symbols this file uses.

**What to implement:**

1. `_historical_main` — delete the "Dhan portfolio from stored snapshots" block and the "Dhan options from stored EOD snapshot" block; remove `dhan_summary=` and the `summary_text + "\n\n" +
   dhan_options_section` append from the `_format_combined_summary` call.
2. `_async_main` — delete:
   - the "Pre-fetch Dhan holdings" block (`_dhan_holdings_prefetched`, `_dhan_tracked_isins`,
     `fetch_dhan_holdings`, `upstox_keys_for_holdings`, `all_keys |= dhan_upstox_keys`)
   - the "Dhan portfolio snapshot — enrich with Upstox prices" block
     (`enrich_with_upstox_prices`, `build_dhan_summary`, `dhan_store.record_snapshot`)
   - the "Dhan Options (Intraday)" block (both the `snap_date < date.today()` historical
     branch and the live `fetch_positions_raw` / `parse_fund_limit` /
     `record_options_snapshot` branch)
   - `dhan_summary=` and the `dhan_options_section` append from the `_format_combined_summary`
     call, and update the trailing Telegram-send comment that mentions the Dhan block
3. Remove now-unused imports: `from src.auth.dhan_verify import load_dhan_credentials` (if no longer referenced), `from src.dhan.reader import …`, `from src.dhan.positions import …`, `from
   src.dhan.store import …`, `dhan_trade_count` param on `_async_main` and its `--dhan-trades` CLI arg if it exists solely for the options block.
4. **Do not** modify `src/auth/dhan_verify.py`, any `src/dhan/` module, or the Dhan tables. `format_options_section` stays in `src/dhan/positions.py`.
5. If the `--dhan-trades` / `dhan_trade_count` plumbing is removed, update `main()` argparse and its tests.
6. **Prior-day options unrealized** (for DHR-1's `nuvama_options_day_delta`): in both `_historical_main` and `_async_main`, after the Nuvama options snapshot is fetched/loaded, read
   `NuvamaStore.get_options_snapshot_for_date(prev_trading_day(snap_date))`, sum `unrealized_pnl` across the returned positions (→ `None` if the list is empty), and pass it as
   `prev_nuvama_options_unrealized=` to `_build_portfolio_summary` / `_format_combined_summary`. Pure DB read, no network.
7. **Send path — stop escaping the whole string** (DHR-2 made the message a fenced block): in the live-path Telegram send, replace `notifier.send(escape_markdown(summary_text))` with a send of the
   fenced `summary_text` as-is. `_format_combined_summary` already emits
   ```` ``` ```` fences and literal content; the only values that could break a fenced block
   are a literal backtick or backslash in an interpolated string, and none of the numeric /
   date fields here can contain one — assert that with a test rather than escaping. Update
   the stale `<pre>`-era comment above the send. `_historical_main` prints only (no send).

**Tests:**
- `test_historical_main_no_dhan_section` — run `_historical_main` against a seeded stored
  snapshot (MF + Nuvama only) → output has no Dhan content, exit 0.
- `test_async_main_skips_dhan` (mock the clients) — the run makes no Dhan call and the
  assembled message has no Dhan block.
- `test_async_main_sends_fenced_unescaped` — the string handed to `notifier.send` starts and
  ends with ```` ``` ```` and is not double-escaped (no `\-` / `\.` sequences).
- `test_dhan_modules_still_import` — `import src.dhan.reader`, `src.dhan.positions`,
  `src.dhan.store`, `src.auth.dhan_verify` all succeed.

**Commit:** `refactor(snapshot): stop fetching Dhan + send the snapshot as a fenced block`

---

## DHR-4 — Epic close

**Files to change:** `CONTEXT.md`, `src/portfolio/CLAUDE.md`, `DECISIONS.md`,
`DB_REGISTRY.md`, `docs/plan/portfolio-snapshot-slimdown/README.md`, `docs/plan/README.md`,
`TODOS.md`, `docs/archive/TODOS_ARCHIVE.md`, plus the epic-folder `git mv`. Targeted `Edit`
only, never `Write`.

**What to implement:**

1. `CONTEXT.md` — "What Exists" `src/portfolio/` bullet: the snapshot now covers MF + Nuvama
   bonds + Nuvama options only. Add a dated state note: Dhan holdings / P&L / options block
   removed from the snapshot; Dhan auth + client + tables retained, unused.
2. `src/portfolio/CLAUDE.md` — remove Dhan from the snapshot-section invariants; note the
   `dhan_summary` param is gone from `_build_portfolio_summary` / `_format_combined_summary`.
3. `DECISIONS.md` §"daily_snapshot.py Design" + §"Dhan Portfolio Integration" — one dated
   row: Dhan holdings + P&L + intraday-options reporting removed from the daily snapshot
   (Animesh, 2026-09-10); integration kept wired for possible future use; tables frozen.
4. `DB_REGISTRY.md` — mark the `dhan` / `dhan_holdings` / `dhan_options` / margin rows
   **frozen (no new rows after `portfolio-snapshot-slimdown`)** — do not delete the rows.
5. Epic close (DHR-4 is the last sub-story — archive the **whole epic**, per
   `docs/plan/README.md` §Conventions *Completion → archive*):
   - epic `README.md` — flip the `dhan-holdings-removal/` Stories row to ✅ and confirm the
     **Epic done when** block satisfied.
   - `git mv docs/plan/portfolio-snapshot-slimdown docs/archive/plan/portfolio-snapshot-slimdown`.
   - `docs/plan/README.md` — collapse the `portfolio-snapshot-slimdown/` entry under
     `## Active Epics` to `✅ Archived → docs/archive/plan/portfolio-snapshot-slimdown/`.
   - `TODOS.md` — delete the Feature Backlog epic line, append it to
     `docs/archive/TODOS_ARCHIVE.md` under a dated heading; add a Session Log line.
   One commit.

**Commit:** `docs: close portfolio-snapshot-slimdown epic (FD/DHR)`
