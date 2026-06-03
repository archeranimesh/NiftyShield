# Options Income Strategy — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/options_income/options_income_stories.md`.

---

- [ ] **S0** — Data audit: `scripts/audit/options_data_audit.py` + `DATA_AUDIT.md` report
- [ ] **S1** — Signal engine: `src/options_income/signal.py` — SMA, neutral zone, VIX floor, event calendar + tests
- [ ] **S2** — Strike selector: `src/options_income/strike_selector.py` — delta-based put + spread selection + tests
- [ ] **S3** — Position manager: `src/options_income/position.py` — exit logic, P&L computation + tests
- [ ] **S4** — Backtest V1: `src/options_income/backtest_v1.py` + `scripts/backtest/run_v1.py` — monthly naked put + tests
- [ ] **S5** — Backtest V2: `src/options_income/backtest_v2.py` + `scripts/backtest/run_v2.py` — quarterly spread + tests
- [ ] **S6** — Paper trading: `src/paper/options_income_runner.py` — live Upstox chain + Telegram + tests
- [ ] **S7** — Reporting: `scripts/reports/options_income_report.py` — backtest summary + comparison
- [ ] **S8** — Docs close: CONTEXT.md, DECISIONS.md, TODOS.md
