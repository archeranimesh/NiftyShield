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
      new format, including the FMT-1c timeframe color/emoji/hashtag header (all 5 active
      variants: V1 weekly/monthly/leaps/yearly + V2 monthly) | Blocked by: `backbone/` +
      `formatting-rules/` complete (data sources: `ROLL-0` for Net Δ/θ, `FMT-1c` for the header —
      both soft dependencies, see `ROLL-1`'s spec for what happens if sequencing is reversed)
- [ ] **ROLL-2** — Migrate IC monthly comparison report
      (`scripts/strategies/ic/paper_ic_monthly_comparison.py`) to a single fenced comparison
      table; adds Legs row (`open_pos`, already available), Bkd P&L (I) (via
      `get_strategy_realized_pnl()` — NOT `paper_nav_snapshots.realized_pnl`'s raw row, which
      resets on a close/reopen cycle per `CONTEXT.md` SNAP-1), and Flt P&L (M) (genuinely new
      `_get_unrealized_pnl_month_change()`, must differ from Flt (I) — see stories.md for why).
      Hand-counted width bug already fixed (TGFMT-1, SHA `a69d817`) — not this task's job.
      | Blocked by: ROLL-1
- [ ] **ROLL-3** — Migrate strategy close/roll notifications (7 classes, same list as
      backbone MD-3) to the new format where it adds value | Blocked by: ROLL-2
- [ ] **ROLL-4** — Migrate approval-request message formatting
      (`TelegramGateway.send_approval_request`) — coordinate with
      `telegram-approval-auth-fix` first | Blocked by: ROLL-3
- [ ] **ROLL-6** — Migrate EOD Paper Summary (`scripts/eod_summary.py`) to
      `TelegramNotifier.send()` + MarkdownV2 — not in the epic's original confirmed-callers
      list (currently sends via raw HTML, missed by `backbone/`'s audit); v2 format confirmed
      2026-08-08 on-device (4 buckets — Track/IC/Overlay/CSP, 12 strategies total —
      totals-first subtotal rows, `FMT-1d` integer-money exception + zero-as-`-`, `FMT-1e`
      ASCII-only-inside-fence rule, `Bkd` sourced from `get_strategy_realized_pnl()`
      since-inception not the resettable snapshot column, `#EOD_SUMMARY` tag after the fence)
      | Blocked by: `backbone/` + `formatting-rules/` complete (same soft deps as other ROLL
      tasks) — financial-logic commit note: `Bkd` sourcing is P&L-adjacent, real
      `@code-reviewer` required
- [ ] **ROLL-5** — Docs close | Blocked by: ROLL-4, ROLL-6
