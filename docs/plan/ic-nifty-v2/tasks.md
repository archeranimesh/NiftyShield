# Iron Condor V2 — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/ic-nifty-v2/stories.md`.
> Council ruling (authoritative): `docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md` Stage 3.

---

- [ ] **IC-V2-0** — Config dataclass: `src/strategy/ic_expiry_config_v2.py` — delta-based config replacing fixed wing_width_points + tests
- [ ] **IC-V2-1** — Entry logic: `src/strategy/ic_nifty_v2.py` — 25Δ/22Δ short selection, 10Δ wing placement, SD sanity guard, liquidity floors + tests
- [ ] **IC-V2-2** — Adjustment logic: partial roll of challenged vertical — 4-leg atomic close+reopen, roll guards (debit cap, inverted condor, max_rolls) + tests
- [ ] **IC-V2-3** — DTE-tiered exit: weekly DTE table (≥6 / 4–5 / ≤3 / ≤1), CLOSE_FULL logic, monthly hard-close DTE≤7 + tests
- [ ] **IC-V2-4** — Signal integration: wire `DELTA_WARN / ROLL_WING / DELTA_STOP / FORCED_CLOSE` signal hierarchy into `check_signals()`, update `PaperStrategy` protocol compliance + tests
- [ ] **IC-V2-5** — Registration: add `paper_ic_nifty_v2_weekly` and `paper_ic_nifty_v2_monthly` to strategy factory / entry script; verify strategy names persist in DB schema + tests
- [ ] **IC-V2-6** — Docs close: CONTEXT.md module tree, CONTEXT_TREE.md, TODOS.md session log — no code
