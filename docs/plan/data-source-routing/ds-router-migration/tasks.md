# DS Router Migration — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: DSR-1, DSR-2, DSR-3..n (enumerated by DSR-1), DSR-last.** Blocked until `ds-chain-monitoring/` is complete and the Dec 2026 roll is done.

- [ ] **DSR-1** — Prior-art audit: every direct `UpstoxMarketClient` importer and `parse_upstox_option_chain` caller, grouped into migration clusters; write `audit.md` | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: none | SHA: <—>
- [ ] **DSR-2** — Quote and candle capability sources (Upstox, Dhan) + router and config | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: <—>
- [ ] **DSR-3** — Migrate cluster 1 (named by DSR-1); further clusters get their own DSR-n lines appended by DSR-1 | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: <—>
- [ ] **DSR-last** — Subscription-health fallback (806 / stale token) generalised across capabilities | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: <—>

## Story done when

- **DSR-1** — `audit.md` covers every site with file, capability used and disposition (migrate / exception); clusters sized to at most 3 files each.
- **DSR-2** — LTP and candle sources route by config; Upstox-only default behaves exactly as today.
- **DSR-3..n** — each cluster's tests pass with the router injected; no behaviour change under default config.
- **DSR-last** — an 806 on any capability degrades that capability to its next source and alerts once.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
