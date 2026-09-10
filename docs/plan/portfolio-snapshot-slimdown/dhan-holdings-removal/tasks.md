# Dhan holdings removal — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

Sub-story 2 of the `portfolio-snapshot-slimdown/` epic. Depends on `finideas-decommission/` — do not start DHR-1 before every FD box is ticked (its epic `README.md` Stories row is ✅). Both sub-stories
edit `_build_portfolio_summary` + `_format_combined_summary`; this one rebases onto the shape FD-3 / FD-4 left them in and lands the epic README **Target message format** (read it first). DHR-4 is the
epic close. No `schema.md`.

**Open: DHR-1, DHR-2, DHR-3, DHR-4.**

- [ ] **DHR-1** — `PortfolioSummary` + `_build_portfolio_summary`: drop the `dhan` field +
      `dhan_summary` param + every Dhan term; Nuvama options P&L **out of** `total_value` /
      `total_pnl` / `total_invested`; add a `nuvama_options_day_delta` field = `(unrealized
      now − unrealized prev day) + realized today` (new `prev_nuvama_options_unrealized`
      param) and fold it into `total_day_delta` + the `has_deltas` guard.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **DHR-2** — Rewrite `_format_combined_summary` to the epic README **Target message
      format**: one fenced layout — `📊 Today` / `📦 Holdings` / `📈 Nuvama options` — no
      Dhan, no waterfall/fallback split, no weight-percent; drop the `_print_combined_summary`
      `dhan_summary` arg. Replace the golden-string tests wholesale, same commit.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **DHR-3** — `scripts/portfolio/daily_snapshot.py`: remove the Dhan portfolio
      snapshot-fetch/record blocks + Dhan options blocks (both `_historical_main` and
      `_async_main`), the `dhan_summary` / `dhan_options_section` wiring, and the Dhan
      holdings pre-fetch + Upstox-key piggyback; send the now-fenced `summary_text` as-is
      (no `escape_markdown` of the whole string). `src/auth/dhan_verify` + `src/dhan/`
      untouched.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **DHR-4** — Epic close: `CONTEXT.md` / `src/portfolio/CLAUDE.md` / `DECISIONS.md` /
      `DB_REGISTRY.md`; flip the last epic `README.md` Stories row + **Epic done when**;
      `git mv` the whole `portfolio-snapshot-slimdown/` folder to `docs/archive/plan/`;
      collapse the `docs/plan/README.md` epic entry to a pointer; move the `TODOS.md`
      Feature Backlog line to `TODOS_ARCHIVE.md`.
      | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **DHR-1** — `PortfolioSummary` has no `dhan` attribute; `_build_portfolio_summary` has no `dhan_summary` parameter; `total_value` / `total_pnl` / `total_invested` are MF + Nuvama bonds only (options
  P&L excluded); `nuvama_options_day_delta` = `(unrealized now − unrealized prev day) + realized today` (or `None` without a prior snapshot); `total_day_delta` = MF delta + bond delta +
  `nuvama_options_day_delta`; an options-only move sets `has_deltas` true; tests green.
- **DHR-2** — `_format_combined_summary` emits exactly the epic README **Target message format**: one fenced block, `📊 Today` / `📦 Holdings` / `📈 Nuvama options`, no Dhan, no weight-percent, `Realized
  month (MTD)` = month + today, `Nifty H/L` shown when both present; degraded states per the spec; the old waterfall/fallback golden tests are replaced with exact-string matches; tests green.
- **DHR-3** — `daily_snapshot.py` makes no Dhan portfolio or options fetch in either path; both paths pass `prev_nuvama_options_unrealized` (summed from
  `get_options_snapshot_for_date(prev_trading_day(...))`) into the summary; no `dhan_summary` / `dhan_options_section` / `_dhan_holdings_prefetched` symbol remains; the live-path send hands the fenced
  `summary_text` to `notifier.send` without `escape_markdown`; `load_dhan_credentials` and every `src/dhan/` module still import cleanly; tests green.
- **DHR-4** — `CONTEXT.md`, `src/portfolio/CLAUDE.md`, `DECISIONS.md`, `DB_REGISTRY.md` (Dhan tables marked frozen, not removed) reflect the change; every epic `README.md` Stories row is ✅ and its
  **Epic done when** block is satisfied; the epic folder is archived to `docs/archive/plan/portfolio-snapshot-slimdown/`; the `docs/plan/README.md` epic entry is a one-line pointer; the `TODOS.md`
  Feature Backlog line moved to `TODOS_ARCHIVE.md`.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then flip this sub-story's row in the epic `README.md` **Stories** table and add one line to `TODOS.md` Session Log. At DHR-4,
follow `docs/plan/README.md` §Conventions *Completion → archive* for the whole epic folder.
