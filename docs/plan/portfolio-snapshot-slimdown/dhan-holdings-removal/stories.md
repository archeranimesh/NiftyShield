# Dhan holdings removal — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, flip this sub-story's row in
> the epic `README.md` **Stories** table, add one line to `TODOS.md`. See
> `docs/plan/README.md` §Conventions.

Sub-story 2 (last) of the `portfolio-snapshot-slimdown/` epic. Depends on
`finideas-decommission/` — rebase onto the shape FD-3 / FD-4 left `_build_portfolio_summary`
and `_format_combined_summary` in. No `schema.md` — no table is dropped; the Dhan tables are
retained and simply stop being written. DHR-4 is the epic close.

Commit order = task order: DHR-1 (summary model) → DHR-2 (formatter) → DHR-3 (orchestration)
→ DHR-4 (docs + epic archive).

---

## DHR-1 — Remove Dhan from the summary model

**Files to change:**
- `src/portfolio/summary.py` — `PortfolioSummary`, `_build_portfolio_summary`
- (`src/models/portfolio.py` if `PortfolioSummary` lives there instead — grep to confirm
  which module is canonical after `finideas-decommission/` FD-3)
- `tests/unit/portfolio/` — summary tests

**Before any code (graph queries):**
- `get_code_snippet("PortfolioSummary")` — the field list as FD-3 left it.
- `trace_path("_build_portfolio_summary")` — every caller and every field consumer, so DHR-2
  and DHR-3 cover them.
- `search_graph("DhanPortfolioSummary")` — confirm the only summary-layer consumer is here
  (the `src/dhan/` producers stay).

**What to implement:**

1. Remove the `dhan` field from `PortfolioSummary` and the `dhan_summary` parameter from
   `_build_portfolio_summary`.
2. Drop every Dhan term:
   - `dhan_eq_value` / `dhan_eq_basis` / `dhan_bd_value` / `dhan_bd_basis` locals
   - the `dhan_summary.equity_pnl` / `.bond_pnl` additions in `total_pnl`
   - the `dhan_summary.equity_day_delta` / `.bond_day_delta` additions in `total_day_delta`
     and the `any_delta` guard
   - `total_value` / `total_invested` lose the Dhan additions
3. After this, `_build_portfolio_summary` sums: MF + Nuvama bonds + Nuvama options for
   `total_value` / `total_pnl`; MF + Nuvama bond deltas for `total_day_delta`.
4. Fix the callers' signatures (they are updated fully in DHR-3, but the module must import
   and type-check now — drop the `dhan_summary=` kwarg at the call sites in
   `_format_combined_summary` and `daily_snapshot.py` in this commit if needed to keep green,
   or land DHR-1..DHR-3 as one sequence and note it).

**Tests (no network, no real DB):**
- `test_build_summary_mf_and_bonds_only` — MF + Nuvama bonds input → correct `total_value` /
  `total_pnl` / `total_day_delta`, no `dhan` attribute.
- `test_build_summary_all_none` — every source `None` → zeros, `has_deltas` false path holds.

**Commit:** `refactor(portfolio): drop Dhan terms from PortfolioSummary`

---

## DHR-2 — Remove Dhan from the snapshot formatter

**Files to change:**
- `src/portfolio/formatting.py` — `_format_combined_summary` (waterfall + fallback)
- `scripts/portfolio/daily_snapshot.py` — `_print_combined_summary` helper signature
  (`dhan_summary` param removed) — coordinate with DHR-3
- `tests/unit/portfolio/test_formatting*.py` — every golden-string assertion

**Before any code:**
- `sed -n` the waterfall Equity / Bonds blocks and the fallback `── Equity ──` /
  `── Bonds ──` sections as FD-4 left them — you are deleting specific Dhan lines, keep the
  rest byte-stable.
- `search_graph("format_options_section")` — confirm the only caller to remove is in
  `daily_snapshot.py` (the function itself stays in `src/dhan/positions.py`).

**What to implement (waterfall path):**

