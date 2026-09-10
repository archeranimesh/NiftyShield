# Dhan holdings removal — prompt

> Remove Dhan equity/bond holdings, their P&L, and the `📊 Dhan Options (Intraday)` block
> from the daily portfolio snapshot and its summary model. Keep the Dhan login flow, the
> `src/dhan/` client, and the Dhan DB tables wired and intact — this is reporting removal
> only.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else.
Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task.
Read that task's full spec in `stories.md` (same task id) before writing any code.
One task per session. Complete it fully. Stop.

## Why this story exists

Sub-story 2 of the `portfolio-snapshot-slimdown/` epic, after `finideas-decommission/`.
Animesh decided (2026-09-10) the Dhan holdings and P&L are no longer worth reporting in the
daily snapshot. The Dhan integration itself stays — the credential flow, the API client, and
the DB tables — because it may be used again; only the *snapshot reporting* is removed.

Dhan appears in the message as: `├ Dhan Equity` / `└ Dhan Bonds` lines under `Equity` /
`Bonds` (waterfall) and full `Dhan Equity` / `Dhan Bonds` sections (fallback), their
contribution to `💰 Total` / `Total invested` / `Total P&L`, the `NOTE: Dhan unavailable`
line and `[unavailable]` placeholders, and the standalone `📊 Dhan Options (Intraday)` block
appended at the end. All of that goes.

`finideas-decommission/` already reworked `_build_portfolio_summary` and
`_format_combined_summary` to drop the Finideas terms — this story rebases onto that shape
and drops the Dhan terms next. After it, the daily snapshot reports **MF + Nuvama bonds +
Nuvama options** only.

## Scope guard

**In bounds:** `src/portfolio/summary.py` (`PortfolioSummary`, `_build_portfolio_summary`) ·
`src/portfolio/formatting.py` (`_format_combined_summary` waterfall + fallback) ·
`scripts/portfolio/daily_snapshot.py` (`_print_combined_summary` helper, the Dhan portfolio
snapshot fetch/record blocks in both `_historical_main` and `_async_main`, the Dhan options
blocks in both paths, the `dhan_summary` / `dhan_options_section` wiring, and the Dhan
holdings pre-fetch / Upstox-key piggyback) · `tests/unit/**` for the above · `DB_REGISTRY.md`
(note the Dhan tables are now frozen) · `CONTEXT.md` / `src/portfolio/CLAUDE.md` /
`DECISIONS.md` / the epic `README.md`.

**Out of bounds — do not touch:** `src/auth/dhan_verify.py` and `load_dhan_credentials` ·
`src/dhan/` client modules (`reader.py`, `positions.py`, `store.py`, models) — they stay
importable and tested · the `dhan_holdings` / `dhan_options` / margin / `dhan` snapshot
tables — retained, not dropped, just no longer written · the Upstox LTP fetch mechanism ·
the Nuvama / MF paths beyond removing any Dhan coupling · `format_options_section` in
`src/dhan/positions.py` (it stays for potential reuse — only its *caller* in
`daily_snapshot.py` is removed).

Changes `src/` and `scripts/` behaviour: the daily snapshot no longer reports any Dhan
value, and `daily_snapshot.py` no longer calls the Dhan portfolio or options fetch.

## Session-start load hints

- `finideas-decommission/` `stories.md` (sibling sub-story, may be archived with the epic) —
  the shape FD-3 / FD-4 left `_build_portfolio_summary` and `_format_combined_summary` in.
- `src/portfolio/CLAUDE.md` — auto-loads; the snapshot section invariants.
- `DECISIONS.md` §"daily_snapshot.py Design" and §"Dhan Portfolio Integration" — the row a
  DHR-4 line references / amends.
- `DB_REGISTRY.md` — the Dhan tables; DHR-4 marks them frozen, not removed.
- No council file. No `schema.md`.

## Task overview

Target: the epic README **Target message format** — read it first; it is the spec for
DHR-1's totals math and DHR-2's layout.

- **DHR-1** — `PortfolioSummary` + `_build_portfolio_summary`: drop the `dhan` field +
  `dhan_summary` param + every Dhan term; Nuvama options P&L **out of** `total_value` /
  `total_pnl` / `total_invested` (decision 2); add a `nuvama_options_day_delta` field —
  `(unrealized now − unrealized on prev trading day) + realized today`, via a new
  `prev_nuvama_options_unrealized` param — and fold it into `total_day_delta` + the
  `has_deltas` guard (decision 5, the true-daily-delta fix). No schema change — the prior
  unrealized comes from the existing `nuvama_options_snapshots` rows.
- **DHR-2** — Rewrite `_format_combined_summary` to the Target message format: one fenced
  block, `📊 Today` / `📦 Holdings` / `📈 Nuvama options`, no Dhan, no waterfall/fallback
  split, no `▲/▼` weight-percent; `Realized month` MTD-inclusive; `Nifty H/L` when both
  present. Replace the golden-string tests wholesale. Drop the `_print_combined_summary`
  `dhan_summary` arg.
- **DHR-3** — `scripts/portfolio/daily_snapshot.py`: remove the Dhan portfolio
  snapshot-fetch/record blocks (both paths), the Dhan options blocks (both paths), the
  `dhan_summary` / `dhan_options_section` wiring, and the Dhan holdings pre-fetch + piggyback
  (nothing consumes the keys once Finideas + Dhan holdings are gone). Send the now-fenced
  `summary_text` as-is — no `escape_markdown` of the whole string. Keep
  `load_dhan_credentials` importable; leave `src/auth/dhan_verify` + `src/dhan/` untouched.
- **DHR-4** — Epic close: `CONTEXT.md`, `src/portfolio/CLAUDE.md`, `DECISIONS.md`,
  `DB_REGISTRY.md`, the epic `README.md` (last Stories row + **Epic done when**); `git mv`
  the whole `portfolio-snapshot-slimdown/` folder to `docs/archive/plan/`; collapse the
  `docs/plan/README.md` epic entry to a pointer; move the `TODOS.md` line to
  `TODOS_ARCHIVE.md`.

## Definition of done

The daily portfolio snapshot matches the epic README **Target message format** exactly — one
fenced block, `📊 Today` / `📦 Holdings` / `📈 Nuvama options`, no Dhan anything, Nuvama
options P&L out of `Total` value, `Realized month` MTD-inclusive, `Nifty H/L` when available.
`PortfolioSummary` has no `dhan` field; `_build_portfolio_summary` and
`_format_combined_summary` take no `dhan_summary` argument; `total_value` / `total_pnl`
exclude options P&L; `total_day_delta` includes a true Nuvama-options daily delta
(`nuvama_options_day_delta`). `scripts/portfolio/daily_snapshot.py`
makes no Dhan portfolio or options fetch call and sends the fenced message without
`escape_markdown`. `src/auth/dhan_verify` and every `src/dhan/` module import cleanly and
their tests pass unchanged. The Dhan DB tables still exist. All
unit tests green. Epic docs updated and the whole epic folder archived per §Conventions
*Completion → archive*.

## Perspectives not covered

Whether "keep fetching price information" (Animesh, 2026-09-10) means the Dhan holdings
pre-fetch / Upstox-key piggyback should stay running even with no consumer. This story reads
it as "keep the Dhan integration importable and working", and DHR-3 removes the now-orphaned
pre-fetch because after `finideas-decommission/` there are no `NSE_EQ|` instruments left to
price. If Animesh wants Dhan kept as a live price source for a future feature, that is a
separate story — flag it at DHR-3 rather than half-keeping the code. Also: the Dhan DB tables
are retained but will accumulate no new rows; a later cleanup could drop them.
