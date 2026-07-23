# Greeks BS Fallback — Story Specs

---

## GF-1 — Audit scope + pick validation ground truth

**Problem:**
Confirmed 2026-07-22 (Cowork session): live Dec 2026 NIFTY chain (DTE 160, the yearly IC
bucket's resolved expiry per `DECISIONS.md` BUG-015) returns `option_greeks.delta` = `0.0` on
all 20 strikes, both PE and CE — alongside `gamma`/`theta`/`vega`/`iv`, all also `0.0`. This is
not a missing-field (`None`) case; the field is present and populated with a real zero. The same
chain's `market_data` block (`ltp`/`bid`/`ask`/`oi`/`volume`) is fully populated and liquid
(OI in the hundreds of thousands to millions per strike, tight spreads) — ruling out "unquoted
contract" as the explanation. Confirmed via `scratch/2026-07-22_ic_yearly_leg_resolution_repro.py`
and `scratch/2026-07-22_ic_yearly_full_chain_dump.py` (the latter now accepts a bucket-name CLI
arg, defaulting to `yearly`).

A quarterly repro (`python scratch/2026-07-22_ic_yearly_full_chain_dump.py quarterly` — resolves
to 2026-09-29, DTE 69 as of 2026-07-22) was requested in the same session but its output was not
captured before this story was written. **Do not assume the pattern is yearly-only** — confirm
which buckets are actually affected before scoping GF-4's fallback trigger.

**Task:**
1. Run the full chain dump script (or its logical equivalent) against `weekly`, `monthly`,
   `quarterly`, and `yearly` buckets. For each, record: does Upstox return nonzero Greeks or not?
2. Pick the nearest bucket that reliably returns real, nonzero Greeks as GF-5's validation ground
   truth — the chain we'll compare our BS-computed deltas against to sanity-check the math before
   trusting it anywhere Upstox gives us nothing.
3. Decide and document the three open items from `prompt.md`:
   - **Risk-free rate.** Check whether any existing code in this repo (e.g. `src/backtest/ivr.py`,
     any options-pricing-adjacent module) already has a rate assumption or config value to reuse.
     If none exists, propose a flat constant (e.g. India's approximate short-term risk-free rate)
     and get it confirmed rather than picking silently — this is a modeling input, not a
     mechanical default.
   - **Time-to-expiry convention.** Calendar-days/365 vs. trading-days/252. Check for an existing
     convention in this repo's vol/backtest code before introducing a new one.
   - **Delta tolerance for GF-5.** How close must a BS-computed delta be to Upstox's own delta on
     the known-good chain to trust the fallback elsewhere? Propose a number (e.g. ±0.02 absolute)
     based on what's defensible for strike selection at the target-delta bands in
     `ic_expiry_config.py` (`delta_range=0.05`-`0.06` across presets — the tolerance should be
     meaningfully tighter than the entry band itself, or it's not adding real precision).
4. **Do not write any pricing code in this task.** Output is the audit findings + the three
   decisions, appended to this file under a new `### GF-1 findings` heading.

**Files touched:** none (read-only audit, plus scratch script runs). Append findings here.

### GF-1 findings (partial — weekly/monthly still unconfirmed)

Ran `scratch/2026-07-22_ic_yearly_full_chain_dump.py` against `yearly` and `quarterly` on
2026-07-22 (`logs/ic_yearly_full_chain.log`-equivalent output, pasted into the session — not yet
saved as a permanent fixture, see below).

- **yearly** (Dec 2026, DTE 160): all 20 strikes, both sides — `delta`/`gamma`/`theta`/`vega`/`iv`
  all exactly `0.0`. Real, liquid `market_data` on every strike (confirmed earlier this session).
  **Zero-Greeks pattern confirmed.**
- **quarterly** (2026-09-29, DTE 69): 104 strike rows, both sides — real, smoothly-varying Greeks
  across essentially every strike with genuine market activity (call delta ranging ~0.95 down to
  ~0.001 as strikes move OTM, put delta mirroring; `iv` 11%–56%; nonzero `theta`/`vega`/`gamma`).
  **No zero-Greeks pattern here — this bucket is a valid known-good chain.**
  - **Anomaly to exclude from GF-5's validation set:** several deep-OTM strikes with `ltp=0` (no
    real trade, e.g. far strikes like 25050 PE, 27000 PE, 30000+ CE/PE) show delta pinned at
    exactly `-1.0` or `1.0` with every other Greek at `0.0` — this looks like Upstox's own
    degenerate/fallback value for a strike with no tradeable quote to derive Greeks from, not a
    real computed delta. GF-5 should only validate against strikes with genuinely smooth,
    non-pinned Greeks (i.e. exclude any row where `abs(delta) == 1.0` and `gamma == 0.0`
    simultaneously — the combination that flags the degenerate case).

**Still open — weekly and monthly buckets have not been checked.** Do not assume they behave
like quarterly; run the same script against both before finalizing GF-4's detection-threshold
design (task explicitly calls this out already).

**Decision — validation ground truth:** use the **quarterly** bucket (2026-09-29 as of this
writing) for GF-5, excluding the pinned-delta anomaly rows described above. Whoever picks this up
should re-resolve the expiry at that time (it will have rolled forward) rather than hardcoding
2026-09-29.

**Not yet decided in this pass — still open for GF-2/GF-3's implementer:**
1. Risk-free rate source.
2. Time-to-expiry convention (calendar vs. trading days).
3. Exact delta tolerance for GF-5 (a candidate number: the quarterly data above shows real deltas
   varying by ~0.01–0.02 between adjacent ₹50-wide strikes near the money, e.g. 22800→22850 PE
   goes -0.143→-0.150; a tolerance much looser than that would make the validation gate
   meaningless, so ±0.02 absolute is a reasonable starting proposal, not yet confirmed).

**Recommendation:** save the raw quarterly chain dump (the full log content) as a static fixture
file (e.g. `tests/fixtures/chains/nifty_quarterly_2026-09-29.json`) before this expiry rolls past
its current DTE — GF-5's regression test needs a frozen snapshot, not a live call every test run.

---

## GF-2 — Black-Scholes pricer + delta formula

**Prerequisite:** GF-1 complete (rate + DTE convention decided).

New module: `src/pricing/black_scholes.py`. Pure functions, no I/O, no live chain dependency:
- `call_price(spot, strike, dte, rate, iv) -> float`
- `put_price(spot, strike, dte, rate, iv) -> float`
- `call_delta(spot, strike, dte, rate, iv) -> float`
- `put_delta(spot, strike, dte, rate, iv) -> float`

Use the standard Black-Scholes-Merton formula for European options on an index (no dividend
adjustment needed for NIFTY index options in the base case — confirm this assumption is correct
for NSE index options specifically before shipping, and document the assumption in the module
docstring either way). Cite the reference formula (e.g. Hull, *Options, Futures, and Other
Derivatives*) in the module docstring.

Type hints per `CLAUDE.md` Python Standards; Google-style docstrings. These are pricing-internal
calculations — use `float`, not `Decimal`, for the math itself (the project's `Decimal`-for-money
invariant applies to stored/persisted monetary fields, not floating-point-native option-pricing
math; document this explicitly in the module docstring so it isn't mistaken for an oversight).

**Tests:** `tests/unit/pricing/test_black_scholes.py` — known textbook reference values (e.g. a
standard Hull example or a cross-checked online BS calculator output) for both price and delta,
at-the-money and away-from-the-money, call and put. No network, no live data dependency.

**Files touched:** `src/pricing/__init__.py` (new, per `CLAUDE.md`'s new-package checklist —
needs an `__init__.py` or the codebase-memory graph silently skips it), `src/pricing/black_scholes.py`,
`tests/unit/pricing/__init__.py`, `tests/unit/pricing/test_black_scholes.py`.

---

## GF-3 — Implied volatility solver

**Prerequisite:** GF-2 complete.

New module: `src/pricing/implied_vol.py`:
- `solve_iv(option_type, mid_price, spot, strike, dte, rate) -> float | None`

Newton-Raphson from an initial IV guess (e.g. a fixed starting point like 0.20, or derived from
India VIX if available — GF-1 to confirm which), iterating against `black_scholes.call_price`/
`put_price` until convergence within a tolerance, capped at a max iteration count. Add a
bisection (or other bracketing) fallback for cases where Newton-Raphson fails to converge or
diverges (can happen with poor initial guesses or near-expiry/deep-ITM/deep-OTM edge cases where
vega is near zero). **Never raises** — on non-convergence, return `None` and log a WARNING with
the inputs that failed, matching this repo's established non-fatal contract (see
`src/notifications/telegram_gateway.py`'s pattern, `src/paper/models.py` `option_type` resolution
fallback, etc. — always log-and-continue on data problems, never crash the caller).

**Tests:** `tests/unit/pricing/test_implied_vol.py` — round-trip: price a synthetic option at a
known IV via `black_scholes.call_price`/`put_price` (GF-2), feed that price back into `solve_iv`,
assert the recovered IV matches the original within a tight tolerance. Cover both call and put,
at least one convergence-failure case (e.g. deep ITM near expiry) confirming graceful `None` +
no exception, not just the happy path.

**Files touched:** `src/pricing/implied_vol.py`, `tests/unit/pricing/test_implied_vol.py`.

---

## GF-4 — Wire fallback into strike selection

**Prerequisite:** GF-2, GF-3 complete.

`src/instruments/strike_selector.py::filter_strikes_by_delta()` currently reads
`greeks.get("delta")` straight from the raw Upstox chain row. Add fallback logic: if every row's
delta comes back `0.0` (or `None`) across the whole input `chain_data` for both sides — the
all-zero pattern confirmed in GF-1 — compute delta per-row instead via GF-3's `solve_iv` (from
the row's `mid` price) then GF-2's `call_delta`/`put_delta`. Needs spot price (fetch via whatever
this repo's existing live-spot mechanism is — check `close_ic_legs()` / `ic_close_executor.py`'s
`NSE_INDEX|Nifty 50` LTP pattern per `CONTEXT.md` rather than introducing a new one) and DTE
(already known at the call site — the resolved expiry's DTE, passed through).

Tag each returned row's delta origin — add a `"delta_source": "upstox" | "computed"` key to the
dict `filter_strikes_by_delta` already returns per row — so downstream logging/Telegram
messages/audit can show which entries relied on the fallback. Log a WARNING once per invocation
(not once per strike — that would spam logs across 20+ strikes) when the fallback path activates,
per `LOGGING.md` conventions.

**Detection threshold:** decide (and document) whether "all-zero across the whole chain" is the
right trigger, vs. a per-row check (some strikes could plausibly have real Greeks while others
don't, in principle) — GF-1's multi-bucket audit should inform which is actually observed in
practice; don't over-engineer a per-row fallback if the real-world pattern is always all-or-nothing.

**Tests:** extend `tests/unit/instruments/test_strike_selector.py` (or create it if it doesn't
exist yet — check via graph first) with a fixture chain that has all-zero Greeks + populated
market data, confirming the fallback activates and returns rows with `delta_source: "computed"`
in the target band; a second fixture with real nonzero Greeks confirming the fallback does NOT
activate (uses Upstox's own delta, `delta_source: "upstox"`) — a regression guard against the
fallback firing when it shouldn't and silently overriding good data.

**Files touched:** `src/instruments/strike_selector.py`, `tests/unit/instruments/test_strike_selector.py`.

---

## GF-5 — Validation against known-good chain (blocking gate)

**Prerequisite:** GF-4 complete.

This is the gate the story owner explicitly required before trusting any of this against live
capital. Run the wired-up fallback path (GF-4) against the known-good chain picked in GF-1 (a
bucket where Upstox *does* return real nonzero Greeks) — force the fallback to compute delta
anyway (e.g. via a test-only override, or by temporarily zeroing the input Greeks in a copy of a
real captured chain response) and compare the computed values against Upstox's own real deltas,
strike by strike.

Record the actual observed error (not just "within tolerance" — the real numbers) in this file
under a new `### GF-5 results` heading: per-strike computed vs. actual delta, and whether it
clears GF-1's tolerance decision. If it doesn't clear tolerance, this story does not ship GF-4 to
any live-capital-adjacent path — stop and flag it rather than shipping a fallback that's been
shown to disagree with the real market.

**Files touched:** none required beyond the results write-up, unless a permanent regression test
is added to lock in the validated tolerance (recommended — add one to
`tests/unit/instruments/test_strike_selector.py` using a captured real chain fixture rather than
live network).

---

## GF-6 — Docs close

**Prerequisite:** GF-1 through GF-5 complete and committed.

- `CONTEXT.md` — new `src/pricing/` module entry (mirror the style of existing module entries:
  what each function does, key invariants, test count).
- `DECISIONS.md` — new entry citing the 2026-07-22 zero-Greeks discovery chain (the yearly IC
  entry failure → diagnostic scripts → confirmed data gap → this story's BS fallback decision)
  and GF-5's validation results (the actual tolerance achieved).
- `TODOS.md` — one session-log line per task actually completed this pass, matching the existing
  log format (date | epic-slug task-id — one-line description — SHA).

No code changes in this task.
