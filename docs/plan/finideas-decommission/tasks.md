# Finideas decommission — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task.
Each task = one commit unless noted. See `prompt.md` for why the story exists;
see `stories.md` for the per-task implementation spec.

History decision: **option A — hard-delete every Finideas row** (Animesh, 2026-09-10). No
`schema.md` (straight `DELETE`). FD-2..FD-4 are code; FD-5 is the DB CLI; FD-6 is example
cleanup; FD-1 and FD-7 are non-code.

**Open: FD-1, FD-2, FD-3, FD-4, FD-5, FD-6, FD-7.**

- [ ] **FD-1** — Pre-delete audit: confirm no open Finideas legs / broker positions remain;
      record the `strategies` / `legs` / `trades` / `daily_snapshots` row ids + counts FD-5
      will delete and the current all-time `Total P&L` for a before/after check.
      | Owner: Animesh | Model: n/a | Review: none | SHA: —
- [ ] **FD-2** — Delete `src/portfolio/strategies/finideas/`; drop `HedgeStrategy` + the
      `["finideas"]` provider list + `ALL_STRATEGIES` wiring; `create_strategy_instance`
      falls back to base `Strategy`.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **FD-3** — Strip `options_pnl` / `options_day_delta` / `finrakshak_day_delta` /
      Finideas-ETF terms from `_build_portfolio_summary` + `PortfolioSummary`; recompute
      `total_value` / `total_pnl` from MF + bonds + Nuvama options + Dhan.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **FD-4** — Rework `_format_combined_summary` (waterfall + fallback): remove the
      `Finideas P&L` line, the `Derivatives` options line, the `🛡 Hedge (FinRakshak)` block,
      `_format_protection_stats`, and the `Finideas ETF` line.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **FD-5** — `scripts/dev/decommission_finideas.py`: tested CLI, hard-deletes every
      `finideas_ilts` / `finrakshak` row from the four tables in one transaction
      (`--dry-run` default, `--apply` commits); update `DB_REGISTRY.md`.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **FD-6** — Seed / example cleanup: `seed_trades.py`, `seed_mf_holdings.py`,
      `record_trade.py`, `roll_leg.py`, `instrument_lookup.py`, and the `LIQUIDBEES` /
      `finideas_ilts` dedup comments in `src/dhan/reader.py` + `src/nuvama/reader.py`.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **FD-7** — Docs close: `CONTEXT.md` / `REFERENCES.md` / `CONTEXT_TREE.md` /
      `DECISIONS.md` / `src/portfolio/CLAUDE.md` / `src/portfolio/NOTES.md` /
      `docs/plan/README.md` / `TODOS.md`; archive the folder.
      | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **FD-1** — a session-log note (or a short `docs/plan/finideas-decommission/audit.md`)
  records: zero open Finideas legs confirmed, the exact row ids/counts per table, and the
  pre-delete all-time `Total P&L`.
- **FD-2** — `src/portfolio/strategies/finideas/` is gone; `ALL_STRATEGIES` is `[]` (or the
  constant is removed); no `HedgeStrategy` / `FINIDEAS_*` symbol is importable; unknown
  strategy names construct a base `Strategy`; unit tests green.
- **FD-3** — `PortfolioSummary` has no `options_pnl` / `options_day_delta` /
  `finrakshak_day_delta`; `_build_portfolio_summary` computes `total_value` / `total_pnl` /
  `total_day_delta` from MF + Dhan + Nuvama bonds + Nuvama options only; tests green.
- **FD-4** — both formatter paths render with no `Finideas P&L`, no `Derivatives` options
  line, no hedge block, no `Finideas ETF` line; a snapshot with only MF + bonds is
  well-formed; golden/string tests updated; tests green.
- **FD-5** — `decommission_finideas.py --dry-run` lists every Finideas row across the four
  tables; `--apply` deletes them in one transaction and is idempotent on a second run;
  `DB_REGISTRY.md` row counts updated; CLI has a happy-path + empty-DB test.
- **FD-6** — no `finideas` / `finrakshak` / `ilts` string remains in the named seed /
  example / lookup files except where it is explicit historical narration; the Nuvama /
  Dhan dedup guards for `LIQUIDBEES` are removed or re-justified; tests green.
- **FD-7** — all eight docs reflect the removal; `REFERENCES.md` Finideas sections deleted;
  a `DECISIONS.md` row records the decommission + option-A history choice; Feature Backlog
  line removed; folder archived to `docs/archive/plan/finideas-decommission/`.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box.
Then update this story's status in `docs/plan/README.md` and add one line to `TODOS.md`
Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do
not leave a done story half-archived.
