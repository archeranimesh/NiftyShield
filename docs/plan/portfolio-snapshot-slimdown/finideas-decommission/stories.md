# Finideas decommission — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, flip this sub-story's row in
> the epic `README.md` **Stories** table, add one line to `TODOS.md`. See
> `docs/plan/README.md` §Conventions.

Sub-story 1 of the `portfolio-snapshot-slimdown/` epic.

History decision: **option A — hard-delete every Finideas row** (Animesh, 2026-09-10). No
`schema.md`: FD-5 is a straight `DELETE` across existing tables, no new table.

Recommended commit order and phase boundaries: FD-2 (strategy layer) → FD-3 (summary model)
→ FD-4 (formatter) → FD-5 (DB CLI) → FD-6 (examples) → FD-7 (docs). FD-1 first, and it may be
done by Animesh outside a Claude session.

---

## FD-1 — Pre-delete audit

**Files to change / create:**
- `docs/plan/finideas-decommission/audit.md` (new, no task checkboxes) — the recorded result.

**What to do (mostly read-only DB + broker check):**

1. Confirm at the broker / from Animesh that `EBBETF0431`, `LIQUIDBEES`, and any remaining
   `finideas_ilts` / `finrakshak` option legs are actually closed — not merely untracked.
   Per `CONTEXT.md` (~2026-07-14) the JUL legs and the DEC PE hedge were already closed
   manually; `finideas_ilts` "currently holds only the EBBETF0431 leg". Verify that is still
   true and that the ETF position itself is exited.
2. Query `portfolio.sqlite` and record, per table, the row ids + counts that FD-5 will
   delete: `strategies` (the 2 rows), `legs` (via `strategy_id`), `trades` (via
   `strategy_name`), `daily_snapshots` (via `leg_id` → `legs` → `strategy_id`). Use scoped
   `COUNT(*)` / `SELECT id` — never a full table dump (Rule 1).
3. Record the current all-time `Total P&L` and `Total value` from a live or most-recent
   snapshot, so FD-3's recomputed figure can be sanity-checked against
   `old_total_pnl − finideas_realized_pnl ≈ new_total_pnl`.

**No tests** (audit only). **Commit:** `docs(plan): finideas-decommission FD-1 pre-delete audit`
(or fold into the FD-2 commit if Animesh runs the audit inline — note it either way in the
Session Log).

---

## FD-2 — Remove the strategy-provider layer

**Files to change:**
- delete `src/portfolio/strategies/finideas/` (`__init__.py`, `ilts.py`, `finrakshak.py`)
- `src/portfolio/strategies/__init__.py` — drop the `finideas` import + `ALL_STRATEGIES`;
  if the module has no other purpose, reduce it to an empty registry aggregator or delete it
  and fix importers.
- `src/models/portfolio.py` — remove `HedgeStrategy` (nothing else subclasses it — confirm
  with `trace_path` / `search_graph`); in `create_strategy_instance` remove the
  `for provider in ["finideas"]` dynamic-import block so an unregistered name just returns
  the base `Strategy`.
- `tests/unit/` — delete `strategies/finideas` tests; update model-factory + registry tests.

**Before any code (graph queries):**
- `search_graph("HedgeStrategy")` — every reference and subclass.
- `search_graph("ALL_STRATEGIES")` / `search_graph("FINIDEAS_STRATEGIES")` — importers.
- `trace_path("create_strategy_instance")` — callers that assume a non-empty registry.
- `trace_path("get_protection_delta")` — confirm `src/portfolio/summary.py` is the only
  consumer (it is removed in FD-3).

**What to implement:**

1. Delete the package and its tests.
2. Rewire `src/portfolio/strategies/__init__.py` and every importer so the project imports
   cleanly with zero strategy providers.
3. Simplify `create_strategy_instance` — keep `register_strategy_type` / `_STRATEGY_REGISTRY`
   (still the extension point) but drop the hard-coded provider loop.
4. Leave `Strategy` and `get_all_strategies()` intact — they must return `[]` gracefully.

