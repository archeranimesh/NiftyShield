# Reporting & Ops Fixes — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line, top to bottom. That is your only task
> for this session. Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full spec for each task is inline below (no separate `stories.md` — grouped items are small
> enough to spec directly here).

Grouped rationale: these are unrelated small fixes (two display bugs, two ops/housekeeping
items) bundled into one story purely to avoid five near-empty directories under `docs/plan/`.
Each task is independently landable and touches different files — do not infer any shared
design intent between them.

---

- [x] **RO-1** — Fix daily breakdown columns in `paper_3track_snapshot.py`. Spawned from
  TODOS.md (detected 2026-06-29). In `--daily` mode, `Day CC`, `Day Collar`, and `Day PP`
  display **inception-to-date totals**, not 1-day deltas. Root cause: `_compute_daily_deltas`
  returns only `{base_pnl, overlay_pnl, net_pnl}`; the merge
  `{**display_rows[i], **delta_row}` leaves the inception `cc_pnl`/`collar_pnl`/`pp_pnl` from
  `summary_rows` untouched. `Day Net` is correct (computed as `base_day + overlay_day` from real
  daily deltas).

  **Fix:** extend `_compute_daily_deltas` to also return `cc_pnl`, `collar_pnl`, `pp_pnl` as
  per-role daily deltas (same loop, broken out by role name).

  **Files:** `scripts/strategies/three_track/paper_3track_snapshot.py`, its test file.

  **Before any code:**
  ```
  get_code_snippet("_compute_daily_deltas")
  git log --oneline -10 scripts/strategies/three_track/paper_3track_snapshot.py
  ```

  **Tests:** `--daily` mode output for a multi-day fixture asserts `Day CC`/`Day Collar`/
  `Day PP` are 1-day deltas, not inception totals; `Day Net` unchanged/still correct.

  **Commit:** `fix(scripts): paper_3track_snapshot --daily CC/Collar/PP show 1-day delta, not inception total` | SHA: 6096fe2

---

- [x] **RO-2** — Fix pre-market P&L for futures in `pre_market_brief.py`. Spawned from
  TODOS.md (detected 2026-06-29). During pre-market, futures have no LTP (no pre-open session),
  so `get_ltp` returns nothing and `prices.get(key, Decimal("0"))` defaults to 0 — a LONG future
  at ~24000 × 65 qty reports as a ~₹1.5M+ notional loss in unrealized P&L.

  **Fix (Option 1, as scoped in TODOS.md):** fall back to the latest `paper_leg_snapshots` row
  per strategy when live LTP is unavailable (`ltp` is `None` or `0` for a futures-sized
  position), instead of calling `compute_pnl` directly with a zeroed price. The prior EOD
  snapshot already holds the correct unrealized P&L.

  **Files:** `scripts/daemon/pre_market_brief.py`, its test file.

  **Before any code:**
  ```
  search_code("pre_market_brief")
  get_code_snippet("PaperTracker.compute_pnl")
  git log --oneline -10 scripts/daemon/pre_market_brief.py
  ```

  **Tests:** futures leg with no live LTP falls back to latest `paper_leg_snapshots` unrealized
  P&L instead of a zeroed-price notional loss; non-futures legs (where LTP is genuinely
  available pre-market) unaffected.

  **Commit:** `fix(scripts): pre_market_brief — fall back to last snapshot P&L for futures with no pre-open LTP` | SHA: 7fa175b

---

- [x] **RO-3** — Fix remaining dead `docs/council/...` links in live docs. Spawned from
  TODOS.md (2026-07-07, spawned from `docs-navigation-and-staleness` T1). That story's T1 fixed
  the two links named in its own spec (`docs/plan/variance-gate/prompt.md`, `DECISIONS.md`
  397-407) but a grep during that story's Phase C found the same dead-path pattern still live in
  `docs/plan/dev-foundation/README.md:46` and
  `docs/plan/variance-gate/variance_gate_spec.md:3,185` — both active docs, not archived
  history, worth repointing to `docs/archive/council/...`. Small, mechanical — same fix pattern
  as that story's Phase C.

  **Fix:** re-grep first (line numbers above are from the original find and may have shifted or
  already been fixed independently — verify before editing):
  ```
  grep -rn "docs/council/" docs/plan/dev-foundation/README.md docs/plan/variance-gate/variance_gate_spec.md
  ```
  Repoint any surviving dead links to their real `docs/archive/council/...` path.

  **No code-reviewer gate** — docs-only.

  **Commit:** `docs: fix remaining dead docs/council links in dev-foundation + variance-gate` | SHA: 98e781e

---

- [x] **RO-4** — Add healthcheck cron. Spawned from TODOS.md. `scripts/healthcheck.py` (CH-8,
  already shipped) is not yet wired into crontab — this is the remaining operational step.

  **Verified 2026-08-07:** `logs/cron.log` already contains a live entry —
  `55 15 * * 1-5 cd /Users/abhadra/myWork/myCode/python/NiftyShield && .venv/bin/python -m scripts.healthcheck >> logs/healthcheck.log 2>&1`
  — consistent invocation shape with every other cron line in the file (`.venv` interpreter,
  `cd`-into-repo, module form, redirected log). Runs at 15:55 IST rather than the task's
  suggested 16:30, placed right after `position_health_check`; no functional gap. Manual
  dry-run confirmation that the Telegram alert fires on failure was not re-verified in this
  session — Animesh, please confirm that's been checked, or flag if the schedule time (15:55
  vs 16:30) should change. No repo diff needed, so no commit for this task.

  **Action (operational, not a code change):**
  ```
  30 16 * * 1-5 python /path/to/scripts/healthcheck.py
  ```
  Run once manually first to confirm the Telegram alert fires correctly before adding to
  crontab. Requires operator access to the live cron host — this task cannot be completed from
  a sandbox session; flag for Animesh to run directly, or execute if this session has host
  cron access.

  **Verify:** manual run produces the expected exit code (0 on full pass, 1 + Telegram alert on
  any failure/warning) before the cron entry is added.

  **Commit (if a repo change accompanies it, e.g. a documented crontab snippet):**
  `chore(ops): document healthcheck cron entry`

---

- [x] **RO-5** — Add IVR NULL note to `BACKTEST_PLAN.md`. Spawned from TODOS.md. Phase 0.8 gate
  criterion A needs a documented exception: *"IVR NULL for Cycles 1 and 2 — accepted data gap;
  criterion A satisfied from Cycle 3 onward."* Cycle 1 (id=14, 2026-05-11): pipeline not live
  yet. Cycle 2 (id=32, 2026-05-28): 0/252 days VIX history blocked computation.

  **Fix:** targeted `Edit` to `BACKTEST_PLAN.md`'s Phase 0.8 gate criterion A section — add the
  note verbatim (or adapt if the gate's wording has since changed; re-read the current criterion
  A text first rather than assuming it matches the phrasing above).

  **No code-reviewer gate** — docs-only.

  **Commit:** `docs(backtest): note IVR NULL exception for Cycles 1-2 in Phase 0.8 gate criterion A`

---

- [ ] **RO-6** — Docs close: `TODOS.md` session log entry per task landed (RO-1 through RO-5,
  whichever subset ships). `CONTEXT.md` update only if RO-1/RO-2 change a described script
  behavior worth noting in the module tree. Run only after RO-1 through RO-5 (or whichever
  subset the team lands) are complete.
