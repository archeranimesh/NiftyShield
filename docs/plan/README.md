# `docs/plan/` — Story Index

> Each story folder is self-contained. Start from its `prompt.md`.
> Archived original files: `docs/archive/plan/`.
> Confirmed defects in shipped code (not forward spec work): [`docs/bugs/`](../bugs/) — same
> folder conventions, separate registry. See also root [`BUGS.md`](../../BUGS.md) (legacy,
> superseded).

---

## Active Epics

| Folder | What it covers | Status |
|--------|---------------|--------|
| `dev-foundation/` | Engineering excellence epic — tooling, CI, code health (3 sub-stories) | ✅ Shipped/Archived |
| `full-repo-review-followups/` | 9 stories spawned from the full-repo-review epic's FR-7 Chairman Synthesis (7 CRITICAL + 2 selected ERROR findings, all independently re-verified) — P0: portfolio P&L fix, DB backup cron; P1: docs staleness, Telegram auth fix; P2: CLAUDE.md/REVIEW.md reconciliation, logging migration; P3: Greeks/parity validation (council-gated), golden tests, suppression hygiene. Priority order and dependencies in the epic's own `README.md`. | ⬜ Not started — start with the P0 folders |
| `3track-consolidation/` (archived) | Overlay (CC/PP/Collar) retired on Futures/Proxy, live only on NiftyBees; base-leg-only daily comparison snapshot (+ Nifty spot as 4th series); automated base-leg rolling (Futures/DITM); full unattended automation (`NiftyTrackComparisonV1.auto_execute=True`, one-time bootstrap entry, Telegram on every trade event); CC/PP/Collar delta-based strike-selection + automated entry sub-threads | All tasks complete (S0–S9, CC1–CC5, PP1–PP5, Collar1–Collar3b) — ✅ Shipped/Archived 2026-08-04, see `docs/archive/plan/3track-consolidation/` |

---

## Active Stories

