# Dhan holdings removal — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task.
Each task = one commit unless noted. See `prompt.md` for why the story exists;
see `stories.md` for the per-task implementation spec.

Sub-story 2 of the `portfolio-snapshot-slimdown/` epic. Depends on `finideas-decommission/`
— do not start DHR-1 before every FD box is ticked (its epic `README.md` Stories row is ✅).
Both sub-stories edit `_build_portfolio_summary` + `_format_combined_summary`; this one
rebases onto the shape FD-3 / FD-4 left them in. DHR-4 is the epic close. No `schema.md`.

**Open: DHR-1, DHR-2, DHR-3, DHR-4.**

- [ ] **DHR-1** — Remove the `dhan` field from `PortfolioSummary` and the `dhan_summary`
      param + every equity/bond value/basis/pnl/day-delta term from `_build_portfolio_summary`
      (`total_value` / `total_invested` / `total_pnl` / `total_day_delta` / `any_delta`).
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **DHR-2** — Remove Dhan from `_format_combined_summary` (waterfall + fallback): the
      Dhan Equity / Dhan Bonds lines + sections, `NOTE: Dhan unavailable`, `[unavailable]`
      placeholders; drop the `📊 Dhan Options (Intraday)` appended section + the
      `_print_combined_summary` `dhan_summary` arg. Update golden-string tests same commit.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **DHR-3** — `scripts/portfolio/daily_snapshot.py`: remove the Dhan portfolio
      snapshot-fetch/record blocks + Dhan options blocks (both `_historical_main` and
      `_async_main`), the `dhan_summary` / `dhan_options_section` wiring, and the Dhan
      holdings pre-fetch + Upstox-key piggyback. `src/auth/dhan_verify` + `src/dhan/`
      untouched.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **DHR-4** — Epic close: `CONTEXT.md` / `src/portfolio/CLAUDE.md` / `DECISIONS.md` /
      `DB_REGISTRY.md`; flip the last epic `README.md` Stories row + **Epic done when**;
      `git mv` the whole `portfolio-snapshot-slimdown/` folder to `docs/archive/plan/`;
      collapse the `docs/plan/README.md` epic entry to a pointer; move the `TODOS.md`
      Feature Backlog line to `TODOS_ARCHIVE.md`.
      | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **DHR-1** — `PortfolioSummary` has no `dhan` attribute; `_build_portfolio_summary` has no
  `dhan_summary` parameter; `total_value` / `total_invested` / `total_pnl` / `total_day_delta`
  are computed from MF + Nuvama bonds + Nuvama options only; a summary built with no Dhan
  input is correct; tests green.
- **DHR-2** — both formatter paths render with no `Dhan Equity` / `Dhan Bonds` line, no
  `NOTE: Dhan unavailable`, no `[unavailable]` Dhan placeholder, and no `📊 Dhan Options
  (Intraday)` block; an MF-plus-Nuvama-bonds snapshot is well-formed (no empty headers,
  no dangling separators); golden-string tests updated; tests green.
- **DHR-3** — `daily_snapshot.py` makes no Dhan portfolio or options fetch in either path;
  no `dhan_summary` / `dhan_options_section` / `_dhan_holdings_prefetched` symbol remains;
  `load_dhan_credentials` and every `src/dhan/` module still import cleanly; a live-path
  dry run (or its test) produces the slimmed message; tests green.
- **DHR-4** — `CONTEXT.md`, `src/portfolio/CLAUDE.md`, `DECISIONS.md`, `DB_REGISTRY.md`
  (Dhan tables marked frozen, not removed) reflect the change; every epic `README.md`
  Stories row is ✅ and its **Epic done when** block is satisfied; the epic folder is
  archived to `docs/archive/plan/portfolio-snapshot-slimdown/`; the `docs/plan/README.md`
  epic entry is a one-line pointer; the `TODOS.md` Feature Backlog line moved to
  `TODOS_ARCHIVE.md`.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box.
Then flip this sub-story's row in the epic `README.md` **Stories** table and add one line to
`TODOS.md` Session Log. At DHR-4, follow `docs/plan/README.md` §Conventions
*Completion → archive* for the whole epic folder.
