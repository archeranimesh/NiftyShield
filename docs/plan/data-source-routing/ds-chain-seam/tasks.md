# DS Chain Seam — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: DSC-1..DSC-4.** Blocked until `ds-capability-map/` DSM-3 is done.

- [ ] **DSC-1** — Canonical types (`ContractRef`, `ChainSnapshot`) + narrow capability `Protocol`s (quote, chain, candles, contract master; `MarketStream` protocol only) | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: code-reviewer | SHA: <—>
- [ ] **DSC-2** — Bidirectional contract resolver from the Upstox BOD and the Dhan instrument master | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: <—>
- [ ] **DSC-3** — Chain sources return `ChainSnapshot` with source tag; `CompositeChainSource` extended, not replaced | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer +
  greeks-analyst | SHA: <—>
- [ ] **DSC-4** — Chain routing config (capability → ordered sources) + `factory.py` wiring; Upstox-only config pinned by a regression test | Owner: Claude | Model: claude-sonnet-5-5 | Review:
  code-reviewer | SHA: <—>

## Story done when

- **DSC-1** — types and protocols importable; no concrete broker import in them; a test pins `ContractRef` equality and hashing.
- **DSC-2** — round-trip tests: canonical → native → canonical for both brokers from fixtures; an unlisted strike raises.
- **DSC-3** — tests cover Upstox-ok, Upstox-all-zero → Dhan, Dhan-fails, and the source tag on each path.
- **DSC-4** — config selects the chain order; default config behaves exactly as today.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
