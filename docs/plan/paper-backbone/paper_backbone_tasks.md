# paper-backbone — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md` session log.
> Full story spec for each task: `docs/plan/paper-backbone/paper_backbone_stories.md`.
>
> **Prerequisite check before PB1.1:** Confirm `PortfolioDeltaTracker` (Task 2) is committed.
> Run `search_graph("PortfolioDeltaTracker")` — must return results. If not, stop.

---

## Phase PT-0 — Common Infrastructure

- [ ] **PB1.1** — `src/strategy/protocol.py`: `PaperStrategy` protocol + `SignalEvent` + `ApprovedAction` + `LegSpec` models + tests
- [ ] **PB1.2** — `src/strategy/monitor.py`: `StrategyMonitor` (registry + tick + signal routing + heartbeat) + tests
- [ ] **PB1.3** — `src/strategy/executor.py`: `PaperExecutor` + `PaperFillSimulator` (VIX-regime slippage) + tests
- [ ] **PB1.4** — `src/council/rapid.py`: `RapidCouncil` (parallel Stage 1 + chairman synthesis + timeout handling) + tests
- [ ] **PB1.5** — `src/notifications/telegram_gateway.py`: `TelegramGateway` (approval request + inbound polling + auth guard + timeout scan) + tests
- [ ] **PB1.6** — `src/paper/store.py`: DB migrations for `pending_approvals` + `council_outputs` + `daemon_heartbeat` + store methods + tests
- [ ] **PB1.7** — Scripts: `monitor_daemon.py` + `start_monitor.py` + `stop_monitor.py` + `pre_market_brief.py` + `eod_summary.py` + `requirements.txt`

## Phase PT-S0 — CSP v1 (Backbone Integration)

- [ ] **PB2.1** — `src/strategy/csp_nifty_v1.py`: `CSPNiftyV1` implements `PaperStrategy` — `check_signals` + `apply_action` + tests

## Phase PT-S1 — Iron Condor v1 (Backbone Integration)

- [ ] **PB3.1** — `src/strategy/ic_nifty_v1.py`: `IronCondorV1` implements `PaperStrategy` — `check_signals` + `apply_action` + tests

## Phase PT-S3 — 3-Track Comparison (Backbone Integration)

- [ ] **PB4.1** — `src/strategy/nifty_track_comparison_v1.py`: `NiftyTrackComparisonV1` implements `PaperStrategy` — `check_signals` (WARN only) + tests

## Docs Close

- [ ] **PB5** — Docs close: `CONTEXT.md` tree, `DECISIONS.md` entry, `TODOS.md` session log
