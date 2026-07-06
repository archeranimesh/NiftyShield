# FR-5 — Test Adequacy & Ground-Truth Coverage Review

**Persona:** Test Auditor
**Scope attached:** `tests/`, `src/` (cross-reference), `CLAUDE.md`
**Date:** 2026-07-06

---

## 0. Environment / methodology note

**Coverage command could not be fully executed in this sandboxed environment.**

- The checked-in `.venv` is broken here (macOS host shebang). A fresh venv at
  `/tmp/fr5env` was created and could install `pytest`, `pytest-cov`, `hypothesis`,
  `pydantic`, `pydantic-settings`, `structlog`, `python-dotenv`, `pyyaml`, and
  `requests` without issue.
- `pandas` could not be installed — the sandbox root filesystem is at ~61%/100%
  effective capacity for this operation and `pip install pandas` fails with
  `OSError: [Errno 28] No space left on device`. `src/paper/`, `src/strategy/`,
  and most of `src/paper`'s test files import `pandas` transitively (via
  `src/strategy/reentry_mixin.py` and `scripts/record/record_paper_trade.py`),
  so `tests/unit/paper/*` and `tests/unit/strategy/*` could not be collected
  under coverage.
- `src/risk/` has **zero** pandas dependency and did run under real coverage:

  ```
  Name                        Stmts   Miss  Cover
  ---------------------------------------------------------
  src/risk/__init__.py            0      0   100%
  src/risk/delta_tracker.py      51      0   100%
  src/risk/entry_gate.py         11      0   100%
  src/risk/models.py             12      0   100%
  ---------------------------------------------------------
  TOTAL                           74      0   100%
  30 passed
  ```

- For `src/paper/` and `src/strategy/`, this report falls back to **static
  file-presence / assertion-content analysis** (reading test files directly
  against source files) rather than measured line coverage. Any claim below
  about "no golden test exists" is based on reading every relevant test file's
  assertions, not on a coverage percentage — flagged explicitly per finding.
- No `pyproject.toml` `fail_under=80` gate could be evaluated against real
  numbers for `src/paper/` or `src/strategy/` for the reason above. This is a
  genuine gap this session could not close — **recommend a follow-up session
  with a working `.venv` or a host with sufficient disk to install `pandas`**
  before treating the 80% aggregate gate as verified for the two modules that
  matter most financially.

---

## 1. src/risk/ — measured, real coverage (100%)

`src/risk/delta_tracker.py` (`PortfolioDeltaTracker.aggregate_delta`,
`_position_delta`) is the standout module in the repo for test rigor:

- **Golden tests exist and are sign-explicit.** `tests/unit/risk/test_delta_tracker.py`
  asserts exact values for every leg type: short put → `Decimal(1)`, short call →
  `Decimal(-1)`, long put → `Decimal(-1)`, long call → `Decimal(1)`, NiftyBees →
  a fully hand-computed fraction. A sign flip in `_position_delta`'s PE/CE branch
  would fail multiple tests immediately.
- **Property tests exist and specifically target the sign-flip case**:
  `test_ce_delta_sign_matches_net_qty` and `test_pe_delta_sign_opposite_net_qty`
  in `tests/unit/risk/test_delta_hypothesis.py` generate random `net_qty` and
  assert the sign relationship holds — this is exactly the property/golden pair
  FR-5 was asked to look for, and here it exists in both forms.
- **Rating: no finding.** This module should be the reference example cited when
  other modules are asked to close their golden-test gap.

---

## 2. src/paper/tracker.py — `_compute_leg_unrealized_pnl` (static analysis)

**Finding PNL-1 — ERROR** (financial logic with property tests but the
*targeted* unit-level test file has no golden assertion; a golden test exists
one layer up, at integration level, so this is graded ERROR not CRITICAL).

- `tests/unit/paper/test_pnl_hypothesis.py` exercises
  `_compute_leg_unrealized_pnl` via `hypothesis` `@given` properties only:
  zero-qty-is-zero, at-cost-is-flat, profit/loss *direction* matches price
  movement. **None of these assert an exact numeric P&L value** — a bug that
  scaled the result by the wrong constant, or that used `net_qty` instead of
  `abs(net_qty)` in a way that preserved sign but not magnitude, would not be
  caught by this file.
- However, `tests/unit/paper/test_tracker.py` (`test_compute_pnl_short_profit`,
  `test_compute_pnl_short_loss`, `test_compute_pnl_long_profit`,
  `test_compute_pnl_realized_from_closed_trade`) DOES assert exact values
  (e.g. `assert unrealized == Decimal("4500.00")  # (120-60)*75`) by calling
  `PaperTracker.compute_pnl`, which internally calls `_compute_leg_unrealized_pnl`.
  This closes the gap **at the integration level** — a sign or magnitude bug in
  the core function would fail these tests too.
