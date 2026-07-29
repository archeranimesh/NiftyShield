# 3-Track Consolidation & Automation — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line whose blockers are already checked.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/3track-consolidation/stories.md`.
> Decision log: `docs/plan/3track-consolidation/prompt.md`; `DECISIONS.md` 2026-07-28 and
> 2026-07-29 (round 5, overlay/track independence) entries.

---

- [x] ~~**S1** — Retire duplicate overlay legs on Futures and Proxy (data migration).~~ **Superseded 2026-07-29 by S1r** — destination changed (re-home to `paper_nifty_overlay`, not leave under `paper_nifty_spot`). Do not implement as originally written; see S1r below.
- [x] ~~**S2** — Restrict overlay entry to NiftyBees only.~~ **Deleted 2026-07-29, see S2r** — operator decision: overlay is track-independent, this story's premise is reversed. Do not implement.
- [x] **S1r** — Re-home overlay legs to independent `strategy_name` (`paper_nifty_overlay`), supersedes S1's destination while reusing its close/LTP-fallback logic. Operator go-ahead given 2026-07-29. Council checkpoint waived by operator override 2026-07-29, see `DECISIONS.md` round 5 entry. | SHA: 8c41cca
- [ ] **S2r** — Remove track-ownership overlay blocks: today's live `_check_futures_cc_block` plus (not-yet-implemented) original S2. Depends on: none, but land alongside/after S1r so overlay entry isn't unblocked before it has a track-independent home to land in.
- [ ] **S3** — Independent daily base-leg comparison snapshot (overlay fully excluded). Independent — can start anytime. Design unaffected by the 2026-07-29 revision.
- [ ] **S3r** — Query-time overlay coverage/P&L per track (Spot/Futures/Proxy), new story, not in original scope. Effective-Nifty-exposure calc (ETF ≈1x, Futures via margin/SPAN, DITM via live delta) — no qty/lot resizing. Depends on: S1r (overlay must be re-homed before a track-agnostic query makes sense).
- [ ] **S4** — Full automation of `NiftyTrackComparisonV1` (`auto_execute=True`). Depends on: S1r, S2r (was S1, S2).
- [ ] **S5** — Automated base-leg rolling for Futures and DITM tracks. Independent — can start anytime.
- [ ] **S6** — Full unattended automation: one-time bootstrap entry + trade-event Telegram notifications. Depends on: S2r, S5 (was S2, S5). Best sequenced after S4 too.
- [ ] **S0** — Documentation and decision-log updates (retire RQ2, module tree, DECISIONS.md rows; also document S1r/S2r/S3r's overlay-independence model). Run last, after S1r/S2r/S3/S3r/S4–S6. Docs-only, no code-reviewer gate.
- [ ] **S7** — **Confirmed bug (2026-07-28), not a missing feature:** daily CC/PP/Collar leg snapshots are already being written by `_save_leg_snapshots()` every cron run, but under the wrong `leg_role` — `generate_track_snapshot()` normalizes overlay legs to display labels (`"cc"`/`"collar"`/`"pp"`) before returning, and `_save_leg_snapshots()` persists directly against those collapsed labels instead of the real `overlay_cc`/`overlay_pp`/`overlay_collar_call`/`overlay_collar_put` leg_roles. Result: `overlay_ltp` is always `None` on these rows (the `get_position()` lookup never matches), and nothing that queries `paper_leg_snapshots` by real leg_role can find this history. Not caught by the existing test (`test_save_leg_snapshots_with_overlay` bypasses `generate_track_snapshot()`'s normalization by constructing its fixture with the real leg_role directly). Independent of S1–S6/CC/PP/Collar automation stories — pure persistence-layer bug fix, can ship anytime.
- [ ] **S8** — Dedicated daily P&L comparison table for CC/PP/Collar overlays (`paper_overlay_pnl_snapshots`), mirroring S3's design (`pnl_1d_abs/pct`, `pnl_inception_abs/pct`) but per overlay instead of per base track. Collar's call+put merge into one row, matching existing display convention. **Depends on: S7** (this table's aggregation reads the leg_role-corrected `paper_leg_snapshots` rows S7 produces — building it before S7 lands would inherit the same broken-key/null-ltp bug).
- [ ] **S9** — NiftyBees protection-recovery comparison table (`paper_protection_recovery_snapshots`) + one compact daily Telegram digest showing NiftyBees P&L against CC/PP/Collar recovery, recovery-pct only shown on loss days. **Depends on: S3, S8** (reads their output tables only, no independent leg computation). Open question flagged in `stories.md`: confirm with operator whether this is three live parallel overlay series or three what-if reconstructions against the single live overlay copy, before writing the aggregation query.

---

- [ ] **CC1** — Per-strategy delta candidate ladder for `find_strike_by_delta.py` (CC gets its own, decoupled from CSP's). Can be built now as an experimentation/comparison tool, but **treat ladder values as provisional until `paper-exit-codification`'s EC-4 lands** (EC-4 owns the TIME_STOP DTE-remaining redesign; calibrating CC's entry delta against the current wrong TIME_STOP risks re-tuning twice).
- [ ] **CC2** — Decision gate (not an implementation task): CC entry delta band vs. current 4% OTM production default. Needs operator decision or council (`strategy_parameters` template). Scope narrowed — does NOT own TIME_STOP/DTE_REVIEW calibration, that's `paper-exit-codification` EC-4's. Gates CC1's ladder values from provisional → live, and gates CC3's `--no-dry-run`.
- [ ] **CC3** — Automated CC entry: idempotency guard on `paper_3track_overlay_entry.py` + Wednesday cron (mirrors `paper_ic_entry.py`'s pattern). Can be built/tested now in parallel with CC1/CC2, but **must ship `--dry-run`-only until CC1 + CC2 + `paper-exit-codification` EC-4 all resolve.**

---

- [ ] **PP1** — Per-strategy delta candidate ladder for PP (`PP_DELTA_CANDIDATES` in `find_strike_by_delta.py`, PE-long, gated by explicit `--overlay-type pp` flag so it never gets inferred from bare `--option-type PE`). Corrects a stale CONTEXT.md claim in passing — `PPOverlayV1` already inherits `ReEntryMixin`, confirmed via code read 2026-07-28. **PE/CSP ladder-collision concern deferred** (2026-07-28, operator) — PP evaluated independently of CSP for now, re-open before both are ever automated/live simultaneously.
- [ ] **PP1a** — Fix confirmed live bug: `find_strike_by_delta.py --strategy paper_protective_put_v1` defaults `--action` to `SELL` (records a naked short put under a strategy name that implies protection). Add `_resolve_action()` helper — auto-resolves `BUY` for PP, hard-errors on explicit `--action SELL` for PP. Independent of PP1's ladder scope; can ship first/standalone.
- [ ] **PP2** — Decision gate (not an implementation task): PP entry delta band vs. current fixed %OTM default. Needs operator decision or council (`strategy_parameters` template). Different tradeoff axis than CC2 (protection cost vs. responsiveness, not premium vs. assignment risk) — do not reuse CC2's answer by analogy. Gates PP1's ladder values from provisional → live, and gates PP3's `--no-dry-run`.
- [ ] **PP3** — Two bundled fixes: (1) investigate + resolve whether `ROLL_PP` should trigger `_check_reentry` in `PPOverlayV1.apply_action()` (currently only `MONETIZE_PP` does — may be correct as-is if ROLL_PP keeps the position open, unlike CC's gap; **do not assume it mirrors CC3 without checking `evaluate_pp`'s ROLL_PP semantics first**); (2) automated PP entry — idempotency guard on `paper_3track_overlay_entry.py` + cron. Cadence is an open question, not a Wednesday-cron copy — PP is drawdown protection, not an expiry-cycle premium collection. Fix (1) can ship independently of PP1/PP2; automated entry (2) depends on PP1 + PP2 same as CC3 depends on CC1 + CC2.

---

- [ ] **Collar1** — Two-leg strike selection for Collar: coordinates CC1's `CC_DELTA_CANDIDATES` (short call) and PP1's `PP_DELTA_CANDIDATES` (long put) via a new `--overlay-type collar` mode in `find_strike_by_delta.py`, adds net-combo-premium reporting. **Hard dependency: cannot start until both CC1 and PP1 ship** — unlike CC1/PP1 this story has no independent ladder to invent, it only coordinates theirs. Does not auto-select a single combo; prints the candidate cross-product for operator/Collar2 judgment.
- [ ] **Collar2** — Decision gate (not an implementation task): Collar entry method — fixed %OTM (both legs) vs. coordinated delta-targeted (Collar1). Needs operator decision or council (`strategy_parameters` template). Two-dimensional tradeoff axis (net cost *and* payoff shape move together) — distinct from both CC2 (premium vs. assignment risk) and PP2 (cost vs. responsiveness); do not reuse either by analogy. Gates Collar1's ladder/net-premium values from provisional → live, and gates Collar3's `--no-dry-run`.
- [ ] **Collar3** — Two bundled fixes: (1) confirmed re-entry gap — `CollarOverlayV1.apply_action()` only calls `_check_reentry` for `PROFIT_TARGET`/`TIME_STOP`, same gap class CC3 fixes; widen to also cover `LOSS_STOP`, `DELTA_STOP`, `BELOW_FLOOR` (confirm `DELTA_WARN`, a WARN not ACTION severity, correctly stays excluded before assuming); (2) automated Collar entry — new idempotency guard on `paper_3track_overlay_entry.py` (existing `_query_open_call_roles`/`_validate_collar_pairs` checks are same-instrument/shape guards, not a "collar pair already open" bootstrap check) + cron (cadence open question, same caveat as PP3 — don't copy CC3's Wednesday cadence verbatim, collar has both a premium-collection leg and a protection leg). Fix (1) can ship independently first; automated entry (2) depends on Collar1 + Collar2 same as CC3→CC1/CC2 and PP3→PP1/PP2.

---

## Notes

- S1–S6/S0, CC1–CC3, PP1–PP3, and Collar1–Collar3 are independent sub-threads of the same epic
  folder — none blocks or gets blocked by the others' sequencing; CC, PP, and Collar are tracked
  here because they're the overlays this epic's S1/S2/S4 restrict and automate.
- PP1–PP3 mirror CC1–CC3's shape (delta ladder → decision gate → automated entry) but are
  **not** a mechanical copy — PP is long options (protection) vs. CC's short options (premium
  collection), so the ladder ranking logic, the decision-gate tradeoff, the re-entry trigger
  gap, and the entry cadence all need their own investigation rather than find-and-replace.
  See `stories.md` PP1/PP3 for the specific places this session flagged as "don't assume,
  verify" before writing code.
- Collar1–Collar3 depend on **both** CC1–CC2 and PP1–PP2 landing first — Collar has no
  independent ladder of its own, it coordinates CC's short-call ladder and PP's long-put ladder
  into one two-leg combo. Collar3's re-entry-gap fix is independent and can ship first, same
  pattern as PP3's Gap-1/Gap-2 split. See `stories.md` Collar1/Collar3 for the two-leg-specific
  reasoning (net combo premium, atomic close already correct and not to be re-fixed).
- See `stories.md`'s "Open risk not resolved by this epic" section (after PP3) for the
  epic-wide flagged risk: full automation + single overlay copy removes the human check
  that previously existed via triplicated data.
