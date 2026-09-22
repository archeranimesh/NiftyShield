# Options Income Strategy — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: S0, S1, S2, S3, S4, S5, S6, S7, S8.**

- [ ] **S0** — Data audit: `scripts/audit/options_data_audit.py` + `DATA_AUDIT.md` report | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **S1** — Signal engine: SMA, neutral zone, VIX floor, event calendar + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **S2** — Strike selector: delta-based put + spread selection + tests | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: <—>
- [ ] **S3** — Position manager: exit logic, P&L computation + tests | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: <—>
- [ ] **S4** — Backtest V1: monthly naked put simulation + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **S5** — Backtest V2: quarterly spread simulation + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **S6** — Paper trading: live Upstox chain + Telegram + tests | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: <—>
- [ ] **S7** — Reporting: backtest summary + V1/V2 comparison | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **S8** — Docs close: CONTEXT.md, DECISIONS.md, TODOS.md | Owner: Claude | Model: n/a | Review: none | SHA: <—>

## Story done when

- **S0** — `DATA_AUDIT.md` shows completeness % per year 2018–present with a PROCEED/GAPS recommendation.
- **S1** — `get_signal` returns the correct `SignalResult` for every filter combination in the story spec's test list.
- **S2** — `find_put_strike` / `find_spread` return the correct strike(s) or `None` per the story spec's test list.
- **S3** — `check_exit` / `close_position` apply the documented priority order and produce correct P&L.
- **S4** — `BacktestV1.run` produces a trade log and `compute_metrics` returns all documented keys.
- **S5** — `BacktestV2.run` mirrors V1 with spread mechanics; `spread_efficiency` present in metrics.
- **S6** — `OptionsIncomeRunner.run_daily` opens/closes positions correctly against `MockBrokerClient` with Telegram alerts, never raising when `notifier=None`.
- **S7** — `options_income_report.py` prints V1 summary, V2 summary, comparison, and active paper positions.
- **S8** — `CONTEXT.md`, `DECISIONS.md`, `TODOS.md` reflect the shipped module.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in `docs/plan/README.md` and add one line to `TODOS.md` Session Log. When the whole story is done,
follow §Conventions *Completion → archive* — do not leave a done story half-archived.
