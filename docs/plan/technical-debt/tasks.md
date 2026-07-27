# Technical Debt — Tasks

**These are not a sequence.** Unlike every other story in `docs/plan/`, do not pick these up on
their own — each is fixed **only** when you are already touching the same file or module for an
unrelated reason. Never a standalone commit. See `prompt.md` for the exact trigger condition per
item.

- [ ] **DEBT-3** — License boilerplate: decision needed before automation. Every file gets a
  header once a license is chosen. Blocked on a decision, not on code — see `stories.md`.
- [ ] **DEBT-5** — `test_bhavcopy_ingest.py` missing append-path coverage. Trigger: next time
  `test_bhavcopy_ingest.py` or `write_to_parquet`'s merge branch is touched for another reason.
- [ ] **DEBT-6a** — Move hardcoded expiry whitelist (`{2026-04-07, 2026-12-29}`) from `Leg` to
  `market_calendar` YAML. Trigger: next time `Leg` construction or `market_calendar` is touched.
- [ ] **DEBT-6b** — Holiday YAML datasets for 2017–2025 missing in `src/market_calendar/data/` —
  historical `Leg` construction pre-2026 fails open. Trigger: next time historical/backtest `Leg`
  construction is touched (this one is also a real prerequisite for
  `docs/plan/backtest-engine/phase1/` tasks that construct pre-2026 `Leg`s — flag it if hit there).
- [ ] **DEBT-6c** — Formalise `is_nifty` check: replace denylist with an `instrument_key`-based
  predicate. Trigger: next time the `is_nifty` denylist is touched.
- [ ] **DEBT-7** — Refactor dynamic dispatch in `daily_snapshot.py` to eliminate `noqa: F401`
  unused-import suppressions (they hide broken imports if helpers are renamed/moved). Trigger:
  next time `daily_snapshot.py`'s dynamic-dispatch block is touched.