**Tests:**
- `test_get_all_strategies_empty_registry` — with no providers, `get_all_strategies()`
  returns `[]` and does not raise.
- `test_create_strategy_instance_unknown_name_returns_base` — an arbitrary name yields a
  plain `Strategy`, no import error.

**Commit:** `refactor(portfolio): remove finideas strategy provider layer`

---

## FD-3 — Strip Finideas terms from the portfolio summary

**Files to change:**
- `src/portfolio/summary.py` — `PortfolioSummary` dataclass + `_build_portfolio_summary`
- `src/models/portfolio.py` — if `PortfolioSummary` / `finrakshak_day_delta` live there
  instead (grep both; the field is referenced at `src/portfolio/summary.py:250` and
  `src/models/portfolio.py:494` — resolve which is canonical)
- `tests/unit/portfolio/` — summary tests

**Before any code:**
- `get_code_snippet("PortfolioSummary")` — the full field list.
- `trace_path("_build_portfolio_summary")` — every field consumer (formatter, snapshot
  service, any store write).
- `search_graph("options_pnl")` / `search_graph("options_day_delta")` /
  `search_graph("finrakshak_day_delta")` — all readers, so FD-4 covers them.

**What to implement:**

1. Remove `options_pnl`, `options_day_delta`, `finrakshak_day_delta` from `PortfolioSummary`
   and every assignment in `_build_portfolio_summary`. Remove the `HedgeStrategy` isinstance
   loop and the `prev_options_pnl` / `_compute_strategy_pnl_from_prices` reconstruction.
2. `etf_value` / `etf_basis` / `etf_day_delta`: since all ETF value was `finideas_ilts`,
   remove the ETF terms too (`_etf_current_value` / `_etf_cost_basis` become dead — delete
   them and their tests unless another caller exists — check with `trace_path`).
3. Recompute:
   `total_value = mf_value + dhan_eq + dhan_bd + nuvama_bd + nuvama_options.net_pnl` (decide
   whether Nuvama options P&L stays a `total_value` term — it does today; keep it for
   continuity and note it).
   `total_pnl` = MF P&L + Dhan equity P&L + Dhan bond P&L + Nuvama bond P&L + Nuvama options
   net P&L.
   `total_day_delta` = MF + Dhan equity + Dhan bond + Nuvama bond deltas (no options term).
4. `strategies` / `strategy_pnls` / `prices` params of `_build_portfolio_summary` are now
   unused — remove them and fix callers (`daily_snapshot.py` both paths, `SnapshotService`).

**Tests:**
- `test_build_summary_no_strategies` — MF + Nuvama bonds only → correct `total_value` /
  `total_pnl` / `total_day_delta`, no attribute errors.
- `test_build_summary_all_sources_unavailable` — everything `None` → zeros, `has_deltas`
  false path still works.

**Commit:** `refactor(portfolio): drop options + hedge + ETF terms from PortfolioSummary`

---

## FD-4 — Remove Finideas lines from the snapshot formatter

**Interim step.** FD-4 only *deletes* the Finideas/hedge/ETF lines — Dhan lines stay, the
waterfall/fallback split stays. `dhan-holdings-removal/` DHR-2 then rewrites the whole
function to the epic README **Target message format**. Do not reshape here; just remove and
keep the rest byte-stable.

**Files to change:**
- `src/portfolio/formatting.py` — `_format_combined_summary` (waterfall + fallback),
  `_format_protection_stats` (delete), `_delta` / `_pnl_str` helpers stay
- `tests/unit/portfolio/test_formatting*.py` — every golden-string assertion

**Before any code:**
- `sed -n` the current waterfall block (`formatting.py` ~155–265) and fallback block
  (~280–390) — you are removing specific lines, keep the rest byte-stable.
- `search_graph("_format_protection_stats")` — confirm the only caller is the fallback path.

**What to implement (waterfall path):**

1. Delete the `Derivatives` parent line, the `├ Finideas P&L` line, and the `└ Nuvama P&L`
   child. Decide where Nuvama options P&L now reads best — either a top-level
   `📊 Nuvama Options` line in the waterfall, or leave it only in the existing detailed
   Nuvama block lower down (which already shows `Nuvama M2M P&L` etc.). Prefer the latter —
   drop it from the waterfall entirely — and note the decision.
