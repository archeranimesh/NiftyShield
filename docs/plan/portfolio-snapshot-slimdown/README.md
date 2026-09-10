# Portfolio snapshot slimdown — epic index

> Shed two data sources from the daily portfolio snapshot (`daily_snapshot.py` → `_format_combined_summary`): the Finideas strategies (fully — code + DB) and the Dhan holdings / P&L reporting
> (message + summary only, keeping the Dhan integration wired). One epic because both sub-stories rework the same two functions — `_build_portfolio_summary` and `_format_combined_summary` — to drop a
> source, and doing them as disconnected stories would touch those files twice with a near-certain merge conflict.

## Why this epic exists

Animesh is winding down two things at once (both decided 2026-09-10):

- **Finideas** — the ILTS overlay, its ETF legs (`EBBETF0431` / `LIQUIDBEES`), and the `finrakshak` MF hedge. Not worth running. Remove everything: the `src/portfolio/strategies/` provider layer
  (finideas is the *only* provider), the options / hedge / ETF terms in the snapshot, and every Finideas row in `portfolio.sqlite` (history option A — hard delete, no archive).
- **Dhan holdings + P&L** — the `├ Dhan Equity` / `└ Dhan Bonds` lines, their contribution to `💰 Total`, and the whole `📊 Dhan Options (Intraday)` block. The Dhan **login flow and API client stay
  wired and working** (credential plumbing, `src/auth/dhan_verify`, `src/dhan/` modules) — only the *reporting* is removed. Dhan portfolio DB tables are retained (frozen, no new rows), not dropped.

After both sub-stories the daily snapshot reports **MF + Nuvama bonds + Nuvama options** only, and `get_all_strategies()` returns `[]`.

## Scope decisions

Confirmed with Animesh, 2026-09-10:

- **Finideas: full removal, hard-delete DB rows (option A).** No archive table, no export. Accepted consequence: the all-time `Total P&L` drops the realized Finideas P&L that was in the closed
  history, and that history is not recoverable from the DB.
- **Dhan: message + summary + orchestration only.** Do **not** touch `src/auth/dhan_verify`, the `src/dhan/` client modules, or `load_dhan_credentials`. Do **not** drop the `dhan_holdings` /
  `dhan_options` / margin tables — they stop being written, nothing more.
- **The `📊 Dhan Options (Intraday)` block is removed** along with the holdings — it is P&L reporting in the same category.
- **Order is fixed: `finideas-decommission/` first, then `dhan-holdings-removal/`.** Both edit `_build_portfolio_summary` and `_format_combined_summary`; they must not be interleaved. Finideas is the
  deeper change and was scoped first.
- **No `schema.md` anywhere in the epic.** Finideas is a straight `DELETE`; Dhan drops no schema.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `finideas-decommission/` | Full removal of `finideas_ilts` + `finrakshak` — strategy layer, options/hedge/ETF snapshot terms, every Finideas DB row (FD-1..7) | ⬜ Not started | — | — |
| `dhan-holdings-removal/` | Remove Dhan holdings + P&L + the Dhan Options block from the snapshot; keep the Dhan integration wired (DHR-1..4) | ⬜ | `finideas-decommission` | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`.

## Cross-cutting constraints

- **Both sub-stories rework `_build_portfolio_summary` + `_format_combined_summary`.** Run them in order, never interleaved. The second sub-story rebases onto whatever shape the first left those
  functions in.
- **The snapshot must render with a single remaining source.** After each removal, a snapshot with only MF (or only MF + one bond source) must be well-formed — no empty section headers, no dangling
  separators, no `NOTE:` line referring to a removed source.
- **`total_value` / `total_invested` / `total_pnl` / `total_day_delta` recompute** from the surviving terms only. `total_pnl_pct` stays `total_pnl / total_invested`.
- **The waterfall and fallback formatter paths both change** in each sub-story — do not fix one and leave the other.
- **Golden-string / snapshot tests are updated in the same commit** as the code that changes the output — never a separate "fix the tests" commit.
- **Sub-stories are not individually archived.** Each sub-story close flips its row in this file's **Stories** table; the whole epic folder is archived in one move at DHR-4.

## Supersession / coordination

- The Finideas ETF (`EBBETF0431` / `LIQUIDBEES`) and the Dhan equity holdings were the only `NSE_EQ|` instruments in the Upstox LTP batch. After both sub-stories, `daily_snapshot.py` fetches only
  Nifty spot from Upstox — `dhan-holdings-removal/` DHR-3 decides whether the Dhan holdings pre-fetch / piggyback stays (dormant, "keep fetching price information") or is removed with the rest.
- Not related to `telegram-message-unification/` — that epic is the paper-strategy entry/exit cards; this is the live portfolio snapshot, a different message family.

## Epic done when

- **`finideas-decommission`** — `get_all_strategies()` returns `[]`; the `src/portfolio/strategies/finideas/` package is gone; the snapshot (both paths) has no `Finideas P&L`, no `Derivatives` line,
  no `🛡 Hedge (FinRakshak)` block, no ETF value; `scripts/dev/decommission_finideas.py --apply` has removed every Finideas row from `strategies` / `legs` / `trades` / `daily_snapshots`;
  `DB_REGISTRY.md` updated.
- **`dhan-holdings-removal`** — the snapshot (both paths) has no `Dhan Equity` / `Dhan Bonds` line, no `NOTE: Dhan unavailable`, and no `📊 Dhan Options (Intraday)` block; `PortfolioSummary` has no
  `dhan` term; `_build_portfolio_summary` / `_format_combined_summary` take no `dhan_summary` argument; `daily_snapshot.py` no longer builds a Dhan section; `src/auth/dhan_verify` and `src/dhan/` are
  untouched and still import cleanly; the Dhan DB tables are retained.
