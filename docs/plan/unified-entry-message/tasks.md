# Unified entry message — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task.
Each task = one commit unless noted. See `prompt.md` for why the story exists;
see `stories.md` for the per-task implementation spec.

**Open: UEM-1, UEM-2, UEM-3.**

- [ ] **UEM-1** — Generalize `ic_entry_message.py` → `entry_message.py` (`EntryMessage` +
      `format_entry_message`, `headline_label` field, optional `ivr`/`mode`/`expiry_type`); migrate
      both IC call sites; rename the test file.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **UEM-2** — CSP lean entry card from `record_paper_trade.py` behind `--notify`, on a successful
      open only (no-op on close / roll), via `TelegramNotifier`, non-fatal on send failure.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **UEM-3** — Docs close: `CONTEXT.md` / `src/notifications/CLAUDE.md` / `DECISIONS.md` /
      `docs/plan/README.md` / `TODOS.md`; archive the folder.
      | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **UEM-1** — `src/notifications/entry_message.py` renders a 4-leg IC card byte-identical to the
  pre-refactor `format_ic_entry_message` for the same inputs; both IC entry scripts call
  `format_entry_message`; no `ic_entry_message` / `ICEntryMessage` / `format_ic_entry_message` reference
  remains in `src/` or `scripts/`; test file renamed; all unit tests green.
- **UEM-2** — `record_paper_trade.py --notify` sends a one-leg `✅ *CSP Entry*` card on a successful open
  and nothing on close / roll / when the flag is absent; send failure is logged and non-fatal; three
  tests green.
- **UEM-3** — All five docs reflect the new renderer and the CSP card; Feature Backlog line removed;
  folder archived to `docs/archive/plan/unified-entry-message/`.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box.
Then update this story's status in `docs/plan/README.md` (single story) and add one line to
`TODOS.md` Session Log.
When the whole story is done, follow §Conventions *Completion → archive* — do not leave a
done story half-archived.
