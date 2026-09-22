# Full-Repo-Review Follow-ups — Epic Index

Spawned from `docs/plan/full-repo-review/findings/FR-7_synthesis.md` (Chairman Synthesis) by FR-9. Each folder below is a self-contained story — start from its `prompt.md`. All 7 CRITICAL findings
that fed these stories were independently re-derived against the live repo (not re-read) before the folder was created; see `DECISIONS.md` 2026-07-06 for the verification method and the two severity
divergences (D1, D2) that were preserved rather than collapsed.

Do not start a P2 story before its P0/P1 blockers close where a dependency is noted below — everything else in a tier can run in any order or in parallel.

---

## Priority order

Surface/model routing follows FR-8's Step 3b criteria (file count is a weak signal; mechanical-vs-judgment is the real test), not a default-to-Antigravity assumption. Full reasoning for each is in the
story's own `prompt.md` under "Surface & Model" — this table is the lookup, not the justification.

| Tier | Folder | Source (FR-7 row) | Why this tier | Surface | Model |
|---|---|---|---|---|---|
| **P0 — real capital, fix now** | `portfolio-pnl-critical-fix/` | row 1 (CRITICAL) | Live P&L wrong today | Claude Code | Opus + mandatory real `@code-reviewer` |
| **P0 — real capital, fix now** | `sqlite-backup-cron/` | row 2 (CRITICAL) | No backup of the store of record | Antigravity | N/A / Sonnet for review |
| **P1 — actively misdirecting sessions** | `docs-navigation-and-staleness/` | rows 3, 8, 14 (CRITICAL + ERROR) | Stale status table + dead links | Antigravity | N/A / Sonnet for review |
| **P1 — live security gap** | `telegram-approval-auth-fix/` | row 9 (ERROR) | Any group-chat member can approve trades | Claude Code | Sonnet, escalate Opus if guard semantics unclear |
| **P2 — protocol correctness** | `protocol-standards-reconciliation/` | rows 4, 5, 11 (CRITICAL + ERROR) | Reviewer blocks compliant code | Claude Code | Opus (edits the protocol docs) |
| **P2 — mechanical, unblocks Antigravity handoff** | `logging-migration-completion/` | row 7 (CRITICAL) | 21 bare loggers + 24 script entrypoints | Antigravity | N/A / Sonnet for review |
| **P3 — needs a council consult before code** | `greeks-parity-validation/` | row 6 (CRITICAL, contested — D1) | Contested — quant decision needed first | Claude Code only | Opus for the consult |
| **P3 — test hardening** | `paper-pnl-golden-tests/` | row 13 (ERROR) | Already mitigated one layer up | Claude Code | Sonnet (needs a graph query mid-implementation) |
| **P3 — docs triage** | `suppression-hygiene-triage/` | row 10 (ERROR, downgraded from FR-4's CRITICAL — D2) | Policy carve-out, not a code fix | Claude Code | Sonnet (policy-wording judgment call) |

### Why each tier (expanded)

- `portfolio-pnl-critical-fix/` — Live P&L is wrong today: ₹52,318.50 confirmed invisible, open short P&L wrong sign/magnitude.
- `sqlite-backup-cron/` — Zero backup for the single store of record; one bad write away from unrecoverable loss.
- `docs-navigation-and-staleness/` — Stale status table + dead links (incl. the *source of record* for live exit thresholds) send agents to the wrong place today.
- `telegram-approval-auth-fix/` — OR-vs-AND callback bug lets any group-chat member approve real trades; small fix, real exposure.
- `protocol-standards-reconciliation/` — Compliant agents currently get blocked by a compliant reviewer either way (broad-catch / assert / AutoTrigger contradictions).
- `logging-migration-completion/` — 21 bare loggers + 24 script entrypoints; good Antigravity candidate once P0/P1 land.
- `greeks-parity-validation/` — Do not implement directly: gated on an `options-strategist`/`greeks-analyst` tolerance-band decision first.
- `paper-pnl-golden-tests/` — Mitigated one layer up already (`test_tracker.py`); real but not urgent.
- `suppression-hygiene-triage/` — Policy carve-out, not a code fix; no live consequence identified.

**4 of 9 are Antigravity handoffs** (`sqlite-backup-cron`, `docs-navigation-and-staleness`, `logging-migration-completion`, plus none others — greeks/telegram/suppression/golden-tests/portfolio-pnl
all require live judgment, a council consult, or a mid-implementation graph query that a cold Antigravity spawn can't do). For every Antigravity row, Claude still runs the Phase Completion Output
verification (SHA match, test count) per Step 3b before closing the phase — Antigravity does not self-certify.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `portfolio-pnl-critical-fix/` | Fix live P&L wrong sign/magnitude on open short legs | ⬜ Not started | — | — |
| `sqlite-backup-cron/` | Add scheduled backup of `portfolio.sqlite` | ⬜ Not started | — | — |
| `docs-navigation-and-staleness/` | Fix stale status table + dead links in nav docs | ⬜ Not started | — | — |
| `telegram-approval-auth-fix/` | Fix OR-vs-AND callback bug in trade-approval auth | ⬜ Not started | — | — |
| `protocol-standards-reconciliation/` | Resolve reviewer/protocol contradictions | ⬜ Not started | — | — |
| `logging-migration-completion/` | Migrate 21 bare loggers + 24 script entrypoints | ⬜ Not started | — | — |
| `greeks-parity-validation/` | Resolve contested Greeks tolerance-band decision, then implement | ⬜ Not started | council/strategist consult first | — |
| `paper-pnl-golden-tests/` | Add golden tests for paper P&L (already mitigated one layer up) | ⬜ Not started | — | — |
| `suppression-hygiene-triage/` | Triage suppression-hygiene policy carve-out | ⬜ Not started | — | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`. Story order matches the Priority order table
above, which the router (`prompt.md`) walks.

## Cross-cutting constraints

- Surface/model routing follows FR-8's Step 3b criteria per story — see each story's own `prompt.md` under "Surface & Model" for the reasoning; the Priority order table above is the lookup, not the
  justification.
- `greeks-parity-validation/` should ideally follow `portfolio-pnl-critical-fix/` even though there is no hard blocker recorded — the same reconciliation exercise that surfaced row 1 is the evidence
  base for row 6's contested CRITICAL severity (FR-7's D1 divergence).
- `protocol-standards-reconciliation/` touches the same `CLAUDE.md` region already edited by FR-9 itself (AI Collaboration section, Step 5a) — diff against current `CLAUDE.md` before editing, not
  against the version FR-1 originally reviewed.
- All 7 CRITICAL findings that fed these stories were independently re-derived against the live repo before the folder was created — do not re-derive again; see `DECISIONS.md` 2026-07-06 for the
  verification method and the two severity divergences (D1, D2) preserved rather than collapsed.

## Epic done when

Every sub-story's `tasks.md` is fully checked with a real closing SHA on its last task, and this README's Stories table status column reflects ✅ Done for all nine rows. `greeks-parity-validation/` is
not done until its gating consult is recorded in `DECISIONS.md` and the resulting implementation task(s) are also closed.

## Dependencies worth noting

- `greeks-parity-validation/` should ideally follow `portfolio-pnl-critical-fix/` — the same reconciliation exercise that surfaced row 1 is the evidence base for why row 6 stays CRITICAL (FR-7's D1
  divergence). Not a hard blocker, but do the P0 first if sequencing.
- `protocol-standards-reconciliation/` touches the same `CLAUDE.md` region already edited by FR-9 itself (AI Collaboration section, Step 5a). Diff against current `CLAUDE.md` before editing, not
  against the version FR-1 originally reviewed.

---

## Conventions

Same as `docs/plan/README.md` — each folder has `prompt.md` (session entry point), `tasks.md` (first-unchecked-box protocol), `stories.md` (implementation spec).
