# YF-1 — Overlay hardcode audit

> Every site that hardcodes the overlay namespace, the `monthly` tenor, `date.today()` or a monthly DTE gate, for CC / PP / Collar. Line numbers are from `main` at `7c705d2` (2026-10-11). Classes:
> **tenor** (a monthly policy value), **clock** (a hidden `date.today()`), **namespace** (`STRATEGY_OVERLAY` / `paper_nifty_overlay`), **label** (a display map keyed on the namespace). Owning story is
> the one that changes the site. Docstring-only mentions of `STRATEGY_OVERLAY` are omitted. In tables, `OE` = `scripts/strategies/three_track/paper_3track_overlay_entry.py` and `SNAP` =
> `scripts/strategies/three_track/paper_3track_snapshot.py`.

## Prior-art check

`docs/refactor/code-deduplication-and-taxonomy.md` names no existing expiry-resolution helper. `InstrumentLookup.get_expiry_candidates` (`src/instruments/lookup.py:279`) already resolves the labels
`weekly`, `monthly`, `quarterly` and `yearly` (`yearly` = nearest live December, no lower DTE bound) and takes `today` and `min_expiry`. So YF-4's `resolve_overlay_expiry` wraps that one call; it adds
the `today`/policy parameters and the DTE floor, and does not re-implement the calendar logic. The resolution block is repeated three times in `paper_3track_overlay_entry.py` (CC 273-298, Collar
437-462, PP 740-766) and once in `collar_entry.py` `_resolve_expiry` (132-165, used by Collar re-entry); that is the dedup target.

## A. Expiry resolution — tenor + clock

| Site | What is hardcoded | Required change | Story |
|---|---|---|---|
| `OE:273-298` (`auto_cc_bootstrap`) | `date.today()`, `preference=["monthly"]`, `label == "monthly"`, `dte < 14` | take `today` + policy; call the shared resolver | YF-4 |
| same file `437,443,451,462` (`auto_collar_bootstrap`) | same four | same | YF-4 |
| same file `740,747,755,766` (`auto_pp_bootstrap`) | same four | same | YF-4 |
| same file `384, 540, 859` | `expiry_type="monthly"` literal on the returned `OverlayConfig` | set from the policy | YF-4 |
| same file `911` (`load_overlay_config`) | `ov.get("expiry_type", "monthly")` default | keep the default; allow `yearly` | YF-4 |
| same file `517` | `expiries=[("monthly", expiry_str)]` passed into the Collar leg build | use the policy label | YF-4 |
| `collar_entry.py:148-160` (`_resolve_expiry`) | `closing_dte <= 5`, `preference=["monthly"]`, `"monthly"` label | policy `roll_dte`; reuse `min_expiry` for the roll | YF-4, `yearly-collar` |
| `src/strategy/reentry_mixin.py:181` | `dte < 14` re-entry gate (reads a tenor-agnostic `expiry` already) | read `entry_min_dte` from the instance's policy | YF-3 / YF-4 |
| `src/strategy/exit_signals.py:374` (`evaluate_cc`) | `dte <= 5` -> `DTE_REVIEW` auto-close (EC-5) | `review_dte` from policy, passed as a parameter (pure method) | YF-3, `yearly-cc` |
| same file `484, 521` (`evaluate_pp`, `evaluate_roll_overlay`) | `dte <= 5` / `dte > 5` PP roll window | `roll_dte` from policy | YF-3, `yearly-pp` |
| `src/strategy/collar_overlay_v1.py:39-47,436` | `DTE_REVIEW (DTE<=5)` is the only time-based Collar trigger | same | `yearly-collar` |
| `OE:138,1442,1475` (`_PP_ROLL_DTE_THRESHOLD = 5`) | constant; `main()` no-ops a PP roll when DTE > 5 | policy `roll_dte` | `yearly-pp` |
| same file `642` (`_open_pp_dte`) | `today = date.today()` inside the open-PP DTE helper | inject `today` | YF-4 |
| `src/strategy/overlay_closer.py:451` | `"Evaluate replacement" if dte >= 14` note | policy `entry_min_dte` (cosmetic note) | `yearly-pp` |
| `scripts/strategies/three_track/paper_3track_snapshot.py:430` | base-leg expiry check `dte > 5` | not an overlay site (base `ditm_call` roll); leave | out of epic |
| same file `2124` | fallback `preference=["monthly","quarterly"]` when no positions carry an expiry | not an overlay site; leave | out of epic |