- **Net assessment:** the gap is real but narrower than the seed issue implies —
  it's "the property-test file itself has no golden case" rather than "no golden
  test exists anywhere for this calculation." Recommend adding 1-2 exact-value
  assertions directly into `test_pnl_hypothesis.py` (or a new
  `test_pnl_golden.py`) so the unit closest to the math is self-verifying
  without depending on the tracker integration path staying wired up the same
  way.
- Could not confirm via coverage numbers whether `_compute_leg_unrealized_pnl`
  itself is fully covered (pandas import blocker, see §0) — static read confirms
  both code paths (short branch, long branch, zero branch) are hit by at least
  one of the two test files.

---

## 3. src/strategy/profit_lock_engine.py — ProfitLockEngine (static analysis)

**Rating: no finding — this module has strong golden-test coverage,
counter to what the seed issue in stories.md might suggest.**

`tests/unit/strategy/test_profit_lock_engine.py` is NOT purely a property-test
gap. It contains hand-worked, commented exact-value assertions, e.g.:

```python
# new put ask = 40.5, new call ask = 40.5 -> total = 81
# old put bid = 9, old call bid = 9 -> total = 18
# D_lock = 81 - 18 = 63
assert decision.net_debit_pts == Decimal("63")  # 81 - 18
...
assert decision.guaranteed_floor_fraction == Decimal("87") / Decimal("260")
```

and a dedicated golden test of the private formula itself:
`test_formula_evaluation_exact` / `test_formula_evaluation_fails` call
`engine._evaluate_floor_formula(...)` directly with hand-computed inputs and
boundary-crossing outputs (144 <= 150 passes, 170 > 150 fails). This is exactly
the "would fail if the sign/magnitude were flipped" bar FR-5 is auditing for.

**No hypothesis/property-test file exists for `ProfitLockEngine`** (confirmed:
only 3 hypothesis files exist repo-wide — `test_delta_hypothesis.py`,
`test_ivr_hypothesis.py`, `test_pnl_hypothesis.py` — none for
`profit_lock_engine.py`). Given the golden-test coverage is already strong here,
this is **WARNING, not ERROR**: a property-test suite would add confidence
against untested input combinations (e.g. randomized `active_put_width_pts` /
`active_call_width_pts` / chain shapes), but its absence does not leave the
module's core arithmetic unverified the way a pure-property-only module would be.

---

## 4. src/strategy/exit_signals.py — ExitSignalEngine (static analysis)

**Rating: no finding — also has strong golden/boundary-test coverage.**

`tests/unit/strategy/test_exit_signals.py` is unusually thorough: every CSP/CC/PP
threshold (`PROFIT_TARGET` at 30%, `HARD_STOP` at 2x, `DELTA_BREACH` at 0.40,
`TIME_STOP` at 21 days, `ROLL_ELIGIBLE` at DTE<=7/DTE<=5, `PROXY_DELTA_WARN` at
0.65, `PROXY_DELTA_CRITICAL` at 0.40 for 3+ consecutive days) has an explicit
boundary-inclusive/exclusive pair of tests (e.g.
`test_evaluate_hard_stop_csp_fires_at_2x` + `_no_fire_below_2x`,
`test_evaluate_delta_breach_csp_boundary_inclusive`). This is exactly the
"one happy-path + one error/edge-case" rule from `CLAUDE.md` Step 4, applied
consistently across ~13 public classmethods.

**No hypothesis/property-test file exists for `ExitSignalEngine`** either.
Same reasoning as §3: **WARNING**, not a coverage gap that leaves the math
unverified — the boundary-pair pattern here is arguably a *stronger* signal-flip
guard than a randomized property test would be, since thresholds are exact
business rules (2x, 0.40, 21 days) rather than continuous functions where
property-based fuzzing adds the most value.

**Correction to the seed issue in stories.md:** the seed text frames
"ProfitLockEngine / ExitSignalEngine lack a property-test suite" as presumptively
a gap on par with the Greeks/PnL property-only modules. Static reading shows the
opposite risk profile: these two modules are golden-heavy / property-light,
while `_compute_leg_unrealized_pnl` (§2) and the Greeks parser (§5) are the
ones that are property-heavy / golden-light at the targeted-file level. The
seed issue's framing should be revised in `DECISIONS.md` / follow-up story
text to point at the correct modules.

