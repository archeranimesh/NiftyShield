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
- **`total_value` / `total_invested` / `total_pnl` recompute** from MF + Nuvama bonds only (Nuvama options P&L is **not** a value term — see *Target message format*). `total_day_delta` = MF delta +
  bond delta + Nuvama options **daily delta** (`(unrealized today − unrealized prev day) + realized today`, prior day from the stored options snapshot — no schema change). `total_pnl_pct` stays
  `total_pnl / total_invested`.
- **The waterfall and fallback formatter paths both change** in each sub-story — do not fix one and leave the other. `dhan-holdings-removal/` DHR-2 then collapses the two into the single *Target
  message format* layout.
- **Golden-string / snapshot tests are updated in the same commit** as the code that changes the output — never a separate "fix the tests" commit.
- **Sub-stories are not individually archived.** Each sub-story close flips its row in this file's **Stories** table; the whole epic folder is archived in one move at DHR-4.

## Target message format

The north-star output after both sub-stories. `finideas-decommission/` FD-4 is an interim step toward this (Dhan lines still present); `dhan-holdings-removal/` DHR-1 + DHR-2 land it exactly. This
supersedes the current waterfall / fallback split — there is now **one layout** (the "no prior-day data" case just omits the `📊 Today` block).

Decisions confirmed with Animesh, 2026-09-10: (1) render as a single MarkdownV2 **fenced code block** — content emitted literally, no per-value escaping, columns align; (2) Nuvama options P&L is
**not** a portfolio-value term — `💰 Total` is MF value + Nuvama bond value only, and its P&L excludes options; (3) `Realized month` is **month-to-date including today** (`monthly_realized_pnl +
total_realized_pnl_today`); (4) show a `Nifty H/L` line when `nifty_high` / `nifty_low` are both present; (5) every `📊 Today` row is a **true since-previous-trading-day delta**, including Nuvama
options; (6) `📦 Holdings` P&L is lifetime since purchase — `mf_transactions` / Nuvama bond basis hold the full purchase history (confirmed), so the label is a plain `P&L`, no "since 2026" qualifier.

```
🟢 NiftyShield · 2026-09-09

📊 Today                     +2,52,265
   Mutual funds              +2,45,120
   Nuvama bonds                 +5,126
   Nuvama options               +2,019
   ──────────────────────────────────
   Net                      +2,52,265

📦 Holdings
   Mutual funds    ₹41,90,300   +6,05,900   +16.9%
   Nuvama bonds    ₹ 2,22,882     +12,656    +6.0%
   ──────────────────────────────────
   Total           ₹44,13,182   +6,18,556   +16.3%

📈 Nuvama options
   Open M2M                     +2,019
   M2M today  H/L        +2,019 / -3,460
   Nifty      H/L      24,150 / 23,980
   Realized today                   +0
   Realized month (MTD)        +25,683
   Realized total            +1,41,865
```

Field sources — **`📊 Today` = `total_day_delta` = the sum of three since-previous-trading-day deltas:**

- `mf_day_delta` = today's MF value − MF value on `prev_trading_day(snap_date)` (from `mf_nav_snapshots`; carries the known AMFI-publish-lag caveat).
- `nuvama_bonds.total_day_delta` = Σ (`current_value × chgP%`) — Nuvama's own broker day-change percent, so already a since-yesterday figure.
- `nuvama_options_day_delta` = `(Σ unrealized_pnl today − Σ unrealized_pnl on prev_trading_day) + Σ realized_pnl_today`. The prior-day unrealized comes from
  `NuvamaStore.get_options_snapshot_for_date(prev_trading_day(snap_date))` — the `nuvama_options_snapshots` table already stores per-position `unrealized_pnl` / `realized_pnl_today`, so **no schema
  change**. This replaces the `net_pnl` property for the daily total (`net_pnl` = lifetime-open + today-realized was *not* a true daily delta). `net_pnl` stays on the model for any other caller.

