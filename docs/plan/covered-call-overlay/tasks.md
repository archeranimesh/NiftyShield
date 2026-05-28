# Covered Call Overlay — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md` session log.
> Full story spec for each task: `docs/plan/covered-call-overlay/stories.md`.
> Strategy parameters (delta target, IVR gate, exit triggers, qty formula): `docs/strategies/covered_call_overlay_v1.md`.

---

- [ ] **CC1** — `src/paper/constants.py`: add `STRATEGY_CC_OVERLAY` constant + `compute_max_lots` pure function + tests
- [ ] **CC2** — `scripts/paper_cc_entry.py`: delta-based CE selection + IVR gate + qty constraint + dry-run command output
- [ ] **CC3** — `scripts/paper_cc_roll.py`: three-trigger exit handler (profit target / time stop / delta stop)
- [ ] **CC4** — Docs close: CONTEXT.md tree, DECISIONS.md entry, TODOS.md session log
