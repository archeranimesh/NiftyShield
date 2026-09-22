# Greeks / Option-Chain Correctness Checks — Tasks

> Find the first unchecked box below. That is the only task for this session.

- [ ] **T1** — **Do not implement directly.** First step is a council/quant consultation (`options-strategist` / `greeks-analyst` per CLAUDE.md's Council Decision Protocol) to decide: (a) tolerance
  bands for a put-call-parity check (C - P = S - K*e^(-rT), fixture-arithmetic only, cheap — implement first), and (b) reference-model assumptions for a Black-Scholes golden test (implement second,
  more expensive to get right — dividend yield treatment for NiftyBees, which rate curve, which fixture snapshots). Log the consultation outcome in DECISIONS.md before writing any check. | Owner:
  Claude | Model: claude-opus-5 | Review: none | SHA: —

---

**Source:** `docs/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 row 6 (CRITICAL, contested — see D1) — FR-5 GREEKS-1/PARITY-1, FR-2 F7.