`📦 Holdings` rows = `mf_pnl.total_current_value` / `.total_pnl` / `.total_pnl_pct` and `nuvama_bonds.total_value` / `.total_pnl` / `.total_pnl_pct` — **lifetime since purchase** (`mf_transactions`
BUY−SELL and the Nuvama bond basis are full history). `Total` = their sums: `total_value` = MF value + bond value; `total_pnl` likewise; `total_pnl_pct` = `total_pnl / total_invested` where
`total_invested` = MF invested + bond basis. Nuvama options P&L is **excluded** from all three `Total` terms.

`📈 Nuvama options` — this section still shows the *position-level* figures (not deltas): `Open M2M` = `total_unrealized_pnl` (lifetime paper P&L on the open book); `M2M today H/L` = `intraday_high` /
`intraday_low`; `Nifty H/L` = `nifty_high` / `nifty_low` (omit the line if either is `None`); `Realized today` = `total_realized_pnl_today`; `Realized month (MTD)` = `monthly_realized_pnl +
total_realized_pnl_today`; `Realized total` = `total_realized_pnl_today + cumulative_realized_pnl`. Only the `Nuvama options` row up in `📊 Today` is the delta.

Degraded states: a failed source renders `[fetch failed]` on its `📊 Today` and `📦 Holdings` lines, is excluded from `Net` and `Total`, and adds one `⚠ <source> excluded` line under `Total`. Nuvama
options unavailable → omit the whole `📈 Nuvama options` section and the `Nuvama options` row in `📊 Today`. No prior-day data (`has_deltas` false) → omit the entire `📊 Today` block; lead with `📦
Holdings`. The header 🟢/🔴 follows the sign of `total_day_delta` (or `total_pnl` when there is no delta).

Not in this epic's scope but noted: the fenced block means `daily_snapshot.py` must stop wrapping the whole string in `escape_markdown()` and instead emit ```` ``` ```` fences with literal content
(DHR-2 / DHR-3).

## Supersession / coordination

- The Finideas ETF (`EBBETF0431` / `LIQUIDBEES`) and the Dhan equity holdings were the only `NSE_EQ|` instruments in the Upstox LTP batch. After both sub-stories, `daily_snapshot.py` fetches only
  Nifty spot from Upstox — `dhan-holdings-removal/` DHR-3 decides whether the Dhan holdings pre-fetch / piggyback stays (dormant, "keep fetching price information") or is removed with the rest.
- Not related to `telegram-message-unification/` — that epic is the paper-strategy entry/exit cards; this is the live portfolio snapshot, a different message family.

## Epic done when

- **`finideas-decommission`** — `get_all_strategies()` returns `[]`; the `src/portfolio/strategies/finideas/` package is gone; the snapshot (both paths) has no `Finideas P&L`, no `Derivatives` line,
  no `🛡 Hedge (FinRakshak)` block, no ETF value; `scripts/dev/decommission_finideas.py --apply` has removed every Finideas row from `strategies` / `legs` / `trades` / `daily_snapshots`;
  `DB_REGISTRY.md` updated.
- **`dhan-holdings-removal`** — the daily snapshot matches the *Target message format* above exactly: one fenced block, `📊 Today` / `📦 Holdings` / `📈 Nuvama options`, no Dhan anything, options P&L out
  of `Total` value, every `📊 Today` row a true since-previous-trading-day delta (including a `nuvama_options_day_delta` computed from the stored options snapshot — no schema change), `Realized month`
  MTD-inclusive, `Nifty H/L` when available. `PortfolioSummary` has no `dhan` term; the summary functions take no `dhan_summary` argument; `daily_snapshot.py` builds no Dhan section and fences the
  message instead of `escape_markdown`-ing it; `src/auth/dhan_verify` and `src/dhan/` are untouched and still import cleanly; the Dhan DB tables are retained.
