# DS Chain Seam — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: DSC-1..DSC-5.** Blocked until `ds-capability-map/` is complete (DSM-1 BOD coverage result decides whether the ledger-key design holds).

- [ ] **DSC-1** — `ContractRef`, `ChainSnapshot`, `ContractResolver` protocol in `src/models/contract.py` | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: <—>
- [ ] **DSC-2** — `ContractResolver` implementation from the Upstox BOD and the Dhan instrument master (exact joins, partial map legal) | Owner: Claude | Model: claude-sonnet-5-5 | Review:
  code-reviewer | SHA: <—>
- [ ] **DSC-3** — Chain sources return `ChainSnapshot`; per-expiry fallback with the 805 / 806 / empty / transport taxonomy; chain health keyed `(source, capability)` | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: code-reviewer + greeks-analyst | SHA: <—>
- [ ] **DSC-4** — Chain routing config via `Settings` + `factory.py` wiring; Upstox-only default pinned by a regression test | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA:
  <—>
- [ ] **DSC-5** — Cross-process Dhan throttle shared by the capture cron and the monitor daemon | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: <—>

## Story done when

- **DSC-1** — types importable with no concrete broker import; `ContractRef` equality and hashing pinned; a partial `instrument_keys` map is legal.
- **DSC-2** — round trip canonical to native to canonical for both brokers from fixtures; an unmapped strike returns `None`; a duplicate or ambiguous mapping raises.
- **DSC-3** — tests cover the Q5 offline list: monthly selects Upstox without a Dhan call; far-expiry all-zero falls through to Dhan without changing the next near-expiry call; 805 does not flip; 806
  and a stale token issue no Dhan call and alert; transport failure retries once.
- **DSC-4** — config selects chain order; default config behaves exactly as today.
- **DSC-5** — two limiter instances (simulating two processes) never issue Dhan chain calls closer than the floor.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
