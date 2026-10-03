# Chart Core — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: PC-3.**

- [x] **PC-1** — Scaffold the `strategy-payoff-charts/` epic + both sub-stories; register in `TODOS.md` + README | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 7210c31
- [x] **PC-2** — `src/payoff/` leaf package: `core.py` (`PayoffLeg`, `StrategyPayoff`, `compute_payoff`), `errors.py` (`PayoffError` hierarchy), import-boundary test, `Decimal` | Owner: Claude |
  Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: bd6e6a1
- [ ] **PC-3** — `src/payoff/core.py`: `expiry_pnl_at` + `expiry_pnl_series` for any `StrategyPayoff` | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **PC-4** — Acceptance matrix `tests/unit/strategy/test_payoff_acceptance.py`: IC, CSP, CC, Collar hand-computed fixtures | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **PC-5** — `src/notifications/payoff_chart.py`: `render_payoff_png` generic chart body via the matplotlib `Figure` API (no `pyplot`); add matplotlib dep | Owner: Antigravity | Model: n/a |
  Review: code-reviewer | SHA: —
- [ ] **PC-6** — `payoff_chart.py`: stat strip (Max P/L or "Unlimited", R:R, Net Credit/Debit, Breakevens + %, Margin when given) | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **PC-7** — `TelegramNotifier.send_photo` — multipart `sendPhoto`, non-fatal, honours the budget | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **PC-8** — `TelegramGateway.send_photo` delegating (+ `protocol.py` only if a typed caller needs it) | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **PC-9** — Message-budget fix: payoff photos must not starve the EOD text budget | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **PC-10** — `src/payoff/registry.py`: `PayoffRegistry` (injectable), split adapter Protocols (`PayoffAdapter`, `HasTitle`), `register_payoff`, `DefaultPositionAdapter` with injected strike
  resolver | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: — code-reviewer | SHA: —
- [ ] **PC-11** — `send_payoff_chart(sender: PhotoSender, ...)` — non-raising entry point: registry lookup → compute → render off-loop (`to_thread`) → `send_photo` | Owner: Antigravity | Model: n/a |
  Review: code-reviewer | SHA: — code-reviewer | SHA: —
- [ ] **PC-12** — Hook audit (read-only): find the central open / EOD / close hook point; record the decision in `stories.md` | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **PC-13** — `src/strategy/payoff_registrations.py`: explicit idempotent `ensure_registered()` registering `iron_condor_v1` / `iron_condor_v2` | Owner: Claude | Model: claude-sonnet-5 | Review:
  greeks-analyst | SHA: —
- [ ] **PC-14** — Wire entry V1 (`paper_ic_entry.py`): `send_payoff_chart` after the `ICEntryMessage` text send | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **PC-15** — Wire entry V2 (`paper_ic_entry_v2.py`): same | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **PC-16** — Wire EOD snapshot (`paper_ic_snapshot.py` `process_variant`): one PNG per open variant | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: —
- [ ] **PC-17** — Wire close V1 (`ic_nifty_v1.py` `_send_close_notification`): PNG after the text send | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: —
- [ ] **PC-18** — Wire close V2 (`ic_nifty_v2.py` `_send_close_notification` mirror) | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: —
- [ ] **PC-19** — Docs close: `CONTEXT.md` + `DECISIONS.md` + `TODOS.md` + README + epic README + "register a strategy" recipe in `src/strategy/CLAUDE.md`; re-index graph | Owner: Claude | Model:
  claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **PC-1** — the epic folder exists with a valid epic root + two conforming sub-stories; `check_story_structure.py` clean; registered in `TODOS.md` and `docs/plan/README.md`.
- **PC-2** — `src/payoff/` exists as a leaf package (an AST test proves it imports nothing from `src.strategy` / `src.notifications`); `compute_payoff` returns correct max profit / max loss /
  breakevens (any number, ordered) / R:R for a bounded structure, and flags an unbounded profit or loss side instead of inventing a number; a happy-path and an edge-case (no legs, zero net premium,
  single naked leg) test.
- **PC-3** — `expiry_pnl_at` exact at kinks, on the plateaus and on the tails; ≈ 0 at a breakeven; `expiry_pnl_series` returns matched-length spot / pnl arrays.
- **PC-4** — the four acceptance structures (Iron Condor, Cash-Secured Put, Covered Call, Collar) each match hand-computed max profit / max loss / breakevens; the CSP and CC cases exercise the
  bounded-by-zero-spot tail and the Collar a mixed EQ + CE + PE leg set.
- **PC-5** — `render_payoff_png` (matplotlib `Figure` API, no `pyplot` global state) returns non-empty PNG bytes (magic `\x89PNG`) under Agg with no display for a bounded and an unbounded structure;
  payoff line, fills, breakeven + short-strike verticals, spot line, P&L dot drawn; `matplotlib` in `requirements.txt`.
- **PC-6** — the stat strip shows Max Profit, Max Loss (or "Unlimited"), R:R, Net Credit/Debit, and Breakevens with % from spot; Est. Margin appears only when a margin value is passed.
- **PC-7** — `TelegramNotifier.send_photo` POSTs a multipart `sendPhoto` (`chat_id`, `photo`, optional `caption`); a non-200 is logged and does not raise; it respects the per-session budget.
- **PC-8** — `TelegramGateway.send_photo` delegates and is non-fatal; the `NotificationGateway` protocol carries `send_photo` iff a type-checked caller needs it.
- **PC-9** — an EOD snapshot run sending ~8 text + ~8 photos delivers all of them (photos do not consume the text budget), with a test.
- **PC-10** — registering an adapter by name makes `get(name)` return it from an injected `PayoffRegistry`; an unregistered name returns `None`; a duplicate registration raises
  `DuplicateRegistrationError`; `HasTitle` is a separate Protocol an adapter may or may not implement; the default adapter (with an injected strike resolver) builds `PayoffLeg`s from a fixture
  position set and raises `InvalidLegsError` rather than charting a partially resolved set.
- **PC-11** — `send_payoff_chart` for a registered strategy builds legs, renders off the event loop, calls `sender.send_photo`, and never raises; an unregistered name logs a warning and sends nothing;
  compute / render / send failures and timeouts are logged and swallowed; the correlation context reaches the render worker (tested).
- **PC-12** — a short findings note in `stories.md` PC-12 naming the central hook (or stating none exists and the wiring stays per-site), which fixes the shape of PC-14..18.
- **PC-13** — `ensure_registered()` is explicit and idempotent, registers `iron_condor_v1` / `iron_condor_v2`, and is the only registration site (no import-time side effect); a test over the strategy
  names the wired sites pass proves each resolves; the IC legs reproduce the entry strikes + credit.
- **PC-14 / PC-15** — a dry-run of each entry script against a fixture chain produces a PNG and attempts the send, right after the existing text send.
- **PC-16** — `paper_ic_snapshot.py --dry-run` with ≥ 1 seeded open position sends one PNG per open variant, after that variant's text report; no open position → no photo.
- **PC-17 / PC-18** — a simulated CLOSE_FULL for V1 and V2 sends the close text then a payoff PNG; `_notifier is None` or an empty close still sends nothing.
- **PC-19** — `CONTEXT.md`, `DECISIONS.md`, `TODOS.md`, and `docs/plan/README.md` reflect the shipped state; `src/strategy/CLAUDE.md` carries the "register a new strategy for payoff charts" recipe;
  the graph is re-indexed.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` **Stories** table and add one line to `TODOS.md` Session Log. Follow
`docs/plan/README.md` §Conventions *Completion → archive* only once **both** sub-stories are complete — the epic folder moves as a unit.
