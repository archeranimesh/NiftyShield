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
| `dev-foundation/` | Engineering excellence epic — tooling, CI, code health (3 sub-stories) | ⬜ Not started |

---

## Active Stories

| Folder | What it covers | Next task | Status |
|--------|---------------|-----------|--------|
| `risk-gamma-phase-a/` | Risk delta gate (done) + Near-Expiry Gamma Buy `gamma_daily_watch.py` | B2.2 — chain fetch + field computation | 🔄 In progress |
| `variance-gate/` | CSP v1 Phase 0.8 deployment gate — spec reconciliation + gate criteria A–D | VG0 — CSP v1 spec reconciliation | ⬜ Not started |
| `paper-backbone/` | Strategy Monitor daemon + pluggable strategy backbone (`src/strategy/`, `TelegramGateway`) | PT-0 infra | ⬜ Not started |
| `mvp/` | Multi-bagger Value Picks Tracker (`src/mvp/`, `scripts/mvp.py`, `scripts/mvp_watch.py`) | M1 — models + store | ⬜ Not started |
| `council-refactor/` | Remove `RapidCouncil` from daemon approval path; fix `send_approval_request` signature bug; add deterministic backtestable roll rules (`evaluate_roll_csp`, `evaluate_roll_overlay`) to `ExitSignalEngine` | CR0 — fix approval flow signature | ⬜ Not started |
| `ic-nifty-v2/` | IronCondorV2: 25Δ/22Δ high-delta IC with 10Δ wings, partial-roll adjustment, DTE-tiered exit — 6 code stories + docs close | IC-V2-0 — config dataclass | ⬜ Not started |
| `paper-exit-codification/` | Codify q11+q12 council rulings: TIME_STOP/DTE_REVIEW priority fix in `evaluate_cc`; StrategyMonitor observability logs | EC-1 — TIME_STOP priority fix | ⬜ Not started |

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