2. Delete the `🛡 Hedge (FinRakshak)` block (the `if summary.mf_day_delta is not None and
   summary.finrakshak_day_delta is not None:` branch). The Nuvama-options detail lines that
   were nested under it move to sit directly after the waterfall `Net` line.
3. `Equity` waterfall line: drop the `├ ETF` child; `eq_day` / `eq_subtotal` lose their ETF
   term. If MF is then the only Equity child, collapse `Equity` into a single `MF` line
   (decide + note).
4. The `equity_pct` / `bonds_pct` weight figures: recompute against the new `total_value`.
   Do **not** redesign the "arrow + weight%" here — `dhan-holdings-removal/` DHR-2 drops it
   when it rewrites the formatter to the Target message format. Just correct the inputs.

**Fallback path:**

5. Remove the `── Derivatives ──` section entirely, the `Finideas ETF` line + basis line in
   `── Equity ──`, and the trailing `lines.extend(_format_protection_stats(summary))`.
6. Delete `_format_protection_stats`.

**Tests:**
- `test_waterfall_no_finideas` — MF + Nuvama bonds + Nuvama options input → output has no
  `Finideas`, no `Derivatives`, no `🛡 Hedge`, no `ETF`; `Net` and `💰 Total` lines present
  and correct.
- `test_fallback_no_finideas` — same for `has_deltas=False`.
- `test_snapshot_mf_only` — MF the only available source → well-formed minimal message.

**Commit:** `refactor(portfolio): remove finideas/hedge/ETF from snapshot message`

---

## FD-5 — DB decommission CLI

**Files to change / create:**
- `scripts/dev/decommission_finideas.py` (new) — see `scripts.dev.reflow_md` /
  `scripts.dev.cycle_pnl_report` for the house CLI shape (argparse, `_SCRIPT_NAME` logger
  per `LOGGING.md`, `--dry-run` default).
- `tests/unit/scripts/dev/test_decommission_finideas.py` (new)
- `DB_REGISTRY.md` — the `strategies` / `legs` / `trades` / `daily_snapshots` rows

**Before any code:**
- `get_code_snippet("PortfolioStore")` — the connection helper (`_connect`) and whether it
  exposes a raw transaction context.
- `search_code("DELETE FROM")` in `src/` — match the existing delete-idiom (there is a
  `delete_trade` rollback path in the paper store; the portfolio store may not have one).

**What to implement:**

1. Resolve the two strategy ids (`finideas_ilts`, `finrakshak`) → their `legs.id` set →
   delete in FK-safe order inside **one** transaction:
   `daily_snapshots WHERE leg_id IN (…)` → `trades WHERE strategy_name IN ('finideas_ilts',
   'finrakshak')` → `legs WHERE strategy_id IN (…)` → `strategies WHERE name IN (…)`.
2. `--dry-run` (default): print the per-table counts that *would* be deleted, no writes.
   `--apply`: run the transaction, print the actual deleted counts, log a
   `decommission_finideas.applied` event with the counts.
3. Idempotent: a second `--apply` on an already-clean DB deletes 0 rows and exits 0.
4. `--db-path` override for tests; default to the canonical live path from settings.
5. Do **not** wire this into any cron or the snapshot flow — it is a one-shot dev tool
   (see the [[no-throwaway-scripts-for-repeatable-ops]] memory — this belongs in
   `scripts/dev/` as a tested CLI, which is exactly what this is).

**Tests (temp SQLite, no network):**
- `test_dry_run_reports_counts_no_delete` — seed a mini DB with both strategies + legs +
  trades + snapshots; `--dry-run` reports the right counts and leaves every row.
- `test_apply_deletes_all_finideas_rows` — `--apply` empties the four tables of Finideas
  rows, leaves a non-Finideas control row untouched, second run deletes 0.

**Commit:** `feat(dev): decommission_finideas CLI — hard-delete Finideas DB rows`

