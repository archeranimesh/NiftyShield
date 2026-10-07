# DS Chain Monitoring — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: DSN-1..DSN-4.** Blocked until `ds-chain-seam/` is complete and `yearly-overlays/yearly-foundation` YF-3 is done. DSN-1 may start earlier if DSM-1 shows renewal is possible and the capture cron
needs it.

- [ ] **DSN-1** — Dhan token freshness: renewal if DSM-1 allows it, otherwise a stale-token alert; healthcheck reads it | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: <—>
- [ ] **DSN-2** — Yearly monitor and snapshot paths read delta from the routed chain; persist `source` per snapshot | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer + greeks-analyst
  | SHA: <—>
- [ ] **DSN-3** — Stale-Greeks fallback order and source-flip policy, as the council rules | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer + greeks-analyst | SHA: <—>
- [ ] **DSN-4** — Monitor-cadence field in `OverlayTenorPolicy`; yearly cadence set and monthly pinned | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: <—>

## Story done when

- **DSN-1** — a stale token and a lapsed plan (806) each produce an alert; the healthcheck reports token age; no secrets in logs.
- **DSN-2** — fixture-driven test: yearly leg delta comes from Dhan when Upstox is all-zero; the persisted row carries `source`; monthly path unchanged.
- **DSN-3** — tests cover each fallback step and the max-age cutoff; the source flip around Upstox Greeks returning is logged and tolerance-banded as ruled.
- **DSN-4** — a test pins every monthly cadence value; the yearly cadence keeps Dhan calls at least 4 s apart.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
