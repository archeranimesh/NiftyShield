# Greeks BS Fallback — Tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: GF-1.**

- [ ] **GF-1** — Audit scope (read-only, no code): confirm which expiry buckets actually hit
      all-zero Greeks (yearly confirmed 2026-07-22, re-confirmed 2026-08-06; quarterly and
      monthly confirmed clean; weekly still unchecked), pick a known-good live chain as GF-5's
      validation ground truth, and surface the three open decisions listed in `prompt.md`
      (risk-free rate source, DTE convention, delta tolerance) for Animesh to decide before
      GF-2 starts. | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **GF-2** — Black-Scholes European option pricer + delta formula, new module
      `src/pricing/black_scholes.py`. Pure functions (call_price/put_price/call_delta/
      put_delta), cite the reference formula used in the docstring. Unit tests against known
      textbook reference values — no network, no live chain dependency. | Owner: Claude |
      Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **GF-3** — Implied-vol solver, `src/pricing/implied_vol.py`. Newton-Raphson from a mid
      price back to IV, with bounds/max-iteration guards and a bisection or other fallback for
      non-convergence; never raises — returns `None` + logged WARNING on failure, matching this
      repo's non-fatal contract elsewhere. Unit tests: round-trip a BS-priced synthetic option
      back through the solver and confirm the recovered IV matches within tolerance. |
      Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **GF-4** — Wire the fallback into `filter_strikes_by_delta()` (or a thin wrapper around
      it) in `src/instruments/strike_selector.py`: detect when the input chain's Greeks are
      all-zero, and only then compute delta per-row via GF-2/GF-3 using spot + strike + DTE +
      solved IV. Tag each row's delta origin (`"upstox"` vs `"computed"`) in the returned dict
      for downstream logging/audit. Log a WARNING once per run when the fallback path is used. |
      Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: —
- [ ] **GF-5** — Validation gate (blocking before any live-capital-adjacent use): run the
      fallback path against the known-good chain picked in GF-1 (where Upstox *does* return
      real Greeks), compare computed delta vs Upstox's own delta per strike, and record the
      observed error against GF-1's tolerance decision in `stories.md`. This must pass before
      GF-4's change is considered trustworthy for `paper_ic_entry.py --expiry-type yearly`. |
      Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: —
- [ ] **GF-6** — Docs close: `CONTEXT.md` new `src/pricing/` module entry, `DECISIONS.md` entry
      (cite the 2026-07-22 zero-Greeks discovery chain + this story's validation results),
      `TODOS.md` session log line. | Owner: Claude | Model: claude-sonnet-5 | Review: none |
      SHA: —

## Story done when

- **GF-1** — audit covers all four expiry buckets, a validation-ground-truth chain is picked, and the three open modeling decisions are confirmed by Animesh.
- **GF-2** — `black_scholes.py` ships with call/put price and delta functions, tested against known reference values.
- **GF-3** — `implied_vol.py` ships a Newton-Raphson (+ bracketing fallback) IV solver that never raises, tested via round-trip against GF-2.
- **GF-4** — `filter_strikes_by_delta()` falls back to computed deltas only when Upstox's own Greeks are all-zero, tagging `delta_source` per row, with regression tests for both paths.
- **GF-5** — computed deltas are validated against a known-good live chain and the observed error is recorded and confirmed within GF-1's tolerance before any live-capital use.
- **GF-6** — `CONTEXT.md`, `DECISIONS.md`, and `TODOS.md` reflect the shipped `src/pricing/` module and the validation results.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in `docs/plan/README.md` and add one line to `TODOS.md` Session Log. When the whole story is done,
follow §Conventions *Completion → archive*.
