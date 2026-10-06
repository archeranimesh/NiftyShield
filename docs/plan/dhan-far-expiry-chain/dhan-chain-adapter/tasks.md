# Dhan Chain Adapter — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit.

**Open: DA-0..DA-3.**

- [ ] **DA-0** — Decide Dhan data-plan renewal before 2026-11-04 and record it in `findings.md` | Owner: Animesh | Model: n/a | Review: none | SHA: —
- [ ] **DA-1** — Record sanitised live fixtures (Dec 2026, Dec 2027) and check whether Upstox now returns Greeks for Dec 2026 | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **DA-2** — `DhanMarketClient.get_option_chain` + pure `parse_dhan_option_chain` + injectable 4 s rate limiter with 805 backoff and timeouts | Owner: Antigravity | Model: n/a | Review:
  greeks-analyst | SHA: —
- [ ] **DA-3** — Chain-source `Protocol` + composite that falls back to Dhan only on all-zero Upstox Greeks | Owner: Claude | Model: claude-sonnet-5-5 | Review: greeks-analyst | SHA: —

## Story done when

- **DA-0** — decision and date recorded.
- **DA-1** — fixtures committed with no credentials; the Upstox Dec 2026 result (Greeks present or zero, DTE) is written down.
- **DA-2** — fixture parse, 805 backoff and timeout tests green offline.
- **DA-3** — composite tests cover Upstox-ok, Upstox-all-zero, Dhan-fails.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
