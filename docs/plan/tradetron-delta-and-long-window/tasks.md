
# Tradetron delta check and long-window validation — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: TDL-10.**
- [x] **TDL-1** — Free own-data delta check: read the stored Upstox delta for the six strikes Tradetron chose in run 2 | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: b20ec40
- [x] **TDL-2** — Live Offline Greeks probe, Tradetron versus Upstox at one timestamp, near-dated and far-dated; reference table for `greeks-bs-fallback` | Owner: Claude | Model: claude-sonnet-5-5 |
  Review: none | SHA: 39938a3
- [ ] **TDL-3** — Long-window pre-flight on CC template v2 (free): data coverage, Greeks, the April 2026 expiry boundary; pick the window | Owner: Claude | Model: claude-sonnet-5-5 | Review: none |
  SHA: —
- [ ] **TDL-4** — Own-side comparator audit (read-only) and the go or no-go on funded runs with a budget Animesh approves | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **TDL-5** — CC long-window funded run on template v2; cycles, exit mix, regime split, sample size | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **TDL-6** — PP and Collar: live rules from code and the paper ground-truth table from the DB | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **TDL-7** — PP and Collar templates: validate, pre-flight, create | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **TDL-8** — PP and Collar funded runs and reconciliation | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **TDL-9** — IC v1 and v2 buildability audit (free); GO, PARTIAL or STOP; no template unless GO | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **TDL-10** — Verdict on the data-purchase question, save learnings, close and archive the story | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —

## Story done when

- **TDL-1** — `findings.md` has a table of the six run-2 strikes with the Upstox delta found at the nearest timestamp, the timestamp gap, and a verdict on the direction and size of any offset; or a
  recorded coverage gap.
- **TDL-2** — `findings.md` has Tradetron and Upstox delta and IV side by side at one timestamp for near-dated and far-dated contracts, including whether Tradetron is nonzero where Upstox is zero,
  flagged for `greeks-bs-fallback`.
- **TDL-3** — `findings.md` records the pre-flight verdict verbatim, the data coverage found, whether Greeks and both expiry regimes resolve, and the chosen window.
- **TDL-4** — `findings.md` lists what own-side backtest data and comparator exist, a go or no-go on funded runs, and a budget Animesh has approved.
- **TDL-5** — at least one finished long-window CC run is logged with ids, window, settings and price paid, with cycle count, exit mix by price ratio, pre and post April 2026 split and round-trip
  count.
- **TDL-6** — `findings.md` lists every PP and Collar threshold the templates must encode with a code-sourced value and line, and a paper ground-truth table with sample sizes.
- **TDL-7** — each PP and Collar template validates, has a recorded `tt_check_backtestability` verdict and GO, PARTIAL or STOP, and exists on Tradetron with its id recorded; or the skip is recorded.
- **TDL-8** — at least one finished run per built template is logged and reconciled against paper over the overlapping window, with sample size next to each figure.
- **TDL-9** — `findings.md` lists which IC v1 and v2 rules Tradetron can and cannot express, with a GO, PARTIAL or STOP verdict; no IC run unless GO and Animesh approves it as a follow-up story.
- **TDL-10** — the purchase question is answered in `findings.md`, platform findings are in `docs/reference/tradetron.md`, `DECISIONS.md` carries any decision, and the story is archived.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md` for a single story, the epic `README.md` story
list for an epic sub-story) and add one line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
