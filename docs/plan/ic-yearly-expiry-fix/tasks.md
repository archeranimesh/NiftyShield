# IC Yearly Expiry Correction — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/ic-yearly-expiry-fix/stories.md`.

---

- [ ] **YE-1** — Audit all 6 non-test callers of the `"yearly"` expiry label; produce impact table (read-only, no code)
- [ ] **YE-2** — Fix `get_expiry_candidates()`: `"yearly"` resolves to nearest December last-Tuesday expiry only, no DTE band gate at this layer
- [ ] **YE-3** — Fix/confirm callers per YE-1 findings; add regression tests proving no silent behavior change
- [ ] **YE-4** — Docs close: TODOS.md session log, DECISIONS.md entry, CONTEXT.md update if docstring changed — no code

---

> Separate concern, added 2026-07-08 — unrelated to YE-1..YE-4 (June/December yearly-label bug).
> Do not bundle into the same session/commit as the YE tasks above. Full spec:
> `docs/plan/ic-yearly-expiry-fix/stories.md` — "Separate concern — weekly-expiry Greeks snapshot gap".

- [ ] **WG-1** — Persist per-leg Greeks for the weekly expiry bucket (option-chain snapshot pipeline currently archives monthly/quarterly/yearly only, not weekly — root cause of an unresolvable DELTA_WARN discrepancy on 2026-07-08)
