# CSP Collateral Leg (`long_niftybees`) — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line, top to bottom. That is your only task
> for this session. Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.

**Origin:** TODOS.md — `long_niftybees` collateral leg for CSP. **DoD per the original item:
story dir + back-fill command documented.** This creation pass satisfies that DoD; implementation
tasks below are scoped for future sessions.

**Formula (from the original item):** `qty = floor((65 × nifty_spot) / niftybees_ltp)`.

---

- [x] **CL-0** — Create this story directory (`prompt.md` + `tasks.md`), scope the
  implementation into tasks below. No code. Docs-only.
- [x] **CL-1 (rescoped, 2026-08-06)** — **No new model needed.** Investigation found the
  `long_niftybees` holding already exists and is fully tracked: `STRATEGY_SPOT =
  "paper_nifty_spot"` (`src/paper/constants.py`) is the 3-track base-leg `PaperPosition` for
  `NIFTYBEES_KEY`, already carrying real `paper_trades` rows, already valued nightly (confirmed
  live via the EOD Telegram summary's `paper_nifty_spot` unrealized P&L line). Creating a second
  `PaperPosition`/`leg_role` under `paper_csp_nifty_v1` for the same physical shares would
  double-count one real holding across two strategy ledgers. Original quantity formula
  `qty = floor((65 × nifty_spot) / niftybees_ltp)` is not a new-position sizing formula — it's
  the same relationship `compute_max_lots()` (`src/paper/constants.py`, already shipped for the
  CC overlay, `covered-call-overlay` CC1) already computes, just solved for lots instead of
  units. CSP reuses `compute_max_lots()` directly against the existing `paper_nifty_spot`
  position rather than building anything new.
- [x] **CL-2 (struck, 2026-08-06)** — No backfill needed. There is no new position to backfill;
  the real entry already exists under `paper_nifty_spot`.
- [x] **CL-3 (struck, 2026-08-06)** — No snapshot wiring needed. `paper_nifty_spot`'s LTP is
  already in the nightly batch fetch — confirmed by its live unrealized P&L appearing in the EOD
  Telegram summary (`+₹52,016.45` on 2026-08-05).
- [x] **CL-4 (resolved by reuse, 2026-08-06)** — No cron/script/manual-procedure needed.
  `compute_max_lots()`'s existing docstring already specifies the "annual reset" semantics:
  recompute at read-time against the current `nifty_spot`/`niftybees_ltp` each cycle — not a
  stored value, not a position mutation, no scheduled job. Verified live against real data
  (`niftybees_units=5735` from `paper_trades`, `niftybees_ltp=280.07` from `paper_leg_snapshots`
  2026-08-05, `nifty_spot=24635.70` live 2026-08-06) →
  `compute_max_lots(5735, Decimal("24635.70"), Decimal("280.07"), 65) == 1` lot. The "reset" is
  simply re-running this call at each cycle checkpoint with fresh inputs — same pattern CC
  already uses, no new mechanism.
- [x] **CL-5** — Docs close: `TODOS.md` session log entry, `DECISIONS.md` entry recording the
  no-new-model decision and the CL-4 reuse ruling. No `CONTEXT.md` change — no new field/model
  was added.
