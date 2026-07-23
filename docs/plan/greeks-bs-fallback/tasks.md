# Greeks BS Fallback — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/greeks-bs-fallback/stories.md`.

---

- [ ] **GF-1** — Audit scope (read-only, no code): confirm which expiry buckets actually hit
      all-zero Greeks (yearly confirmed 2026-07-22; check quarterly/monthly/weekly too — a
      quarterly repro was requested but not yet run to completion this session), pick a
      known-good live chain to use as GF-5's validation ground truth, and surface the three open
      decisions listed in `prompt.md` (risk-free rate source, DTE convention, delta tolerance)
      for the story owner to decide before GF-2 starts.
- [ ] **GF-2** — Black-Scholes European option pricer + delta formula, new module
      `src/pricing/black_scholes.py`. Pure functions (call_price/put_price/call_delta/put_delta),
      cite the reference formula used in the docstring. Unit tests against known textbook
      reference values — no network, no live chain dependency.
- [ ] **GF-3** — Implied-vol solver, `src/pricing/implied_vol.py`. Newton-Raphson from a mid
      price back to IV, with bounds/max-iteration guards and a bisection or other fallback for
      non-convergence; never raises — returns `None` + logged WARNING on failure, matching this
      repo's non-fatal contract elsewhere. Unit tests: round-trip a BS-priced synthetic option
      back through the solver and confirm the recovered IV matches within tolerance.
- [ ] **GF-4** — Wire the fallback into `filter_strikes_by_delta()` (or a thin wrapper around it)
      in `src/instruments/strike_selector.py`: detect when the input chain's Greeks are all-zero,
      and only then compute delta per-row via GF-2/GF-3 using spot + strike + DTE + solved IV.
      Tag each row's delta origin (`"upstox"` vs `"computed"`) in the returned dict for
      downstream logging/audit. Log a WARNING once per run when the fallback path is used.
- [ ] **GF-5** — Validation gate (blocking before any live-capital-adjacent use): run the
      fallback path against the known-good chain picked in GF-1 (where Upstox *does* return real
      Greeks), compare computed delta vs Upstox's own delta per strike, and record the observed
      error against GF-1's tolerance decision in `stories.md`. This must pass before GF-4's
      change is considered trustworthy for `paper_ic_entry.py --expiry-type yearly`.
- [ ] **GF-6** — Docs close: `CONTEXT.md` new `src/pricing/` module entry, `DECISIONS.md` entry
      (cite the 2026-07-22 zero-Greeks discovery chain + this story's validation results),
      `TODOS.md` session log line.