1. Delete the `├ Dhan Equity` / `└ Dhan Bonds` child lines and their `elif not
   summary.dhan_available: … [unavailable]` branches.
2. `eq_subtotal` / `bonds_subtotal` / `eq_day` / `bd_day` lose their Dhan terms. If a segment
   then has only one contributor (e.g. Bonds = Nuvama only), keep the parent + single child
   for consistency with the other segments, or collapse — match whatever FD-4 chose for the
   MF-only Equity case, and note it.
3. Remove the `NOTE: Dhan unavailable — Dhan values excluded from total` line.

**Fallback path:**

4. In `── Equity ──`: remove the `Dhan Equity` line + its P&L line + the `dhan_available`
   guard. In `── Bonds ──`: remove the `Dhan Bonds` line + P&L line + the `[unavailable]`
   branch; keep the `_has_any_bonds` logic working for Nuvama-only.
5. Remove the `NOTE: Dhan unavailable` line here too.

**Both paths / caller:**

6. The `📊 Dhan Options (Intraday)` block is appended by `daily_snapshot.py`
   (`summary_text + "\n\n" + dhan_options_section`), not by `_format_combined_summary` — its
   removal is DHR-3. In this commit only remove the `dhan_summary` parameter from
   `_format_combined_summary` and `_print_combined_summary` and every `summary.dhan*`
   reference.

**Tests:**
- `test_waterfall_no_dhan` — MF + Nuvama bonds + Nuvama options → output has no `Dhan`, no
  `NOTE: Dhan`, no `[unavailable]`; `Net` and `💰 Total` correct.
- `test_fallback_no_dhan` — same for `has_deltas=False`.
- `test_snapshot_mf_and_nuvama_only` — well-formed minimal message, no empty section headers.

**Commit:** `refactor(portfolio): remove Dhan holdings lines from snapshot message`

---

## DHR-3 — Strip Dhan fetches from daily_snapshot.py

**Files to change:**
- `scripts/portfolio/daily_snapshot.py`
- `tests/unit/` / `tests/integration/` snapshot-orchestration tests

**Before any code:**
- `grep -n -i "dhan" scripts/portfolio/daily_snapshot.py` — the full hit list (there are
  ~6 blocks: the `_print_combined_summary` param, the historical Dhan portfolio block, the
  historical Dhan options block, the live pre-fetch/piggyback, the live Dhan portfolio
  snapshot enrich/record, the live Dhan options block, plus the two `_format_combined_summary`
  call sites).
- Confirm with `search_graph` that nothing else in `scripts/` imports the Dhan symbols this
  file uses.

**What to implement:**

1. `_historical_main` — delete the "Dhan portfolio from stored snapshots" block and the
   "Dhan options from stored EOD snapshot" block; remove `dhan_summary=` and the
   `summary_text + "\n\n" + dhan_options_section` append from the `_format_combined_summary`
   call.
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
3. Remove now-unused imports: `from src.auth.dhan_verify import load_dhan_credentials` (if no
   longer referenced), `from src.dhan.reader import …`, `from src.dhan.positions import …`,
   `from src.dhan.store import …`, `dhan_trade_count` param on `_async_main` and its
   `--dhan-trades` CLI arg if it exists solely for the options block.
4. **Do not** modify `src/auth/dhan_verify.py`, any `src/dhan/` module, or the Dhan tables.
   `format_options_section` stays in `src/dhan/positions.py`.
5. If the `--dhan-trades` / `dhan_trade_count` plumbing is removed, update `main()` argparse
   and its tests.

**Tests:**
- `test_historical_main_no_dhan_section` — run `_historical_main` against a seeded stored
  snapshot (MF + Nuvama only) → output has no Dhan content, exit 0.
- `test_async_main_skips_dhan` (mock the clients) — the run makes no Dhan call and the
  assembled message has no Dhan block.
- `test_dhan_modules_still_import` — `import src.dhan.reader`, `src.dhan.positions`,
  `src.dhan.store`, `src.auth.dhan_verify` all succeed.

**Commit:** `refactor(snapshot): stop fetching Dhan portfolio + options in daily_snapshot`

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
