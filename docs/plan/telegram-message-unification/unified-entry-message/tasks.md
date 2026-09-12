# Unified entry message — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: UEM-2, UEM-3.**

- [x] **UEM-1** — Generalize `ic_entry_message.py` → `entry_message.py` (`EntryMessage` +
      `format_entry_message`, `headline_label` field, optional `ivr`/`mode`/`expiry_type`); migrate
      both IC call sites; rename the test file.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 08fd78c
- [ ] **UEM-2** — CSP / CC lean entry card from `record_paper_trade.py` behind `--notify` (headline
      chosen from `--strategy`), on a successful open only (no-op on close / roll), via
      `TelegramNotifier`, non-fatal on send failure.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **UEM-3** — Sub-story docs close: `CONTEXT.md` / `src/notifications/CLAUDE.md` / `DECISIONS.md` /
      the epic `README.md` Stories table / `TODOS.md` Session Log. No folder archive — the epic
      archives as a whole at UXM-8.
      | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **UEM-1** — `src/notifications/entry_message.py` renders a 4-leg IC card byte-identical to the pre-refactor `format_ic_entry_message` for the same inputs; both IC entry scripts call
  `format_entry_message`; no `ic_entry_message` / `ICEntryMessage` / `format_ic_entry_message` reference remains in `src/` or `scripts/`; test file renamed; all unit tests green.
- **UEM-2** — `record_paper_trade.py --notify` sends a one-leg `✅ *CSP Entry*` or `✅ *CC Entry*` card (chosen by `--strategy`) on a successful open and nothing on close / roll / when the flag is
  absent; send failure is logged and non-fatal; four tests green.
- **UEM-3** — `CONTEXT.md`, `src/notifications/CLAUDE.md`, `DECISIONS.md` reflect the new renderer and the CSP / CC card; the epic `README.md` Stories-table row is ✅ with the closing SHA; `TODOS.md`
  Session Log line added. The epic folder is **not** archived here.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then flip this sub-story's row in the epic `README.md` **Stories** table (`docs/plan/telegram-message-unification/README.md`) and
add one line to `TODOS.md` Session Log. The epic folder is archived only when every sub-story is done — see the epic `prompt.md` Step 4 and `docs/plan/README.md` §Conventions *Completion → archive*.
