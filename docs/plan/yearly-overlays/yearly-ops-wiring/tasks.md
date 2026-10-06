# Yearly Ops Wiring — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit.

**Open: YW-1..YW-3.**

- [ ] **YW-1** — `monitor_daemon.py` registers yearly CC/PP/Collar instances from the policy registry behind `MONITOR_YEARLY_OVERLAYS` (default off) | Owner: Claude | Model: claude-sonnet-5-5 |
  Review: code-reviewer | SHA: —
- [ ] **YW-2** — Labels and reports: `STRATEGY_LABELS`, `eod_summary`, `eod_pt_summary`, `pre_market_brief`, 3-track overlay P&L show the yearly book as separate rows | Owner: Antigravity | Model: n/a
  | Review: greeks-analyst | SHA: —
- [ ] **YW-3** — Cron entries, runbook lines, `DB_REGISTRY.md` note (no new table) and `CONTEXT_TREE.md` update | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —

## Story done when

- **YW-1** — flag on registers 3 yearly + 3 monthly; flag off registers only monthly (test).
- **YW-2** — report builders emit distinct yearly rows; monthly rows unchanged (golden tests).
- **YW-3** — docs name the new flag, crons and the no-schema-change finding.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
