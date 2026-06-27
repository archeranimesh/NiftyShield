# Iron Condor V2 — Task Checklist

> Find the first unchecked `- [ ]` line. That is the only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/ic-nifty-v2/stories.md`.
> Council ruling — core design: `docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md` Stage 3.
> Council ruling — profit-lock: `docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md` Stage 3.

**Executor key:**
- `[A:sonnet]` — Antigravity, claude-sonnet-4-6 (mechanical TDD loop, fully spec'd, no inline judgment calls)
- `[C:haiku]` — Claude, claude-haiku-4-5 (graph queries, doc edits, registration)
- `[C:sonnet]` — Claude, claude-sonnet-4-6 (inline judgment calls, precedence design, wiring work)
- `[C:opus]`  — Claude, claude-opus-4-6 (code review gate — financial logic, floor formula, precedence ladder)

**Review policy:**
- IC-V2-8, IC-V2-10: `@code-reviewer (opus)` mandatory per-commit (financial math + precedence)
- All other tasks: `@code-reviewer (sonnet)` per-commit
- IC-V2-12: final `@code-reviewer (opus)` sweep across full Phase 1+2 diff before closing

---

## Phase 1 — Core IC V2

- [x] **IC-V2-0** `[A:sonnet]` — Config dataclass: `src/strategy/ic_expiry_config_v2.py` — delta-based config replacing fixed wing_width_points + tests | SHA: 9bcb838
- [x] **IC-V2-1** `[C:sonnet]` — Entry logic: `src/strategy/ic_nifty_v2.py` — 25Δ/22Δ short selection, 10Δ wing placement, SD sanity guard, liquidity floors + tests | SHA: f3e0423
- [x] **IC-V2-2** `[A:sonnet]` — Adjustment logic: partial roll of challenged vertical — 4-leg atomic close+reopen, 7 roll guards (debit cap, inverted condor, max_rolls, width expansion) + tests | SHA: b8942d9
- [x] **IC-V2-3** `[A:sonnet]` — DTE-tiered exit: monthly hard-close DTE≤7, FORCE_CLOSE DTE≤1 + tests | SHA: 5b0de55
- [x] **IC-V2-4** `[C:sonnet]` — Signal integration: wire `DELTA_WARN / ROLL_WING / DELTA_STOP / FORCED_CLOSE` signal hierarchy into `check_signals()`, PaperStrategy protocol compliance + tests | SHA: cf81258
- [x] **IC-V2-5** `[C:haiku]` — Registration: add `paper_ic_nifty_v2_monthly` to strategy factory / entry script; verify strategy name persists in DB schema + tests | SHA: 91d0bc7
- [x] **IC-V2-6** `[C:haiku]` — Docs close: CONTEXT.md module tree, CONTEXT_TREE.md, TODOS.md session log — no code | SHA: pending-git-lock

## Phase 2 — Profit-Lock Adjustment
> Council ruling: `docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md` Stage 3.
> All profit-lock actions are auto_execute=True. No Telegram approval gate — notification only after execution.

- [ ] **IC-V2-7** `[A:sonnet]` — Profit-lock config: `ProfitLockConfig` dataclass + zone thresholds + DTE/IV/debit guards added to `ic_expiry_config_v2.py` + tests
- [ ] **IC-V2-8** `[A:sonnet]` — Profit-lock engine: `src/strategy/profit_lock_engine.py` — stateless evaluator; floor formula `max(W,W)+D_cum+D_lock+K ≤ 0.75×C₀`; wing selector; 3-zone decision; 14 tests including exact numeric spot-checks
- [ ] **IC-V2-9** `[A:sonnet]` — State persistence: `paper_strategies` schema migration + `PaperStore.get/set/reset_profit_lock_state()` + tests
- [ ] **IC-V2-10** `[C:sonnet]` — Signal wiring: profit-lock into `IronCondorV2.check_signals()` — 8-level precedence ladder, auto_execute path, post-execution Telegram notification (not approval) + tests
- [ ] **IC-V2-11** `[A:sonnet]` — V1 vs V2 monthly comparison: `scripts/strategies/ic/paper_ic_monthly_comparison.py` — `ICMonthlyStats`, side-by-side Telegram report, cron `45 15 * * 1-5` + tests

## Phase 3 — Docs Close (after Phase 2)

- [ ] **IC-V2-12** `[C:haiku]` — Final docs: CONTEXT.md, CONTEXT_TREE.md, DECISIONS.md, TODOS.md — reflect profit-lock + comparison modules — no code
