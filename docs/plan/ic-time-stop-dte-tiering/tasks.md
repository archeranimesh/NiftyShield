# IC Time-Stop DTE Tiering — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/ic-time-stop-dte-tiering/stories.md`.
> Origin: `docs/council/2026-08-05_ic-time-stop-dte-tiering.md` (Stage 3 ruling).
>
> **Owner column** follows `CLAUDE.md` Step 3b: Claude takes single/2-file tasks with real
> judgment calls or unresolved ambiguity requiring mid-task graph queries; Antigravity takes
> 3+-file mechanical tasks with a fully pinned-down spec and a TDD-style edit/test loop.

---

- [x] **DT-1** `[Claude]` — Update `ic_expiry_config.py` CONFIGS: `time_stop_dte=7`/`dte_warn=14` for monthly/leaps/yearly (weekly unchanged) + test run | SHA: 184667c
- [x] **DT-2** `[Claude]` — Docs: `DECISIONS.md` entry + `IC-M1.md` correction note (docs only, no code-reviewer gate) | SHA: f59104d
- [x] **DT-3a** `[Claude]` — Audit: confirm the actual write path for IC `paper_exit_events` rows (`create_exit_event` has no confirmed IC-side caller yet — see stories.md). Ambiguous, exploratory, must resolve before DT-3b can be handed off. Finding: no writer exists at all — DT-3b must add new call sites in `IronCondorV1.check_signals` and `IronCondorV2.check_signals`. Also surfaced: `paper_ic_snapshot.py`'s "Intraday actions" query has always been dead for IC. | SHA: adb1589
- [ ] **DT-3b** `[Antigravity]` — Counterfactual DTE logging: `paper_exit_events.counterfactual_dte_marks` column + wiring at the call site DT-3a confirms + tests. Do not start until DT-3a's findings are written into `stories.md` — the spec as written is provisional.
- [ ] **DT-4** `[Claude]` — Docs close: `CONTEXT.md`, `TODOS.md`, `docs/plan/README.md` status row, schedule the 6-monthly-cycle review reminder
