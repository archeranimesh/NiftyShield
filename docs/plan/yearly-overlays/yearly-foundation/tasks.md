# Yearly Foundation — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: YF-1..YF-5.**

- [ ] **YF-1** — Audit every overlay site that hardcodes STRATEGY_OVERLAY, "monthly", `date.today()` or a monthly DTE gate; write `audit.md` | Owner: Claude | Model: claude-sonnet-5-5 | Review: none |
  SHA: —
- [ ] **YF-2** — Test fixtures: BOD with Dec 2026 + Dec 2027, zero-Greeks and populated chain fixtures, frozen-clock helper | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **YF-3** — `OverlayTenorPolicy` registry (monthly pinned to today's values, yearly added) + `STRATEGY_OVERLAY_YEARLY` constant | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **YF-4** — Pure `resolve_overlay_expiry(lookup, today, policy)`; inject `today` + policy into the three bootstraps (default monthly) | Owner: Claude | Model: claude-sonnet-5-5 | Review:
  code-reviewer | SHA: —
- [ ] **YF-5** — Namespace read-paths (reentry_mixin, collateral_gate, auto_close, overlay_coverage, eod_pt_summary, track_snapshot) recognise the yearly namespace | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: greeks-analyst | SHA: —

## Story done when

- **YF-1** — `audit.md` lists every site with file:line, current behaviour and required change; no `schema` need unaddressed.
- **YF-2** — fixtures load offline; the frozen-clock helper is used by at least one test.
- **YF-3** — a test pins every monthly value; yearly entry present; constant exported.
- **YF-4** — frozen-date tests give Dec 2026 and Dec 2027; monthly callers unchanged.
- **YF-5** — each audited consumer has a yearly-namespace test; monthly tests unchanged.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md` for a single story, the epic `README.md` story
list for an epic sub-story) and add one line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
