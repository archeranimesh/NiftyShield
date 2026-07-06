# Full-Repo-Review Follow-ups — Epic Index

Spawned from `docs/plan/full-repo-review/findings/FR-7_synthesis.md` (Chairman Synthesis) by
FR-9. Each folder below is a self-contained story — start from its `prompt.md`. All 7 CRITICAL
findings that fed these stories were independently re-derived against the live repo (not
re-read) before the folder was created; see `DECISIONS.md` 2026-07-06 for the verification
method and the two severity divergences (D1, D2) that were preserved rather than collapsed.

Do not start a P2 story before its P0/P1 blockers close where a dependency is noted below —
everything else in a tier can run in any order or in parallel.

---

## Priority order

| Tier | Folder | Source (FR-7 row) | Why this tier |
|---|---|---|---|
| **P0 — real capital, fix now** | `portfolio-pnl-critical-fix/` | row 1 (CRITICAL) | Live P&L is wrong today — ₹52,318.50 confirmed invisible, open short P&L wrong sign/magnitude. |
| **P0 — real capital, fix now** | `sqlite-backup-cron/` | row 2 (CRITICAL) | Zero backup for the single store of record; one bad write away from unrecoverable loss. |
| **P1 — actively misdirecting sessions** | `docs-navigation-and-staleness/` | rows 3, 8, 14 (CRITICAL + ERROR) | Stale status table + dead links (incl. the *source of record* for live exit thresholds) send agents to the wrong place today. |
| **P1 — live security gap** | `telegram-approval-auth-fix/` | row 9 (ERROR) | OR-vs-AND callback bug lets any group-chat member approve real trades; small fix, real exposure. |
| **P2 — protocol correctness, blocks clean new-code writes** | `protocol-standards-reconciliation/` | rows 4, 5, 11 (CRITICAL + ERROR) | Compliant agents currently get blocked by a compliant reviewer either way (broad-catch / assert / AutoTrigger contradictions). |
| **P2 — mechanical, unblocks Antigravity handoff** | `logging-migration-completion/` | row 7 (CRITICAL) | 21 bare loggers + 24 script entrypoints; good Antigravity candidate once P0/P1 land. |
| **P3 — needs a council consult before code** | `greeks-parity-validation/` | row 6 (CRITICAL, contested — D1) | Do not implement directly: gated on an `options-strategist`/`greeks-analyst` tolerance-band decision first. |
| **P3 — test hardening** | `paper-pnl-golden-tests/` | row 13 (ERROR) | Mitigated one layer up already (`test_tracker.py`); real but not urgent. |
| **P3 — docs triage** | `suppression-hygiene-triage/` | row 10 (ERROR, downgraded from FR-4's CRITICAL — D2) | Policy carve-out, not a code fix; no live consequence identified. |

## Dependencies worth noting

- `greeks-parity-validation/` should ideally follow `portfolio-pnl-critical-fix/` — the same
  reconciliation exercise that surfaced row 1 is the evidence base for why row 6 stays CRITICAL
  (FR-7's D1 divergence). Not a hard blocker, but do the P0 first if sequencing.
- `protocol-standards-reconciliation/` touches the same `CLAUDE.md` region already edited by
  FR-9 itself (AI Collaboration section, Step 5a). Diff against current `CLAUDE.md` before
  editing, not against the version FR-1 originally reviewed.

---

## Conventions

Same as `docs/plan/README.md` — each folder has `prompt.md` (session entry point),
`tasks.md` (first-unchecked-box protocol), `stories.md` (implementation spec).
