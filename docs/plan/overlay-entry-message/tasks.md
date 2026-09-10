# Overlay entry message — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task.
Each task = one commit unless noted. See `prompt.md` for why the story exists;
see `stories.md` for the per-task implementation spec.

Depends on `unified-entry-message/` (UEM-1..3) — `src/notifications/entry_message.py` must
already exist. Do not start OEM-1 before UEM-3 has landed and archived.

**Open: OEM-1, OEM-2, OEM-3, OEM-4, OEM-5.**

- [ ] **OEM-1** — Sign-aware net line in `entry_message.py::_credit_line`: negative
      `net_credit` → `💰 *Net debit:* …` (absolute value, label flipped); positive / zero
      byte-identical. Two new tests.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **OEM-2** — `CollarOverlayV1._reenter_collar` sends a `✅ *Collar Entry*` card (2 legs,
      `[B]` put + `[S]` call) on a successful two-leg record, via `self._notifier`, non-fatal.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer + greeks-analyst | SHA: —
- [ ] **OEM-3** — `CCOverlayV1` (`✅ *CC Entry*`, 1 `[S]` leg) and `PPOverlayV1`
      (`✅ *PP Entry*`, 1 `[B]` leg) send the same card on a successful automated re-entry.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer + greeks-analyst | SHA: —
- [ ] **OEM-4** — Migrate the `📥 Overlay Entry — {TYPE} Bootstrap` message in
      `paper_3track_overlay_entry.py` to `format_entry_message`; the `⚠️ Gate Logged` line
      stays appended by the caller after the rendered card.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **OEM-5** — Docs close: `CONTEXT.md` / `src/notifications/CLAUDE.md` / `DECISIONS.md` /
      `docs/plan/README.md` / `TODOS.md`; archive the folder.
      | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **OEM-1** — `format_entry_message` renders `💰 *Net debit:*` for a negative `net_credit`
  and is byte-identical to the pre-OEM-1 output for a positive / zero one; all unit tests
  green.
- **OEM-2** — a successful Collar re-entry sends one `✅ *Collar Entry*` card (`[B]` put +
  `[S]` call, `💰 *Net debit:*` line); a send failure is logged and never crashes the tick;
  two tests green; `greeks-analyst` clean.
- **OEM-3** — a successful CC re-entry sends `✅ *CC Entry*` (`Net credit`) and a successful
  PP re-entry sends `✅ *PP Entry*` (`Net debit`); send failure non-fatal; tests green;
  `greeks-analyst` clean.
- **OEM-4** — the bootstrap message is `format_entry_message`'s output for cc / pp / collar,
  with the unchanged `⚠️ Gate Logged` line appended when a gate fired; no hand-rolled
  `📥 Overlay Entry` f-string remains; tests green.
- **OEM-5** — all five docs reflect the shared overlay renderer and the sign-aware net line;
  Feature Backlog line removed; folder archived to
  `docs/archive/plan/overlay-entry-message/`.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box.
Then update this story's status in `docs/plan/README.md` and add one line to `TODOS.md`
Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do
not leave a done story half-archived.
