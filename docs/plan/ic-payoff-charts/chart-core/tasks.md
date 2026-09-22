# Chart Core — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: PC-2.**

- [x] **PC-1** — Scaffold the `ic-payoff-charts/` epic + both sub-stories; register in `TODOS.md` + README | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 7210c31
- [ ] **PC-2** — `src/strategy/payoff.py`: `ICPayoff` + `compute_ic_payoff` (max P/L, breakevens, R:R), `Decimal` | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **PC-3** — `src/strategy/payoff.py`: `expiry_pnl_at` + `expiry_pnl_series` for the plot line | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **PC-4** — `src/notifications/payoff_chart.py`: `render_expiry_payoff_png` chart body; add matplotlib dep | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **PC-5** — `payoff_chart.py`: stat strip (Max P/L, R:R, Net Credit, Breakevens + %, Margin when given) | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **PC-6** — `TelegramNotifier.send_photo` — multipart `sendPhoto`, non-fatal, honours the budget | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **PC-7** — `TelegramGateway.send_photo` delegating (+ `protocol.py` only if a typed caller needs it) | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **PC-8** — Message-budget fix: payoff photos must not starve the EOD text budget | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **PC-9** — `build_and_send_ic_payoff(...)` — the single non-raising wiring entry point for the 3 call sites | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **PC-10** — Wire entry V1 (`paper_ic_entry.py`): call the helper after the `ICEntryMessage` text send | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **PC-11** — Wire entry V2 (`paper_ic_entry_v2.py`): same | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **PC-12** — Wire EOD snapshot (`paper_ic_snapshot.py` `process_variant`): one PNG per open variant | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: —
- [ ] **PC-13** — Wire close V1 (`ic_nifty_v1.py` `_send_close_notification`): PNG after the text send | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: —
- [ ] **PC-14** — Wire close V2 (`ic_nifty_v2.py` `_send_close_notification` mirror) | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: —
- [ ] **PC-15** — Docs close: `CONTEXT.md` + `DECISIONS.md` + `TODOS.md` + README + epic README; re-index graph | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **PC-1** — the epic folder exists with a valid epic root + two conforming sub-stories; `check_story_structure.py` clean; registered in `TODOS.md` and `docs/plan/README.md`.
- **PC-2** — `compute_ic_payoff` returns correct max profit / max loss / lower + upper breakeven / R:R for a known IC, with a happy-path and an edge-case (credit ≥ wing, credit ≤ 0) test.
- **PC-3** — `expiry_pnl_at` exact at the profit plateau, past each breakeven, ≈ 0 at a breakeven; `expiry_pnl_series` returns matched-length spot / pnl arrays.
- **PC-4** — `render_expiry_payoff_png` returns non-empty PNG bytes (magic `\x89PNG`) under Agg with no display; trapezoid, fills, verticals, spot line, P&L dot drawn; `matplotlib` in
  `requirements.txt`.
- **PC-5** — the stat strip shows Max Profit, Max Loss, R:R, Net Credit, and Breakevens with % from spot; Est. Margin appears only when a margin value is passed.
- **PC-6** — `TelegramNotifier.send_photo` POSTs a multipart `sendPhoto` (`chat_id`, `photo`, optional `caption`); a non-200 is logged and does not raise; it respects the per-session budget.
- **PC-7** — `TelegramGateway.send_photo` delegates and is non-fatal; the `NotificationGateway` protocol carries `send_photo` iff a type-checked caller needs it.
- **PC-8** — an EOD snapshot run sending ~8 text + ~8 photos delivers all of them (photos do not consume the text budget), with a test.
- **PC-9** — `build_and_send_ic_payoff` builds the `ICPayoff`, renders the PNG, calls `gateway.send_photo`, and never raises; a test covers the happy path and a render/send failure.
- **PC-10 / PC-11** — a dry-run of each entry script against a fixture chain produces a PNG and attempts the send, right after the existing text send.
- **PC-12** — `paper_ic_snapshot.py --dry-run` with ≥ 1 seeded open position sends one PNG per open variant, after that variant's text report; no open position → no photo.
- **PC-13 / PC-14** — a simulated CLOSE_FULL for V1 and V2 sends the close text then a payoff PNG; `_notifier is None` or an empty close still sends nothing.
- **PC-15** — `CONTEXT.md`, `DECISIONS.md`, `TODOS.md`, and `docs/plan/README.md` reflect the shipped state; the graph is re-indexed.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` **Stories** table and add one line to `TODOS.md` Session Log. Follow
`docs/plan/README.md` §Conventions *Completion → archive* only once **both** sub-stories are complete — the epic folder moves as a unit.