---

## 5. Greeks — parser correctness vs. Greeks correctness (NEEDS-OPUS-REVIEW)

**Finding GREEKS-1 — CRITICAL.** `NEEDS-OPUS-REVIEW`

`tests/unit/test_greeks_capture.py` (`test_parse_chain_atm_ce_greeks`,
`test_parse_chain_atm_pe_greeks`) asserts exact Decimal values for delta, gamma,
theta, vega, iv against a recorded fixture
(`tests/fixtures/responses/option_chain/nifty_chain_2026-04-07.json`):

```python
assert ce.delta == Decimal("0.525")
assert ce.iv == Decimal("27.4")
assert ce.theta == Decimal("-28.0612")
assert ce.vega == Decimal("10.5313")
assert ce.gamma == Decimal("0.0005")
```

**This is a golden test for the parser** (proves `parse_upstox_option_chain`
faithfully reproduces whatever Upstox sent, byte-for-byte through the Decimal
conversion) — it is **not** a golden test for the Greeks themselves. Upstox's
own `option_greeks.delta` value is treated as ground truth with no independent
verification (e.g. a Black-Scholes reference implementation computing delta
from spot/strike/IV/DTE/rate and checking Upstox's reported value is within
tolerance). If Upstox's Greeks feed has a sign error, a stale-IV bug, or a
unit mismatch (e.g. theta per-day vs per-year) on their side, nothing in this
repo's test suite would catch it — the fixture *is* the (uninspected) ground
truth.

**Cross-reference with FR-2:** `docs/plan/full-repo-review/findings/FR-2_quant-reviewer.md`
Finding 7 independently confirms the same gap ("No golden-value test exists
anywhere for a Black-Scholes-derived Greek") and additionally notes it is the
reason two other FR-2 findings (financial-logic errors) went undetected until
manual ground-truth reconciliation — FR-2 rates the absence itself **WARNING**
(absence of a test is not itself a wrong result) while treating the *downstream*
undetected errors as the higher-severity findings. This review rates GREEKS-1
**CRITICAL** because it is scoped to "is the correctness-checking test missing
for financial logic" per the FR-5 rating rubric, not to whether the absence has
yet produced a known bad number in production — the two ratings are consistent
once the different rating axes are accounted for; FR-7 should preserve both
framings rather than collapsing to one severity label.

**Why NEEDS-OPUS-REVIEW:** whether an independent Black-Scholes/Greeks
reference implementation is warranted, and what tolerance would be appropriate
given Upstox's likely internal model assumptions (dividend yield, rate curve,
American vs European treatment for index options), is a quant judgment call
this pass is not making. Flagging the gap; not asserting what the correct
delta for 22250 CE on 2026-04-07 actually was.

---

## 6. Put-call parity — option chain parser (NEEDS-OPUS-REVIEW)

**Finding PARITY-1 — CRITICAL.** `NEEDS-OPUS-REVIEW`

Confirmed via `grep -r "parity" tests/ src/` (repo-wide): **zero matches.**
No test anywhere checks put-call parity
(`C - P ≈ S - K·e^(-rT)`, or the simpler no-dividend approximation
`C - P ≈ S - K` for near-the-money short-dated index options) against the
parsed `OptionChain` from `src/client/upstox_market.py` /
`src/models/options.py`. This matches FR-2 Finding 7's note that "No
put-call-parity test exists for `parse_upstox_option_chain`
(`src/client/upstox_market.py:327`) either" — both reviews independently
confirm zero matches for "parity" repo-wide.

This matters because:
- `OptionChainStrike.ce` / `.pe` are independently optional (`None` if the
  broker omits either side) — there's no cross-field validation tying the two
  sides of a strike together at all, let alone a parity check.
