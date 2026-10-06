# Far-Expiry Liquidity Gate — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit.

**Open: FG-1..FG-3. Blocked until the capture has enough days.**

- [ ] **FG-1** — Calibration findings: read the liquidity report over the captured window and propose spread cap, OI floor and quote rule per expiry type | Owner: Claude | Model: claude-sonnet-5-5 |
  Review: none | SHA: —
- [ ] **FG-2** — Extend `_apply_liquidity_gate` with OI floor, two-sided-quote rule and an ordered fallback ladder (next strike, next expiry); defaults keep existing callers unchanged | Owner:
  Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **FG-3** — Roll-window decision: from the capture, the DTE at which the next December's target strikes first pass the gate; set yearly `roll_dte` in the policy registry | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: roll-validator | SHA: —

## Story done when

- **FG-1** — `findings.md` holds the thresholds, the window used and the supporting numbers; Animesh signs off.
- **FG-2** — pass, each failure reason and each ladder step tested; old call sites' tests unchanged.
- **FG-3** — `roll_dte` set from evidence; recorded in `DECISIONS.md`.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
