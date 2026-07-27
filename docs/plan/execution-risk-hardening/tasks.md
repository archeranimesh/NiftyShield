# Execution Risk Hardening — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line, top to bottom. That is your only task
> for this session. Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full spec for each task is inline below (no separate `stories.md` — grouped items are small
> enough to spec directly here).

Grouped rationale: all three items are pre-existing risk/protocol gaps around the paper-trading
execution path (`ApprovedAction`/entry-script atomicity) originally flagged during the
`paper-backbone` epic's PB1.1 post-review (now archived — see `docs/archive/plan/paper-backbone/`).
The parent story is closed; these leftover items were never individually actioned and don't
belong reopening the archived epic for.

---

- [ ] **RH-1** — Make the IC entry 4-leg subprocess sequence atomic (or add explicit
  compensation). Spawned from TODOS.md (surfaced 2026-07-03 while fixing the `--ivr`/R3-gate
  bug — see `DECISIONS.md` same date). `paper_ic_entry.py`/`paper_ic_entry_v2.py` shell out to
  `record_paper_trade.py` once per leg (short_put, long_put_hedge, short_call, long_call_hedge)
  with no rollback if a middle leg fails. That `--ivr` fix made partial-leg recording newly
  possible — previously all 4 legs failed uniformly on the crash, which was accidentally "safe."
  A naked short recorded with no offsetting long hedge is a real risk-exposure bug, not
  bookkeeping, once this path sizes real positions.

  **This needs a design decision before code** — check whether it warrants a council call per
  `docs/council/README.md`'s three-condition test (load-bearing + hard-to-reverse + spans
  multiple disciplines). Two candidate designs:
  1. In-process DB transaction across all 4 legs instead of 4 separate subprocesses.
  2. Keep the subprocess-per-leg structure but add an explicit compensating-close on partial
     failure (detect legs 1..k succeeded, k+1 failed → issue closing trades for 1..k).

  **Must be resolved before this path is used to size real (non-paper) positions** — flag this
  explicitly if this task is picked up in a context where live capital is imminent.

  **Files:** `scripts/strategies/ic/paper_ic_entry.py`, `scripts/strategies/ic/paper_ic_entry_v2.py`,
  `scripts/record/record_paper_trade.py`, their test files.

  **Before any code:**
  ```
  get_code_snippet("record_paper_trade")
  search_code("subprocess.run")           # confirm current per-leg call pattern still holds
  git log --oneline -10 scripts/strategies/ic/paper_ic_entry.py
  ```

  **Tests:** simulated mid-sequence failure (leg 3 of 4 raises) — either (a) confirm the whole
  basket rolls back with zero legs persisted (transaction design), or (b) confirm legs 1-2 are
  compensated/closed automatically (compensation design), whichever design is chosen.

  **Commit:** `fix(scripts): make IC entry 4-leg sequence atomic (or add compensating close)`

---

- [ ] **RH-2** — Enforce `strategy_name` `paper_` prefix constraint. Spawned from TODOS.md
  (PB1.1 post-review item, paper-backbone epic — now archived). Validate that concrete
  strategies use the required `paper_` prefix on `strategy_name`. Note: a related check already
  landed — `tests/unit/strategy/test_strategy_protocol.py:64-67` asserts `hasattr(mock_strategy,
  "strategy_name")` + `startswith("paper_")` for the protocol-conformance mock. This task is
  about whether that same assertion (or an equivalent guard) exists for every *concrete*
  strategy class, not just the conformance mock — verify first, this may already be done.

  **Before any code:**
  ```
  search_code("startswith(\"paper_\")")
  search_graph("PaperStrategy")            # protocol + all concrete implementers
  ```

  **If already covered** for every concrete strategy: tick this box with a verification note,
  no code change, no commit needed beyond the docs-close pass.

  **If not covered:** add a comment/guard on the `strategy_name` field or property on any
  concrete class missing the check, and assert it in that class's test file.

  **Commit (if code changes):** `test(strategy): assert paper_ prefix on <StrategyClass>.strategy_name`

---

- [ ] **RH-3** — Reconsider `council_rank: int` on `ApprovedAction`. Spawned from TODOS.md
  (PB1.1 post-review item, paper-backbone epic — now archived). Evaluate decoupling council
  rank from the action model to support a single canonical action object before building the
  executor. Given `PaperExecutor` (`executor.py`) is now fully built and `ApprovedAction`
  already carries `legs_to_close: list[LegClose]` (PG-4, 2026-07-27 — see `CONTEXT.md`
  `src/strategy/` entry and `DECISIONS.md`), this is a retrospective design review, not a
  greenfield decision — check whether `council_rank` is still load-bearing anywhere in the
  now-shipped executor/monitor path before proposing a change.

  **Before any code:**
  ```
  get_code_snippet("ApprovedAction")
  search_code("council_rank")
  ```

  **Deliverable:** a short finding — either "still load-bearing, no change" (tick with a note,
  no code) or a scoped follow-up task if genuinely worth decoupling. Do not implement a
  refactor speculatively in this task; if a change is warranted, split it into its own task
  first per the project's "one task per session" convention.

  **Commit (docs-only finding, no refactor):** `docs(strategy): council_rank review — <finding>`

---

- [ ] **RH-4** — Docs close: `TODOS.md` session log entry per task landed (RH-1 through RH-3,
  whichever subset ships). `DECISIONS.md` entry required if RH-1 lands (atomicity design is an
  architecture decision). Run only after RH-1 through RH-3 are complete.
