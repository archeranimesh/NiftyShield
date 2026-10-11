# PP protection cost study — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: PPS-1.**

- [ ] **PPS-1** — Save the 69 PP cycles from the finished PP run (free) and reproduce the Pareto numbers | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **PPS-2** — Hold-to-DTE-5 put templates at three depths, no crash exit: strike keyword, validate, pre-flight, create (free) | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **PPS-3** — Funded put runs (Animesh confirms each spend) and the per-depth cycle table | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **PPS-4** — CC 2x-exit variant: one funded run, rental net of losses and gap overshoot | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **PPS-5** — Selection rule, sizing note against Animesh's exposure and loss limit, findings, close | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —

## Story done when

- **PPS-1** — `pp_cycles.md` in this folder lists all 69 PP cycles (entry and exit date, NIFTY at each, strike, strike distance, premium and its percent of spot), and `findings.md` reproduces the 81%
  downside share, the -2.5% cutoff and the 0.57% per-cycle premium, or records why they differ.
- **PPS-2** — three put templates (about 2.5%, 3.4% and 5% OTM, or the stated delta fallback) exist on Tradetron with ids recorded, each validated with zero errors and pre-flighted with a recorded
  verdict; or a skip is recorded.
- **PPS-3** — at least one finished run per depth is logged (ids, window, settings, price paid) and a per-depth table shows annual premium, net annual cost after payoffs, realised deductible, share of
  cycles with hold-plus-put loss beyond 3% and 5%, and the worst cycle, with the cycle count beside each figure.
- **PPS-4** — one finished CC run with a 2x-price exit is logged, with realised net rental per year, loss count, and gap overshoot against the trigger, with the trip count beside each figure.
- **PPS-5** — `findings.md` states the selection rule (Animesh approves it), names the chosen depth with its cost, gives the lot formula and a table for ₹15 lakh at 10%, 15% and 25% falls, and records
  the exposure and loss limit Animesh gave; the story's status is updated everywhere it is summarised.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md` for a single story, the epic `README.md` story
list for an epic sub-story) and add one line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