- A parity check is one of the cheapest independent-reference tests available
  for options data (it doesn't require re-deriving Greeks, just arithmetic on
  the fixture's own bid/ask/spot fields) and would catch a broad class of
  parser bugs: wrong strike-to-leg mapping, CE/PE swap, stale spot price
  mismatched to the chain snapshot.
- **Why NEEDS-OPUS-REVIEW rather than a concrete PR suggestion:** the correct
  tolerance band for a parity check on NSE Nifty weekly/monthly options
  (accounting for the risk-free rate proxy to use, whether index dividend
  yield is material for Nifty, and how wide bid/ask spreads make "equality"
  fuzzy near expiry) is a quant call, not a coverage-counting one. Flagging
  that this check is entirely absent; not asserting the tolerance value.

---

## 7. Coverage gate (`fail_under=80`) — partial verification

- `src/risk/`: **100%** measured directly (§1) — comfortably clears the gate,
  no finding.
- `src/paper/`, `src/strategy/`: **could not measure** in this sandbox (§0).
  Static reading suggests these modules are *not* thin on tests by file count —
  every source file in both directories has a corresponding test file, and the
  ones read in depth (`profit_lock_engine.py`, `exit_signals.py`,
  `metrics.py`, `tracker.py`) have substantial assertion density. But file
  presence does not equal line coverage; branches inside large `if/elif` chains
  (e.g. `ProfitLockEngine.evaluate`'s ~10 early-return branches) could still be
  individually uncovered without a coverage tool confirming it.
- **Recommendation (WARNING, process not code):** the next session with a
  working `.venv` (or more disk headroom) should run
  `pytest tests/unit/paper tests/unit/strategy --cov=src/paper --cov=src/strategy --cov-report=term-missing`
  specifically, before anyone treats the repo-wide 80% aggregate as verified
  for the financial-logic modules. An aggregate pass with `src/risk/` at 100%
  could currently be masking a lower number in `src/paper/` or `src/strategy/`
  and nothing in this session can rule that out.

---

## 8. Other observations (lower severity)

- **INFO** — `tests/unit/strategy/test_profit_lock_engine.py`'s
  `test_zone2_invalid_prices` has a verbose, three-way-fallback
  `model_copy`/`copy`/`dataclasses.replace` block to mutate a frozen Pydantic
  model, with a comment trail showing the author iterating live in the test
  ("Actually wait, let's just make a new OptionChainStrike"). Functionally
  fine, but worth a cleanup pass — the reader has to figure out which of the
  three branches actually executes for the current Pydantic version.
- **INFO** — `pyproject.toml` has `-n` (pytest-xdist) wired into `addopts`,
  which is not installed in this sandbox venv and had to be overridden with
  `-o addopts=""` to run anything at all. Not a repo bug (xdist is presumably
  in the real `.venv`), but worth confirming the real `.venv` actually has
  `pytest-xdist` installed — if it doesn't, `pytest tests/unit/` as instructed
  by `CLAUDE.md`'s Step 5b would fail to even start, not just run slow.

---

## Summary table

| Finding | Module | Rating | Tag |
|---|---|---|---|
| `src/risk/delta_tracker.py` | risk | No finding — reference example | — |
| PNL-1 | `src/paper/tracker.py::_compute_leg_unrealized_pnl` | ERROR | — |
| ProfitLockEngine no property-test suite | `src/strategy/profit_lock_engine.py` | WARNING | — |
| ExitSignalEngine no property-test suite | `src/strategy/exit_signals.py` | WARNING | — |
| GREEKS-1 | `src/client/upstox_market.py` / Greeks correctness | CRITICAL | NEEDS-OPUS-REVIEW |
| PARITY-1 | option chain parser / put-call parity | CRITICAL | NEEDS-OPUS-REVIEW |
| Coverage gate unverified for paper/strategy | process | WARNING | — |
| Test cleanup verbosity | `test_profit_lock_engine.py` | INFO | — |
| pytest-xdist addopts dependency | `pyproject.toml` | INFO | — |

**2 findings tagged `NEEDS-OPUS-REVIEW`**: GREEKS-1, PARITY-1.

---

## Closing block

> State the persona you reviewed as (Test Auditor). Name at least one perspective this
> review did not cover that a different persona would have caught — write "none identified"
> explicitly if genuinely nothing comes to mind, do not omit this section.

**Persona reviewed as:** Test Auditor.

**Perspective not covered:** This review reads test *assertions* to judge whether
a sign flip or magnitude error would be caught, but it does not evaluate whether
the *fixtures themselves* are representative of adversarial market conditions
(e.g. an option chain snapshot during a circuit-breaker halt, a strike with
crossed bid/ask, an expiry-day chain with near-zero time value across every
strike). A **Market-Data Adversarial Reviewer** persona — someone who thinks
about what a broker feed looks like during NSE's worst 30 minutes of the year
rather than a normal Tuesday — would likely find that every fixture in
`tests/fixtures/responses/option_chain/` was recorded on a calm day, and that
the parser's behavior under genuinely malformed/extreme broker payloads (not
just `null` or `"N/A"` Greeks, which are tested) is unverified. This review
also did not audit `src/backtest/`, `src/dhan/`, `src/mf/`, or `src/nuvama/`
in any depth — the scope given (`src/risk/`, `src/paper/`, `src/strategy/`)
was followed literally; a full-repo test-adequacy pass would need separate
sessions for those modules.
