# docs/bugs/ — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md` session log.
> Full bug detail for each item: `docs/bugs/bugs.md`. ID numbering continues from root
> `BUGS.md` (`BUG-001`) — see `docs/bugs/prompt.md`.

---

## BUG-002 — Delta sign/magnitude corrupted by put-call misclassification

- [x] **B002.1** — Root-cause confirmed: `_position_delta` substring-matches `"PE"`/`"CE"` against numeric `instrument_key`, dead code, all options priced as full-delta futures | Confirmed 2026-07-02 (no code change, investigation only)
- [ ] **B002.2** — Decision needed from Animesh: should `aggregate_delta` in `paper_ic_entry.py` stay cross-strategy (pool `paper_nifty_futures` / `paper_nifty_proxy` / `paper_nifty_spot` into the same gate as the IC book), or scope to IC-relevant positions only? Blocks B002.3.
- [ ] **B002.3** — Add option-type signal to position data: either extend `PaperPosition` with `option_type` populated from `InstrumentLookup` at trade-record time, or join `legs.asset_type`/`legs.direction` in `PaperStore.get_position`. Depends on B002.2 scope decision.
- [ ] **B002.4** — Replace `net_qty / lot_size` full-delta approximation in `_position_delta` with actual option delta from chain snapshot where available (short 1-lot put ≠ short 1-lot future)
- [ ] **B002.5** — Tests: happy-path (short put → positive delta, correct magnitude), edge case (unrecognised/legacy `instrument_key` still falls back safely with a warning, does not silently misclassify)
- [ ] **B002.6** — Run real `@code-reviewer` subagent against `git diff HEAD` (financial-logic gate, mandatory per root `CLAUDE.md`) — resolve CRITICAL/ERROR before commit
- [ ] **B002.7** — Commit, update `bugs.md` status to ✅ Fixed + SHA, update `CONTEXT.md` if `PaperPosition` schema changed

---

## BUG-003 — `_post_expiry_gate` inverted monthly window

- [x] **B003.1** — Root-cause confirmed: gate checks `_last_tuesday_of_month(today.year, today.month)` (the cycle being entered) instead of the prior settled cycle | Confirmed 2026-07-02 (no code change, investigation only)
- [ ] **B003.2** — Fix: reference previous month's `_last_tuesday_of_month` (last settled expiry) instead of current month's; block only same-day/next-day re-entry immediately after that settlement, not the whole new cycle
- [ ] **B003.3** — Verify fix doesn't disturb the Tuesday-expiry logic documented in `REFERENCES.md` (SEBI change, April 2026) — same `_last_tuesday_of_month` helper is shared
- [ ] **B003.4** — Check whether `paper_ic_entry_v2.py` already solved this correctly (`TODOS.md` 2026-06-28 IC-V2-13 fix log says its own gate switched to BOD expiry date, `_last_tuesday_of_month` removed there) — if so, port that approach into the shared `ic_entry_gates.py::_post_expiry_gate` instead of re-deriving a fix from scratch
- [ ] **B003.5** — Tests: happy-path (first trading day after prior settlement → entry allowed), edge case (same day as prior settlement → still blocked), edge case (year rollover, e.g. Dec → Jan)
- [ ] **B003.6** — Run real `@code-reviewer` subagent against `git diff HEAD` before commit
- [ ] **B003.7** — Commit, update `bugs.md` status to ✅ Fixed + SHA
