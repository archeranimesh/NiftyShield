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
| `3track-consolidation/` | Overlay (CC/PP/Collar) retired on Futures/Proxy, live only on NiftyBees; base-leg-only daily comparison snapshot (+ Nifty spot as 4th series); automated base-leg rolling (Futures/DITM); full unattended automation (`NiftyTrackComparisonV1.auto_execute=True`, one-time bootstrap entry, Telegram on every trade event); plus an independent CC delta-based strike-selector sub-thread (CC1–CC3: per-strategy delta ladder, entry-delta-band decision gate, automated CC entry script + Wednesday cron) | S1r/S2r/S3/S3r/S4/S5/S6/S0/S7/S8/S9 shipped (see TODOS.md); **CC1 shipped (2026-08-01)** — CC1/CC2/CC3/PP1–3/Collar1–3 next |

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
| `paper-exit-codification/` | Codify q11+q12 council rulings: TIME_STOP/DTE_REVIEW priority fix in `evaluate_cc`; StrategyMonitor observability logs | EC-1 — TIME_STOP priority fix | ⬜ Not started |
| `telegram-leg-labels/` | Replace raw Upstox instrument keys in Telegram prose messages with human-readable `NIFTY 22000 CE 07 JUL 26` labels; CLI command lines stay untouched | TL-1 — formatter in `src/instruments/lookup.py` | ⬜ Not started |
| `ic-yearly-expiry-fix/` | Fix `InstrumentLookup.get_expiry_candidates()`'s `"yearly"` label — currently matches June or December whichever clears a 201–420 DTE band, causing IC V1's yearly bucket to resolve June 2027 instead of December 2026 on 2026-07-08; per Animesh, NSE Nifty's annual contract is always December's last Tuesday | YE-1..YE-4 superseded 2026-07-22 by a separately-triggered fix matching the same spec (see DECISIONS.md BUG-015); WG-1 (weekly Greeks snapshot gap) still open | 🔄 Partially superseded — WG-1 open |
| `greeks-bs-fallback/` | Upstox returns all-zero `option_greeks` (delta/gamma/theta/vega/iv) for far-dated NIFTY contracts (confirmed 2026-07-22 for the Dec 2026 yearly bucket, DTE 160) despite the chain having real, liquid `ltp`/`bid`/`ask`/`oi`/`volume` — a data gap, not illiquidity. Blocks all delta-based IC entry for the yearly bucket. Per Animesh's decision: compute Greeks ourselves (BS pricer + Newton-Raphson IV solver from mid price) rather than fall back to a cruder points/percentage-OTM heuristic. | GF-1 — audit scope + pick a known-good validation chain | ⬜ Not started |
| `full-repo-review/` | One-time multi-model, multi-persona review of design docs, source, tests, the AI-collaboration prompting protocol, and which surface (Claude Code / Cowork / Antigravity) to use per job type — Opus/Fable/Sonnet assigned per task by capability, not cost, validated by a Fable-vs-Opus pilot before the Fable tasks run; output is a synthesized findings folder + spawned follow-up story stubs | FR-1..FR-9 complete — see `full-repo-review-followups/` epic above | ✅ Complete |

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
