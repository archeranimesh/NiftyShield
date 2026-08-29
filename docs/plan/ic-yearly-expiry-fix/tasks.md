# IC Yearly Expiry Correction — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/ic-yearly-expiry-fix/stories.md`.

---

- [x] **YE-1..YE-4 — SUPERSEDED, not executed as written.** A separate 2026-07-22 Cowork session
      (user-reported, not from this story's own trigger) independently diagnosed and fixed the
      same root cause via a different path — no formal blast-radius audit was run against the 8
      callers listed in YE-1 below, but the shipped fix matches YE-2's spec almost exactly
      (December-only, no DTE band, nearest-live rollover with no artificial floor after a
      same-day self-correction). See `DECISIONS.md` BUG-015 (both the initial fix and its
      follow-up correction) for the full account, and `TODOS.md` 2026-07-22 entries. Commit
      `7495fb0` + a same-day follow-up commit (not yet landed at time of writing — sandbox
      `.git/index.lock` permission issue, same class as prior sessions).
      **Residual risk:** the YE-1 caller audit was never actually performed — the 8 call sites
      listed below were not individually re-verified against the new December-only semantics.
      Worth a follow-up pass if any of the non-IC-V1 callers (chain snapshot pipelines,
      3-track overlay) show unexpected far-dated-contract selection.
- [ ] **WG-1** below remains open and unaffected by this.

---

> Separate concern, added 2026-07-08 — unrelated to YE-1..YE-4 (June/December yearly-label bug).
> Do not bundle into the same session/commit as the YE tasks above. Full spec:
> `docs/plan/ic-yearly-expiry-fix/stories.md` — "Separate concern — weekly-expiry Greeks snapshot gap".

- [ ] **WG-1** — Persist per-leg Greeks for the weekly expiry bucket
  (option-chain snapshot pipeline currently archives monthly/quarterly/yearly only, not weekly — root cause of an unresolvable DELTA_WARN discrepancy on 2026-07-08)
