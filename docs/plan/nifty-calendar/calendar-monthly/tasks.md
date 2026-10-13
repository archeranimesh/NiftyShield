
# Calendar Monthly - shared core + monthly variant — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: CM-8..CM-9.**
- [x] **CM-0** — Prior-art audit and live-infra readiness probe; amend Design review if the code differs | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: e74f1ee
- [x] **CM-1** — `src/nifty_calendar/` models and payoff maths (Greeks aggregation, breakevens, risk-reward, loss at breakevens, Black-76 repricing of far legs via an interim local pricer) | Owner:
  Antigravity | Model: n/a | Review: code-reviewer, greeks-analyst | SHA: 401edd7
- [x] **CM-2** — `StructureSelector`: wing search under the six entry filters plus absolute spread gate | Owner: Antigravity | Model: n/a | Review: code-reviewer, greeks-analyst | SHA: 64a07aa
- [x] **CM-3** — `CalendarVariantConfig`, `CyclePolicy` and holiday-aware `CycleCalendar` (active variant for any date), monthly policy | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA:
  69cdff7
- [x] **CM-4** — `ExitRule` protocol and monthly rule (target, breach with time gate, hard day-10 close, DTE guard) valued at executable prices | Owner: Antigravity | Model: n/a | Review:
  code-reviewer | SHA: b3e548a
- [x] **CM-5** — `NiftyCalendarV1` shell on `PaperStrategy`: entry gates, fills, persistence, margin snapshot, re-centre via `ReEntryMixin` | Owner: Claude | Model: claude-sonnet-5-5 | Review:
  code-reviewer, greeks-analyst | SHA: 755f0fb
- [x] **CM-6** — Telegram entry, close and re-centre messages; two-expiry `EntryMessage`; payoff chart via an optional renderer `curve` arg, calendar adapter and registration | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: code-reviewer | SHA: fd903c4
- [x] **CM-7** — Entry script, EOD snapshot script, `monitor_daemon` registration, EOD summary pick-up | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: 9f47a68
- [ ] **CM-8** — Close-out: docs, module `CLAUDE.md`, graph re-index, parallel-run cutover note | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **CM-9** — Swap the interim pricer for `src/pricing` (blocked: `greeks-bs-fallback` GF-2/GF-3 not done) | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: —

## Story done when

- **CM-0** — findings recorded in `stories.md` under CM-0; every open question in this story's specs is answered or turned into an explicit decision.
- **CM-1** — metrics match a hand-computed fixture structure (the video's 22,700 straddle with 600/500 wings) within a stated tolerance; pure, no I/O.
- **CM-2** — selector returns a structure satisfying all six filters on a fixture chain, and returns an explicit "no entry" reason when none exists.
- **CM-3** — for every date in a fixture year the calendar returns exactly one active variant or none, across holidays and a Tuesday-expiry shift.
- **CM-4** — each exit path (target, recentre, close on breach late, day-10, DTE guard) is hit by a test and priority order is fixed.
- **CM-5** — the shell enters and closes a monthly cycle against fixtures, persisting trades, snapshots and margin, with no variant branch in its code.
- **CM-6** — entry, close and re-centre messages render in MarkdownV2 per `FORMATTING.md`; the payoff chart renders the calendar curve through IC's renderer with existing callers' output unchanged.
- **CM-7** — scripts run in dry mode against `MockBrokerClient`; the strategy appears in the EOD summaries; the daemon registers it.
- **CM-8** — docs per CLAUDE.md Step 5a done; cutover procedure written.
- **CM-9** — `src/nifty_calendar/pricing.py` is deleted and the calendar payoff and filters use `src/pricing`, with every earlier test passing unchanged.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md` for a single story, the epic `README.md` story
list for an epic sub-story) and add one line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
