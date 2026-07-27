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
- [ ] **CL-1** — Design the `long_niftybees` collateral-leg model/record shape. Check whether
  this fits the existing `PaperPosition`/`PaperTrade` model as a new `leg_role` on the CSP
  strategy, or needs a new field — `get_code_snippet("PaperPosition")` and
  `get_code_snippet("PaperTrade")` first. Confirm quantity formula
  `qty = floor((65 × nifty_spot) / niftybees_ltp)` against current lot size (verify 65 is still
  the live NIFTY lot size — `DateAwareLotSizeResolver` — before hardcoding it anywhere; lot size
  has changed before, see BUG-015 in `DECISIONS.md`).
- [ ] **CL-2** — Back-fill Cycle 1 (entry 2026-05-11) — determine the historical NiftyBees LTP
  and Nifty spot at that date, compute quantity via the formula, record via
  `record_paper_trade.py` (data-only, no `.py` change, mirrors the BUG-017 backfill pattern in
  `DECISIONS.md`/`TODOS_ARCHIVE.md`).
- [ ] **CL-3** — Add `long_niftybees` to `paper_snapshot.py`'s LTP batch fetch so the collateral
  leg's value is tracked in daily snapshots alongside the CSP short put.
- [ ] **CL-4** — Implement the annual reset — check whether this needs a cron/script or a
  documented manual procedure; confirm with the operator which before implementing (annual
  reset semantics for a collateral leg tied to a formula that depends on live spot/LTP need a
  clear "reset to what, and when" definition — do not assume interpretation).
- [ ] **CL-5** — Docs close: `TODOS.md` session log, `CONTEXT.md` module tree entry if a new
  field/model was added in CL-1, `DECISIONS.md` entry for the annual-reset design decision (CL-4).
