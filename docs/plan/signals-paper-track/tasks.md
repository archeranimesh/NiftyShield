# Signals Paper Track — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task.
Each task = one commit unless noted. See `prompt.md` for why the story exists;
see `stories.md` for the per-task implementation spec.

**Open: SPT-1.**

> ⛔ SPT-1 is a council checkpoint. It writes no code. Its output is a `DECISIONS.md` entry
> and a rewrite of SPT-2..SPT-8 below (and `stories.md`) from the ruling. Do not touch
> SPT-2+ until that rewrite has landed — the IDs and specs below SPT-1 are provisional.

- [ ] **SPT-1** — Council checkpoint (no code): (a) module boundary — reuse `src/strategy/` +
  `src/paper/` (signals becomes a `PaperStrategy`) vs a self-contained monitor/exit loop in
  `src/signals/`; (b) trade rules still open — stop-loss / target *levels* (basis is fixed:
  % of entry premium), trailing-stop activation threshold + trail distance + coexist-with-target,
  the intraday fill model. **Pre-decided, not reopened:** monthly expiry / near-month / ≤ 7-DTE
  roll (uniform via `resolve_monthly_option`), fixed 1 lot, hard 15:00 square-off.
  Draft the question against the `strategy_parameters` template with a `data_architecture`
  section for (a). Output: `DECISIONS.md` entry + rewrite of SPT-2..SPT-8 / `stories.md`,
  including a task for the `resolve_monthly_option` ≤ 7-DTE roll before SPT-3.
  | Owner: Animesh | Model: n/a | Review: none | SHA: <—>
- [ ] **SPT-2** — *(provisional)* Paper-position model + `schema.md` + Store — persist entry,
  exit, state, realised P&L for the signals paper track. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SPT-3** — *(provisional)* Entry executor — `DailySignal` → resolved monthly option
  (`resolve_monthly_option`, ≤ 7-DTE roll) → simulated fill → position row + Telegram entry message. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SPT-4** — *(provisional)* Intraday monitor loop — poll position LTP on a cadence,
  evaluate exit rules, dedup. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SPT-5** — *(provisional)* Exit engine — stop-loss / target / trailing-stop / 15:00
  square-off; exit fill + row update + Telegram exit message with P&L. | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: <—>
- [ ] **SPT-6** — *(provisional)* Cron / entrypoint wiring + market-calendar guard +
  `SIGNAL_PHASE`. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SPT-7** — *(provisional)* 6-month evaluation report — paper-track realised P&L, win
  rate, go-live gate criteria. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SPT-8** — *(provisional)* Docs close — `CONTEXT.md`, `DECISIONS.md`, `TODOS.md`,
  `docs/plan/README.md`, module `CLAUDE.md`. | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>

## Story done when

- **SPT-1** — the council has ruled on the module boundary and the open trade-rule design; the
  ruling is in `DECISIONS.md`; SPT-2..SPT-8 and `stories.md` have been rewritten to match,
  including a task for the `resolve_monthly_option` ≤ 7-DTE roll.
- **SPT-2** — a signals paper-position row persists entry, exit, state and P&L; `schema.md` is
  the sole DDL source; happy-path + edge tests pass with no real DB.
- **SPT-3** — a `DailySignal` that fires produces one resolved-option paper entry at a
  simulated fill, one persisted row, and one Telegram entry message stating the fill price.
- **SPT-4** — the monitor polls an open position's mark on the agreed cadence during market
  hours and hands each tick to the exit engine without duplicate firing.
- **SPT-5** — an open position exits on the first of stop-loss / target / trailing-stop / the
  15:00 square-off, the row records the exit fill and realised P&L, and a Telegram exit
  message goes out with the entry→exit prices and P&L per lot.
- **SPT-6** — the entry and monitor entrypoints run under cron on trading days only, with the
  phase resolved from the environment.
- **SPT-7** — a report aggregates the paper track over a date window into realised P&L, win
  rate, and the documented go-live gate metrics.
- **SPT-8** — every state doc and module `CLAUDE.md` reflects the shipped execution layer.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box.
Then update this story's status in `docs/plan/README.md` (single story) and add one line to
`TODOS.md` Session Log.
When the whole story is done, follow `docs/plan/README.md` §Conventions *Completion → archive*.