Strategy classes and the engines do not call `date.today()`: `CCOverlayV1`, `PPOverlayV1`, `CollarOverlayV1`, `overlay_closer` and `auto_close` use `market_today()`
(`src/market_calendar/holidays.py:124`, IST-aware, the repo's documented replacement for `date.today()` in strategy and roll logic). That is a module-level function, so tests monkeypatch it rather
than inject a value. The three bootstraps, `_open_pp_dte` and `collar_entry` take their clock from the naive `date.today()` (server locale), the one the `market_today` docstring warns about: on a UTC
host the date flips at 05:30 IST and DTE is off by one exactly when the <=5 gates fire. YF-4's `today` parameter should default to `market_today()`, not `date.today()`. YF-2's frozen-clock helper can
build on the same monkeypatch pattern (already used in `tests/unit/strategy/test_collar_overlay_v1.py`). Callers of `get_expiry_candidates` outside the overlay path (IC, CSP, signals, pipeline
scripts, `find_strike_by_delta`, `record_paper_trade`) are untouched.

## B. Namespace — `STRATEGY_OVERLAY` / `paper_nifty_overlay`

Definition: `src/paper/constants.py:37`. Shared by CC, PP and Collar and split by `leg_role`.

| Site | Use | Required change | Story |
|---|---|---|---|
| `cc_/pp_overlay_v1.py:55`, `collar_overlay_v1.py:74` | field default `strategy_name = STRATEGY_OVERLAY` | none; a yearly instance passes another name | YF-3 (constant only) |
| `scripts/monitor_daemon.py:445-447` | registers one instance per overlay class, default name | add yearly instances behind their own flag | `yearly-ops-wiring` YW |
| `src/strategy/reentry_mixin.py:54` (`_reentry_headline_label`) | `== STRATEGY_OVERLAY` picks the leg-role label map; other names hit `strategy_label()` (raises) | recognise yearly | YF-5 |
| `src/strategy/auto_close.py:409-437` | PP re-entry notify: active-leg check and P&L read `STRATEGY_OVERLAY`; builds `PPOverlayV1` with the default name | use the instance namespace | YF-5 |
| `src/risk/collateral_gate.py:55-57` (`_COLLATERAL_DRAWING_STRATEGIES`) | namespaces that draw on the collateral pool | add the yearly name (default: shared pool; Animesh to confirm) | YF-5 |
| `src/portfolio/overlay_coverage.py:73-75` | `get_trades` / `get_position` on `STRATEGY_OVERLAY` for coverage | include the yearly name as a separate row | YF-5 |
| `src/reporting/eod_pt_summary.py:267, 440` (maps at 91, 113) | open and closed legs read `STRATEGY_OVERLAY`; leg-role labels | read both namespaces; label the yearly book | YF-5 |
| `src/paper/track_snapshot.py:42,195-202` | docstring contract: overlay legs are read via `STRATEGY_OVERLAY` directly | verify no code path assumes one overlay name | YF-5 |
| `scripts/portfolio/paper_snapshot.py:150` | `if name == STRATEGY_OVERLAY` branch | extend to the yearly name | YF-5 |
| `scripts/pre_market_brief.py:221` | `if name == STRATEGY_OVERLAY` branch (overlay sub-rows) | extend to the yearly name | `yearly-ops-wiring` |
| `OE:631,1010,1032-1151,1249,1525` | `_open_pp_dte`, `_query_open_call_role`, `build_overlay_trades` (11), `_has_open_overlay_leg`, skip, collateral | thread a namespace arg | YF-4, `yearly-cc` |
| `src/strategy/collar_entry.py:269, 279` | `strategy_name=STRATEGY_OVERLAY` on the Collar entry trades | parameterise | `yearly-collar` |
| `SNAP` (28 sites, 1247-2252) | EOD snapshot persists/reads overlay legs and P&L under `STRATEGY_OVERLAY` | loop both namespaces or take it per call | `yearly-ops-wiring` (see file budget) |
| `src/paper/cycle_pnl.py:323` | **private literal** `_OVERLAY_STRATEGY = "paper_nifty_overlay"` (not from `constants.py`); feeds `LegGroup` 349/355 | import the constant; accept a namespace | YF-5 |
| `src/notifications/formatting.py:662` | label map `"paper_nifty_overlay"`; `strategy_label()` raises if unmapped | add yearly name + leg-role labels | YF-5 / `yearly-ops-wiring` |
| `scripts/dev/migrate_overlay_pnl_attribution.py` (18), `scripts/dev/migrate_3track_close_duplicate_overlays.py:79` | one-off historical migrations | none | out of epic |

## C. Schema — no change needed for a second namespace

A distinct `strategy_name` string is enough; every key that matters already includes it (`src/paper/store.py`):

- `paper_trades`: `UNIQUE(strategy_name, leg_role, instrument_key, trade_date, action)` (line 70).
- `paper_leg_snapshots`: `PRIMARY KEY (strategy_name, leg_role, snapshot_date)` (110).
- `paper_overlay_pnl_snapshots`: `PRIMARY KEY (strategy_name, overlay_type, snapshot_date)` (259).
- `paper_nav_snapshots`: `UNIQUE(strategy_name, snapshot_date)` (84). `paper_strategies`: `strategy_name TEXT PRIMARY KEY` (213), no foreign key to it from any table.
- No `CHECK` constrains `strategy_name`; the only `CHECK`s are on `state` (69, 533, 584).

So a second namespace needs **no DDL for the namespace itself**. Separately, the data-source-routing council ruling adds four additive `TEXT NULL` provenance columns (`delta_source`, `delta_asof` on
`paper_leg_snapshots`; `chain_source`, `chain_fetched_at` on `paper_overlay_pnl_snapshots`; spec in `data-source-routing/ds-chain-monitoring/schema.md`). That is `ds-chain-monitoring` DSN-2's change,
not this epic's, and it must not be recorded here as "no schema change at all". The `docs/plan/README.md` blurb "No DB schema change expected" should read "none for the namespace; provenance columns
come from `ds-chain-monitoring`".

## D. Findings that affect later stories

1. **Dead zone before the Dec 2026 roll.** `get_expiry_candidates(preference=["yearly"])` returns the nearest live December with no lower DTE bound, so on 2026-12-15 it is Dec 2026 at DTE 14 and on
   2026-12-24 DTE 5. With the monthly gates copied (entry >= 14, review <= 5), the yearly CC auto-closes at DTE 5 (2026-12-24) and re-entry is blocked until Dec 2026 stops being listed. Dec 2027
   appears as the nearest December only after 2026-12-29. YF-4's resolver needs the existing `min_expiry` parameter for the roll, and YF-3's yearly `review_dte` / `roll_dte` are real decisions, not
   defaults to copy.
2. **No overlay-specific `--expiry-type` exists yet.** `main()` (`paper_3track_overlay_entry.py:1338`) has no such flag; `expiry_type` is only an `OverlayConfig` field set from the literals above.
3. **`strategy_label()` raises on an unmapped name** (`reentry_mixin.py:46-60`, `ValueError`). A yearly instance that skips the label map fails at its first re-entry notice, not at construction.
4. **Hidden second source of truth:** the `cycle_pnl.py:323` literal. A rename of the constant would not reach it.

## Outside the epic's file budget

`paper_3track_snapshot.py` carries 28 namespace sites in a 2,300-line script. The epic README's budget lists `reentry_mixin`, `collateral_gate`, `auto_close`, `overlay_coverage`, `eod_pt_summary` and
`track_snapshot`, and does not list this script, `cycle_pnl.py`, `paper_snapshot.py`, `pre_market_brief.py` or `formatting.py`. YF-5 as written ("six consumers") undercounts; the extra consumers are
`cycle_pnl.py`, `paper_snapshot.py`, `formatting.py` (YF-5) and `paper_3track_snapshot.py`, `pre_market_brief.py` (`yearly-ops-wiring`). Recommendation: keep YF-5 to the read paths listed in section B
under YF-5 and move the snapshot script to `yearly-ops-wiring`, where it already belongs (daily persistence and reporting).

## Summary by story

| Story | Sites |
|---|---|
| YF-3 | tenor policy values + `STRATEGY_OVERLAY_YEARLY` constant; `review_dte`, `roll_dte`, `entry_min_dte` consumed by A |
| YF-4 | three bootstrap resolution blocks, `expiry_type` literals, `_open_pp_dte` clock, namespace threading in `paper_3track_overlay_entry.py`, `collar_entry._resolve_expiry` |
| YF-5 | `reentry_mixin`, `auto_close`, `collateral_gate`, `overlay_coverage`, `eod_pt_summary`, `track_snapshot`, `cycle_pnl`, `paper_snapshot`, `formatting` |
| `yearly-cc` / `yearly-pp` / `yearly-collar` | exit thresholds in `exit_signals`, `_PP_ROLL_DTE_THRESHOLD`, `overlay_closer` note, Collar entry trades |
| `yearly-ops-wiring` | `monitor_daemon` registration, `paper_3track_snapshot.py`, `pre_market_brief.py`, label maps |
