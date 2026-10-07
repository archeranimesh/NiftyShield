# DS Chain Monitoring — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec; `schema.md` for the persisted columns.

**Open: DSN-1..DSN-5.** Blocked until `ds-chain-seam/` is complete and `yearly-overlays/yearly-foundation` YF-3 is done. DSN-1 may start earlier: it needs only the DSC-3 failure taxonomy.

- [ ] **DSN-1** — Dhan token-staleness alert (alert only, no renewal) + healthcheck line; 806 and stale token page via Telegram | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer |
  SHA: <—>
- [ ] **DSN-2** — Yearly monitor and snapshot paths read delta from the routed chain; persist `delta_source` / `delta_asof` per leg and `chain_source` / `chain_fetched_at` per overlay snapshot |
  Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer + greeks-analyst | SHA: <—>
- [ ] **DSN-3** — Stale-Greeks policy by action class, last-known delta from the capture store, +/-1 banned for yearly gates, delta-independent backstop alert | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: code-reviewer + greeks-analyst | SHA: <—>
- [ ] **DSN-4** — Monitor-cadence field in `OverlayTenorPolicy`; yearly cadence set (300 s or slower, final value here) and monthly pinned; freshness-bound startup validation | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: code-reviewer | SHA: <—>
- [ ] **DSN-5** — Source-flip seam: Dhan to Upstox after 2 consecutive trading days of non-zero delta on held contracts; dual-persist, tolerance band, dual-read logging | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: code-reviewer + greeks-analyst | SHA: <—>

## Story done when

- **DSN-1** — a stale token and an 806 each alert once and the healthcheck reports token age; no secrets in logs; the alert path is non-fatal.
- **DSN-2** — fixture test: a yearly leg's delta comes from Dhan when Upstox is all-zero; the row carries `delta_source` and `delta_asof`; monthly path and old rows unchanged.
- **DSN-3** — tests cover each fallback step and both age cutoffs; delta-dependent actions refuse and alert without live delta while delta-independent automation continues; no yearly gate reads the
  +/-1 approximation.
- **DSN-4** — a test pins every monthly cadence value; the yearly cadence keeps Dhan chain calls at least 4 s apart; inconsistent freshness config is rejected at startup.
- **DSN-5** — tests cover the 2-day trigger, the 0.05 / 25% suppression for that session only, the dual-persist, and same-source collar legs.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
