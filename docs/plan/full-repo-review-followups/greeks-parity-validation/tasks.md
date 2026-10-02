# Greeks / Option-Chain Correctness Checks — Tasks

> Find the first unchecked box below. That is the only task for this session.

- [x] **T1** — **Do not implement directly.** First step is a council/quant consultation (`options-strategist` / `greeks-analyst` per CLAUDE.md's Council Decision Protocol) to decide: (a) tolerance
  bands for a put-call-parity check (C - P = S - K*e^(-rT), fixture-arithmetic only, cheap — implement first), and (b) reference-model assumptions for a Black-Scholes golden test (implement second,
  more expensive to get right — dividend yield treatment for NiftyBees, which rate curve, which fixture snapshots). Log the consultation outcome in DECISIONS.md before writing any check. | Owner:
  Claude | Model: claude-opus-5 | Review: none | SHA: 6bfb74d

- [ ] **T2** — Put-call parity fixture test per `DECISIONS.md` "Greeks / option-chain correctness checks" (2026-10-02): mid prices, two-sided + `|K − S| ≤ 2000` filter, OLS implied forward, slope /
  per-strike band / ≤ 5% breach / no-sign-bias asserts. Pure helpers in new `tests/helpers/` package; tests in `tests/unit/test_option_parity.py`. | Owner: Claude | Model: claude-opus-5 | Review:
  code-reviewer | SHA: —
- [ ] **T3** — Black-Scholes golden test per the same `DECISIONS.md` entry: spot BSM, r=0.05, q=0, cal/365 to 15:30 IST, carry-free theta, ATM ±5 strikes, `iv = 0` excluded, tolerances delta 0.005 /
  vega 0.05 / theta 0.10 / gamma 0.0001, parameterised over fixture files. Tests in `tests/unit/test_bs_greeks.py`. | Owner: Claude | Model: claude-opus-5 | Review: code-reviewer + greeks-analyst |
  SHA: —

---

**Source:** `docs/archive/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 row 6 (CRITICAL, contested — see D1) — FR-5 GREEKS-1/PARITY-1, FR-2 F7.