Then run `python -m scripts.dev.decommission_finideas --apply` against the live DB as the
FD-5 closing action (record the deleted counts in the Session Log) and update `DB_REGISTRY.md`.

---

## FD-6 — Seed / example cleanup

**Files to change:**
- `scripts/seed/seed_trades.py` — remove the `finideas_ilts` / `finrakshak` trade rows
- `scripts/seed/seed_mf_holdings.py` — remove any FinRakshak-hedge framing (the MF holdings
  themselves stay — they are not Finideas; only the "protected by FinRakshak" narration goes)
- `scripts/record/record_trade.py`, `scripts/portfolio/roll_leg.py` — docstring / `--help`
  examples that use `ILTS` / `finideas_ilts`
- `scripts/lookup/instrument_lookup.py` — example strings
- `src/dhan/reader.py` (~line 150) and `src/nuvama/reader.py` (~line 30) — the
  `"LIQUIDBEES — tracked in finideas_ilts"` dedup comment + any exclusion list entry that
  only existed to avoid double-counting a Finideas leg; remove the entry or re-justify it if
  the ETF is still held elsewhere (FD-1 settles this).
- matching `tests/unit/`

**Before any code:**
- `git grep -n -iE "finideas|finrakshak|ilts" -- scripts/ src/dhan/ src/nuvama/` — the full
  residual list; every hit is either deleted or turned into explicit past-tense narration.

**Tests:** update the affected seed / reader tests; add
`test_nuvama_reader_no_liquidbees_exclusion` (or adjust the existing one) to lock the new
behaviour.

**Commit:** `chore(portfolio): purge finideas references from seed + reader code`

---

## FD-7 — Sub-story docs close

**Files to change:** `CONTEXT.md`, `REFERENCES.md`, `CONTEXT_TREE.md`, `DECISIONS.md`,
`src/portfolio/CLAUDE.md`, `src/portfolio/NOTES.md`,
`docs/plan/portfolio-snapshot-slimdown/README.md`, `TODOS.md`. Targeted `Edit` only, never
`Write`. **No folder archive** — the whole epic archives at `dhan-holdings-removal/` DHR-4.

**What to implement:**

1. `CONTEXT.md` — "What Exists" `src/portfolio/` bullet: drop "finideas strategies (ILTS,
   FinRakshak)"; add a dated line under the state notes recording the decommission (option A,
   rows deleted, all-time P&L recomputed). Update the ~2026-04-08 / ~2026-07-14 trade-seed
   notes to past tense with a "decommissioned 2026-09-xx" tail rather than deleting the
   history narration.
2. `REFERENCES.md` — delete §"Finideas ILTS (`finideas_ilts`)", §"Finideas FinRakshak
   (`finrakshak`)", §"FinRakshak Protected MF Portfolio". Leave a one-line pointer to this
   archived story for anyone chasing the old instrument keys.
3. `CONTEXT_TREE.md` — remove the `src/portfolio/strategies/finideas/` subtree; adjust the
   `src/portfolio/` description.
4. `DECISIONS.md` §"P&L & Reporting" (and a cross-ref line in §"daily_snapshot.py Design") —
   one dated row: Finideas product wound down; strategy-provider layer, options/hedge/ETF
   snapshot reporting, and all Finideas DB rows removed; history option A (hard delete)
   chosen over export/archive; portfolio snapshot now MF + Dhan + Nuvama bonds + Nuvama
   options (Dhan is removed next by `dhan-holdings-removal/`).
5. `src/portfolio/CLAUDE.md` + `NOTES.md` — remove Finideas/hedge invariants; note the
   strategy registry is now empty but the extension point (`register_strategy_type`) remains.
6. `docs/plan/portfolio-snapshot-slimdown/README.md` — flip the `finideas-decommission/` row
   in the **Stories** table to ✅ with the closing SHA.
7. `TODOS.md` — add a Session Log line (the Feature Backlog line is the epic's, not this
   sub-story's — it stays until DHR-4).

One commit. **Commit:** `docs: close finideas-decommission sub-story (FD-1..7)`
