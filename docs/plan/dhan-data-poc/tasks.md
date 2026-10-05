
# Dhan data API POC — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: DDP-3 to DDP-6.**

- [x] **DDP-1** — Free docs read: Dhan data API and historical dataset shape, price, pass or fail against the POC criteria | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: 0abb226
- [x] **DDP-2** — Animesh buys the one-month POC; record plan, price and access method (no secrets) | Owner: Animesh | Model: n/a | Review: none | SHA: 2cc680d
- [ ] **DDP-3** — Coverage inventory on the real dataset against the strikes each strategy trades | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: <—>
- [ ] **DDP-4** — Old-data validation: Dhan against stored Upstox chain, bhavcopy and paper trades | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: <—>
- [ ] **DDP-5** — Contract questions: Dec 2026 and Jun 2027 Greeks, yearly-bucket relabelling, zero-window delta | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: <—>
- [ ] **DDP-6** — Verdict on the full-year purchase, hand-offs to the Tradetron story, close and archive | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: <—>

## Story done when

- **DDP-1** — `findings.md` records what the docs say about fields, strike and expiry coverage, history depth, candle size and price, with a pass or fail per POC criterion.
- **DDP-2** — `findings.md` records the plan, price and access method Animesh states; no credentials.
- **DDP-3** — `findings.md` has a coverage table per strategy (covered, partly covered, missing) with the date range, expiries and strike range found, and the fields present.
- **DDP-4** — `findings.md` has validation tables against the stored Upstox chain, bhavcopy and paper trades with sample sizes beside each figure, or a recorded coverage gap.
- **DDP-5** — `findings.md` states what Dhan shows for Dec 2026 and Jun 2027, when Upstox's Greeks start, and the one decision for `greeks-bs-fallback`, flagged and not edited.
- **DDP-6** — the full-year question is answered in `findings.md`, `DECISIONS.md` carries any decision, and the story is archived.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md` for a single story, the epic `README.md` story
list for an epic sub-story) and add one line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
