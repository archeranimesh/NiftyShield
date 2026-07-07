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
