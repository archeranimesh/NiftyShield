# Greeks / Option-Chain Correctness Checks — Story

**Source:** `docs/archive/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 row 6 (CRITICAL, contested — see D1) — FR-5 GREEKS-1/PARITY-1, FR-2 F7.

## T1

**Do not implement directly.** First step is a council/quant consultation (`options-strategist` / `greeks-analyst` per CLAUDE.md's Council Decision Protocol) to decide: (a) tolerance bands for a
put-call-parity check (C - P = S - K*e^(-rT), fixture-arithmetic only, cheap — implement first), and (b) reference-model assumptions for a Black-Scholes golden test (implement second, more expensive
to get right — dividend yield treatment for NiftyBees, which rate curve, which fixture snapshots). Log the consultation outcome in DECISIONS.md before writing any check. Once the quant call is made:
implement the parity check against `tests/fixtures/responses/option_chain/` fixtures first; implement the BS reference test second, gated on the same fixtures with the agreed tolerance band.

**Files touched:** TBD pending council output — likely `src/paper/greeks.py` or a new `src/validation/` module, `tests/unit/test_parity.py`, `tests/unit/test_bs_reference.py`

**Tests:** happy-path + error/edge-case per CLAUDE.md Step 4, in the files listed above.

## T2

Implement the put-call-parity fixture check exactly as recorded in `DECISIONS.md` §"Greeks / option-chain correctness checks — parity + BS reference assumptions" (2026-10-02). Pure helpers
(implied-forward OLS, residuals) go in a new `tests/helpers/` package (with `__init__.py`); stdlib only. Error/edge-case tests: a synthetic chain with CE/PE swapped must fail; a strike with a
one-sided quote must be filtered out.

**Files touched:** `tests/helpers/__init__.py`, `tests/helpers/bs_reference.py`, `tests/unit/test_option_parity.py`

## T3

Implement the Black-Scholes golden test against Upstox-reported Greeks with the fitted convention and tolerances from the same `DECISIONS.md` entry (note: Upstox theta omits the carry term).
Parameterise over fixture files so a future longer-DTE snapshot slots in. Error/edge-case tests: `iv = 0` strikes excluded; a unit error (vega per 1.0 instead of per vol point) must fail.

**Files touched:** `tests/helpers/bs_reference.py`, `tests/unit/test_bs_greeks.py`
