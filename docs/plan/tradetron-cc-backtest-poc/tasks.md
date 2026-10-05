
# Tradetron CC backtest POC — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: TCP-6.**

- [x] **TCP-1** — Confirm the live CC thresholds and entry rule from `evaluate_cc()` and `cc_overlay_v1.py`, diff against the archived spec | Owner: Claude | Model: claude-sonnet-5-5 | Review: none |
  SHA: 475ffd6
- [x] **TCP-2** — Build the paper CC ground-truth table from the DB (read `DB_REGISTRY.md` first) and choose the backtest window | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA:
  94cf55c
- [x] **TCP-3** — Draft the CC template, validate it, run `tt_check_backtestability`, record a GO / PARTIAL / STOP verdict | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: 7112e6b
- [x] **TCP-4** — Create the template on Tradetron and record its id (skip if TCP-3 is STOP) | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: 7de8b32
- [x] **TCP-5** — Run the funded backtest (₹20 per run; Animesh tops up the wallet first, ₹100 minimum, ₹200 recommended) and log run ids | Owner: Animesh | Model: n/a | Review: none | SHA: 9142fc9
- [ ] **TCP-6** — Reconcile against paper trades, write the verdict, save learnings to the reference doc and `DECISIONS.md` if warranted, close the story | Owner: Claude | Model: claude-sonnet-5-5 |
  Review: none | SHA: <—>

## Story done when

- **TCP-1** — `findings.md` lists every CC threshold the template must encode, each with a code-sourced value and line, and MATCH or DIFFERS against the archived spec.
- **TCP-2** — `findings.md` has the paper CC table, the sample size and the chosen window (after 2026-04-01).
- **TCP-3** — `template.md` validates, the `tt_check_backtestability` verdict is recorded verbatim and a GO / PARTIAL / STOP decision is written.
- **TCP-4** — the template exists on Tradetron, reads back clean and its id is in `findings.md`; or the task is marked skipped with the STOP reason.
- **TCP-5** — at least one finished run is readable and logged with ids, window, settings and price paid.
- **TCP-6** — reconciliation and verdict are in `findings.md`, platform findings are in `docs/reference/tradetron.md`, and the story is closed or archived.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md` for a single story, the epic `README.md` story
list for an epic sub-story) and add one line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
