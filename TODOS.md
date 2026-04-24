# NiftyShield — TODOs

> Open work only. Completed items and full session history:
> [docs/archive/TODOS_ARCHIVE_2026-04-24.md](docs/archive/TODOS_ARCHIVE_2026-04-24.md)

---

## Priority Key

| Label | Meaning |
|---|---|
| `P1-NEXT` | Do this sprint — unblocked, highest impact |
| `P2-EVAL` | Decision or evaluation required before any code |
| `P3-DEFER` | Explicitly deferred — reason and ETA documented |
| `P5-DEBT` | Technical debt — fix alongside adjacent refactoring only, never standalone |

---

## P1-NEXT — Greeks Capture

Story file: `docs/plan/0_2_greeks_capture.md`

Fix the option chain call, define the `OptionChain` Pydantic model, implement `_extract_greeks_from_chain()`, and wire the null Greeks columns in `daily_snapshots`.

Steps:
- Fix API call: instrument key must be `NSE_INDEX|Nifty 50`
- Define `OptionChain` Pydantic model — drive from `tests/fixtures/responses/nifty_chain_2026-04-07.json`
- Implement `_extract_greeks_from_chain()` in `src/portfolio/tracker.py` (currently returns `{}`)
- Wire Greeks columns into `daily_snapshots` (columns already exist, currently null)
- Tests: fixture-driven, fully offline

Blocked by: nothing.

---

## P2-EVAL — Nuvama Session P&L Alignment

Decision needed before any code changes.

Current `nuvama_intraday_tracker.py` shows "All-time Total P&L" — cumulative sum of all historical `realized_pnl_today` rows via `get_cumulative_realized_pnl()`. This diverges from the Nuvama mobile/web UI which shows "Session P&L" (Unrealized + Today's Realized only), causing a visible mismatch (e.g. system shows +17k, Nuvama shows -17k).

Options:
1. Keep cumulative — true inception P&L; diverges from Nuvama UI intentionally
2. Switch to session-only — matches Nuvama UI; cumulative history still in DB but not displayed

No implementation until Animesh chooses an option.

---

## P3-DEFER — P&L Visualization

Deferred until late May 2026 (need 4+ weeks of snapshot data).

Matplotlib chart or React dashboard from `daily_snapshots` time series (component breakdown over time). `PortfolioSummary` dataclass is already extracted and ready to query. Plan notes in `PLANNER.md`.

---

## P5-DEBT — Technical Debt

Fix alongside adjacent refactoring. Never worth a standalone commit.

### DEBT-1: `@staticmethod` overuse (TD-1)

Per §2.17: replace with module-level `_private_function()`. Mechanical — no logic changes.

| File | Method(s) |
|---|---|
| `src/mf/store.py` | `_row_to_transaction()`, `_row_to_nav_snapshot()` |
| `src/portfolio/store.py` | `_row_to_leg()`, `_row_to_snapshot()` |
| `src/portfolio/tracker.py` | `_extract_greeks_from_chain()` |
| `src/dhan/store.py` | `_row_to_holding()` |
| `src/instruments/lookup.py` | `_score_query()` |
| `src/client/upstox_market.py` | row-mapping helper |

### DEBT-3: Missing license boilerplate (TD-4)

License decision needed before this can be automated. Every file should carry a header once the license is chosen.

---

## Session Log

| Date | What Changed |
|---|---|
| 2026-04-24 | **Root markdown cleanup.** Archived all ✅ DONE items (PKG-1–4, DEBT-2,4,5) + session log to TODOS_ARCHIVE_2026-04-24.md. Moved `python-architecture-review.prompt.md` to `docs/`. Updated README.md project structure to actual src/ layout. Wrote `.claude/skills/md-cleanup/SKILL.md`. |

Full log (2026-04-01 → 2026-04-24): [docs/archive/TODOS_ARCHIVE_2026-04-24.md](docs/archive/TODOS_ARCHIVE_2026-04-24.md)
