# Telegram Markdown Migration — Strategy Rollout — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/telegram-markdown-migration/strategy-rollout/stories.md`.
> Sequenced by risk: informational-only messages first, live position-event notifications
> next, auth-sensitive interactive messages last.

---

- [ ] **ROLL-0** — Capture long-leg delta + theta and compute Net Δ/Net θ in the IC EOD audit
      (`scripts/strategies/ic/paper_ic_snapshot.py::process_variant`) — data-only, plain-text
      report line, no Markdown/parse_mode dependency | Blocked by: none
- [ ] **ROLL-1** — Migrate IC EOD audit (`scripts/strategies/ic/paper_ic_snapshot.py`) to the
      new format | Blocked by: `backbone/` + `formatting-rules/` complete (data source: `ROLL-0`,
      soft dependency — see `ROLL-1`'s spec for what happens if sequencing is reversed)
- [ ] **ROLL-2** — Migrate IC monthly comparison report
      (`scripts/strategies/ic/paper_ic_monthly_comparison.py`) — also fixes its hand-counted
      width bug | Blocked by: ROLL-1
- [ ] **ROLL-3** — Migrate strategy close/roll notifications (7 classes, same list as
      backbone MD-3) to the new format where it adds value | Blocked by: ROLL-2
- [ ] **ROLL-4** — Migrate approval-request message formatting
      (`TelegramGateway.send_approval_request`) — coordinate with
      `telegram-approval-auth-fix` first | Blocked by: ROLL-3
- [ ] **ROLL-5** — Docs close | Blocked by: ROLL-4
