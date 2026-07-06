# Greeks / Option-Chain Correctness Checks — Story

**Source:** `docs/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 row 6 (CRITICAL, contested — see D1) — FR-5 GREEKS-1/PARITY-1, FR-2 F7.

## T1

**Do not implement directly.** First step is a council/quant consultation (`options-strategist` / `greeks-analyst` per CLAUDE.md's Council Decision Protocol) to decide: (a) tolerance bands for a put-call-parity check (C - P = S - K*e^(-rT), fixture-arithmetic only, cheap — implement first), and (b) reference-model assumptions for a Black-Scholes golden test (implement second, more expensive to get right — dividend yield treatment for NiftyBees, which rate curve, which fixture snapshots). Log the consultation outcome in DECISIONS.md before writing any check. Once the quant call is made: implement the parity check against `tests/fixtures/responses/option_chain/` fixtures first; implement the BS reference test second, gated on the same fixtures with the agreed tolerance band.

**Files touched:** TBD pending council output — likely `src/paper/greeks.py` or a new `src/validation/` module, `tests/unit/test_parity.py`, `tests/unit/test_bs_reference.py`

**Tests:** happy-path + error/edge-case per CLAUDE.md Step 4, in the files listed above.
