# Signal outcome profit range — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: SOP-1, SOP-2, SOP-3.**

- [ ] **SOP-1** — `SignalOutcome` fields + `signal_outcomes` migration | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SOP-2** — Compute high/low from `paper_signal_marks` in `run_record_phase` | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SOP-3** — Render high/low in the Telegram outcome message | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>

## Story done when

- **SOP-1** — `SignalOutcome` carries `high_pnl_per_lot` / `low_pnl_per_lot`; `signal_outcomes` has both columns via an idempotent migration; round-trip through `record_outcome`/`get_outcome`
  preserves both as `Decimal`.
- **SOP-2** — An executed trade's outcome has both fields populated from its own `paper_signal_marks` history's final `mfe_pct`/`mae_pct`; not-executed and no-marks cases leave both `None` without
  raising.
- **SOP-3** — The Telegram SIGNAL OUTCOME message shows a "📈 High / 📉 Low" line for executed trades with both values set, and is unchanged (no blank-line artifact) when either is `None`.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md` for a single story) and add one line to `TODOS.md`
Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