| Folder | What it covers | Next task | Status |
|--------|---------------|-----------|--------|
| `risk-gamma-phase-a/` | Risk delta gate (done) + Near-Expiry Gamma Buy `gamma_daily_watch.py` | B2.2 — chain fetch + field computation | 🔄 In progress |
| `variance-gate/` | CSP v1 Phase 0.8 deployment gate — spec reconciliation + gate criteria A–D | VG0 — CSP v1 spec reconciliation | ⬜ Not started |
| `paper-backbone/` | Strategy Monitor daemon + pluggable strategy backbone (`src/strategy/`, `TelegramGateway`) | All tasks complete | ✅ Shipped/Archived |
| `mvp/` | Multi-bagger Value Picks Tracker (`src/mvp/`, `scripts/mvp.py`, `scripts/mvp_watch.py`) | M1 — models + store | ⬜ Not started |
| `council-refactor/` | Remove `RapidCouncil` from daemon approval path; fix `send_approval_request` signature bug; add deterministic backtestable roll rules (`evaluate_roll_csp`, `evaluate_roll_overlay`) to `ExitSignalEngine` | All tasks complete | ✅ Shipped/Archived |
| `ic-nifty-v2/` | IronCondorV2: 25Δ/22Δ high-delta IC with 10Δ wings, partial-roll adjustment, DTE-tiered exit — 6 code stories + docs close | All tasks complete | ✅ Shipped/Archived |
| `paper-exit-codification/` (archived) | Codify q11+q12 council rulings: TIME_STOP/DTE_REVIEW priority fix in `evaluate_cc`; StrategyMonitor observability logs | All tasks complete | ✅ Shipped/Archived 2026-08-04, see `docs/archive/plan/paper-exit-codification/` |
| `telegram-leg-labels/` | Replace raw Upstox instrument keys in Telegram prose messages with human-readable `NIFTY 22000 CE 07 JUL 26` labels; CLI command lines stay untouched | TL-1 — formatter in `src/instruments/lookup.py` | ⬜ Not started |
| `ic-yearly-expiry-fix/` | Fix `InstrumentLookup.get_expiry_candidates()`'s `"yearly"` label — currently matches June or December whichever clears a 201–420 DTE band, causing IC V1's yearly bucket to resolve June 2027 instead of December 2026 on 2026-07-08; per Animesh, NSE Nifty's annual contract is always December's last Tuesday | YE-1..YE-4 superseded 2026-07-22 by a separately-triggered fix matching the same spec (see DECISIONS.md BUG-015); WG-1 (weekly Greeks snapshot gap) still open | 🔄 Partially superseded — WG-1 open |
| `greeks-bs-fallback/` | Upstox returns all-zero `option_greeks` (delta/gamma/theta/vega/iv) for far-dated NIFTY contracts (confirmed 2026-07-22 for the Dec 2026 yearly bucket, DTE 160; re-confirmed persistent 2026-08-06) despite the chain having real, liquid `ltp`/`bid`/`ask`/`oi`/`volume` — a data gap, not illiquidity. Blocks all delta-based IC entry for the yearly bucket. Per Animesh's decision: compute Greeks ourselves (BS pricer + Newton-Raphson IV solver from mid price) rather than fall back to a cruder points/percentage-OTM heuristic. | GF-1 — monthly + quarterly confirmed clean (both to be used as GF-5 validation ground truth); weekly still unaudited (not yet in capture pipeline); 3 open modeling decisions (risk-free rate, DTE convention, delta tolerance) still need Animesh's call | 🔄 Partially scoped |
| `chain-decay-analysis/` | Empirical check: does intraday option premium move track delta (+gamma/theta/vega decomposition), or is there a persistent residual — and which strikes/moneyness bands decay faster than theta alone predicts. Uses existing 5-min intraday chain Parquet (`data/historical/option_chain/intraday/`, capturing since 2026-06-01). Monthly bucket only — yearly excluded (zero-Greeks defect, see `greeks-bs-fallback/`), quarterly deferred to a later pass. | CDA-1 — paired-snapshot reader | ⬜ Not started |
| `full-repo-review/` | One-time multi-model, multi-persona review of design docs, source, tests, the AI-collaboration prompting protocol, and which surface (Claude Code / Cowork / Antigravity) to use per job type — Opus/Fable/Sonnet assigned per task by capability, not cost, validated by a Fable-vs-Opus pilot before the Fable tasks run; output is a synthesized findings folder + spawned follow-up story stubs | FR-1..FR-9 complete — see `full-repo-review-followups/` epic above | ✅ Complete |
| `ic-time-stop-dte-tiering/` (archived) | Council-ruled fix (`docs/council/2026-08-05_ic-time-stop-dte-tiering.md`): `ic_expiry_config.py`'s per-bucket `time_stop_dte`/`dte_warn` de-tiered from entry-DTE-scaled values to a uniform terminal rule (`time_stop_dte=7`/`dte_warn=14` for monthly/leaps/yearly, weekly unchanged); paired with forward-only counterfactual DTE-mark logging on `paper_exit_events` for a post-6-monthly-cycle review | All tasks complete (DT-1..DT-4) | ✅ Shipped/Archived 2026-08-05, see `docs/archive/plan/ic-time-stop-dte-tiering/` |
| `monitor-and-close-hardening/` (archived) | StrategyMonitor tick-loop observability + auto-close leg-resolution hardening: dedupe `expiry_unresolved` double-logging (MC-1); audit exit-signal gating degradation window (MC-2, no fix needed); resolve `ROLL_WING`/`PROFIT_LOCK_ZONE2` replacement-leg `instrument_key` via BOD instead of a fabricated key (MC-3a/BUG-023) and persist the close+open atomically (MC-3b/IC-CLOSE-2); route CC/PP/Collar leg finders through the shared BOD-fallback utility (MC-4); resolve IC V2 entry-leg `instrument_key` via BOD (MC-6/BUG-024) | All tasks complete (MC-1, MC-2, MC-3a, MC-3b, MC-4, MC-6, MC-5) | ✅ Shipped/Archived 2026-08-06, see `docs/archive/plan/monitor-and-close-hardening/` |

---

## Blocked / Later Stories

| Folder | Blocked by |
|--------|------------|
| `backtest-eval-core/` | Phase 1.3 (Bhavcopy) + Phase 1.4 (BacktestEngine) |
| `signals-eval-core/` | backtest-eval-core + Phase 1.12 gate |
| `signals/` | signals-eval-core |

---

## Conventions (summary)

Each story folder contains:
- `prompt.md` — what the story covers, session start protocol, task overview
- `*_tasks.md` — checklist; find the first unchecked item and do only that
- `*_stories.md` — detailed implementation spec per task
- `*_schema.md` or `*_spec.md` — data models / spec (where applicable)

Full conventions (naming, status transitions, maintenance rules): `docs/archive/plan/README.md`.
