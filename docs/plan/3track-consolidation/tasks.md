# 3-Track Consolidation & Automation — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line whose blockers are already checked.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/3track-consolidation/stories.md`.
> Decision log: `docs/plan/3track-consolidation/prompt.md`; `DECISIONS.md` 2026-07-28 entries.

---

- [ ] **S1** — Retire duplicate overlay legs on Futures and Proxy (data migration). **Blocked: requires explicit operator go-ahead before running** — mutates trade history already reported to the operator.
- [ ] **S2** — Restrict overlay entry to NiftyBees only. Depends on: S1.
- [ ] **S3** — Independent daily base-leg comparison snapshot (overlay fully excluded). Independent — can start anytime.
- [ ] **S4** — Full automation of `NiftyTrackComparisonV1` (`auto_execute=True`). Depends on: S1, S2.
- [ ] **S5** — Automated base-leg rolling for Futures and DITM tracks. Independent — can start anytime.
- [ ] **S6** — Full unattended automation: one-time bootstrap entry + trade-event Telegram notifications. Depends on: S2, S5. Best sequenced after S4 too.
- [ ] **S0** — Documentation and decision-log updates (retire RQ2, module tree, DECISIONS.md rows). Run last, after S1–S6. Docs-only, no code-reviewer gate.

---

- [ ] **CC1** — Per-strategy delta candidate ladder for `find_strike_by_delta.py` (CC gets its own, decoupled from CSP's). Can be built now as an experimentation/comparison tool, but **treat ladder values as provisional until `paper-exit-codification`'s EC-4 lands** (EC-4 owns the TIME_STOP DTE-remaining redesign; calibrating CC's entry delta against the current wrong TIME_STOP risks re-tuning twice).
- [ ] **CC2** — Decision gate (not an implementation task): CC entry delta band vs. current 4% OTM production default. Needs operator decision or council (`strategy_parameters` template). Scope narrowed — does NOT own TIME_STOP/DTE_REVIEW calibration, that's `paper-exit-codification` EC-4's. Gates CC1's ladder values from provisional → live, and gates CC3's `--no-dry-run`.
- [ ] **CC3** — Automated CC entry: idempotency guard on `paper_3track_overlay_entry.py` + Wednesday cron (mirrors `paper_ic_entry.py`'s pattern). Can be built/tested now in parallel with CC1/CC2, but **must ship `--dry-run`-only until CC1 + CC2 + `paper-exit-codification` EC-4 all resolve.**

---

## Notes

- S1–S6/S0 and CC1–CC3 are independent sub-threads of the same epic folder — CC's work
  doesn't block or get blocked by S1–S6's sequencing, it's tracked here because CC is the
  overlay this epic's S1/S2/S4 restrict and automate.
- See `stories.md`'s "Open risk not resolved by this epic" section (after S0) for the
  epic-wide flagged risk: full automation + single overlay copy removes the human check
  that previously existed via triplicated data.
