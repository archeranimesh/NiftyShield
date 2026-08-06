# Chain Delta/Decay Analysis — Story Specs

---

## CDA-1 — Paired-snapshot reader

**Problem:** To test whether premium moves track delta, we need, per trading day, the chain state
at two points in time (open-ish and close-ish) for the same set of strikes, joined so each row has
both timestamps' `ltp`/`iv`/`delta`/`gamma`/`theta`/`vega`/`spot` fields side by side.

**Data source:** `data/historical/option_chain/intraday/{year}/{month}/{day}/upstox_{HHMM}_monthly.parquet`,
via `ChainReader` (`src/backtest/chain_reader.py`, DuckDB glob-scan — confirmed already exists,
do not write a new reader from scratch). Monthly bucket only for this story (see `prompt.md` for
why yearly/quarterly are out of scope).

**Known gaps to handle, not silently ignore:**
- Some trading days have multi-hour capture gaps (confirmed 2026-08-06: a ~3.5hr gap 10:15–13:50
  and a further gap 14:05–15:56 on that date specifically, caused by the operator's laptop being
  offline/off-network, not a pipeline defect). A day with no snapshot near market open or no
  snapshot near market close should be skipped for that day, not silently paired with whatever
  timestamp happens to exist — log which days were skipped and why.
- Degenerate rows: `abs(delta) == 1.0 and gamma == 0.0` marks a strike with no real tradeable
  quote (Upstox's own fallback behavior on illiquid strikes, confirmed in
  `greeks-bs-fallback/stories.md` GF-1 findings, same pattern seen on monthly and quarterly).
  Exclude these from the paired output — they will look like massive but fake "decay" otherwise.
- `iv == 0` outside the degenerate case above should not occur on monthly (confirmed clean in
  GF-1's monthly audit pass), but assert/log if it does rather than assuming it can't.

**Output:** a function or small module returning, per trading day, a DataFrame/table keyed on
(strike, option_type) with `_open` and `_close` suffixed columns for ltp/iv/delta/gamma/theta/
vega/spot, plus the elapsed `Δt` and `Δspot` for that day.

**Tests:** `tests/unit/analysis/test_chain_pairing.py` (or wherever this lands per graph lookup of
existing `tests/unit/` structure) — static fixture Parquet-equivalent data (in-memory frames, not
real files) covering: a normal day with clean open/close pairs, a day with a gap that should be
skipped, and a day with degenerate rows that should be excluded. No network, no dependency on the
real `data/historical/` tree existing.

**Files touched:** new reader/pairing module (location TBD by implementer — check whether
`src/backtest/` or a new `src/analysis/` is the right home, per existing module conventions),
its test file.

---

## CDA-2 — Delta/gamma/theta/vega decomposition

**Prerequisite:** CDA-1.

Pure function(s), no I/O:
- `expected_move(delta, gamma, d_spot) -> float` — `delta*d_spot + 0.5*gamma*d_spot**2`
- `theta_component(theta, d_t) -> float`
- `vega_component(vega, d_iv) -> float`
- `residual(actual_d_premium, expected_move, theta_component, vega_component) -> float`

`Δt` convention: match whatever this repo's existing vol/backtest code uses (check
`src/backtest/ivr.py` or similar before picking calendar-days vs. trading-days — same open
question flagged in `greeks-bs-fallback/stories.md`, stay consistent with whatever gets decided
there rather than introducing a second convention).

**Tests:** `tests/unit/analysis/test_decay_decomposition.py` — synthetic inputs with hand-computed
expected outputs (e.g. delta=0.5, gamma=0.001, d_spot=100 → expected_move = 55.0), one happy-path
and one edge case (d_spot=0, confirming residual reduces to actual minus theta/vega only).

**Files touched:** decomposition module (co-located with CDA-1's reader or separate — implementer's
call), its test file.

---

## CDA-3 — Aggregation and findings

**Prerequisite:** CDA-1, CDA-2.

Run the pairing + decomposition across every available trading day for the monthly bucket
(2026-06-01 onward as of this writing — re-check actual earliest date via `ChainReader` rather
than hardcoding, more days will exist by the time this runs) with a single script (e.g.
`scripts/analysis/chain_decay_report.py`). Group residuals by moneyness bucket (e.g. ATM ±2
strikes, near-OTM, far-OTM, ITM equivalents) and report: does the residual center near zero
(delta/gamma/theta/vega explain the move) or is there a persistent bias, and which moneyness
bands show the largest unexplained residual.

**Output:** CSV or similar table under `data/analysis/` (new directory, or wherever fits existing
convention) plus a short written summary — does NOT need to be a polished report, this is
exploratory. Append the top-line finding to this file under a new `### CDA-3 findings` heading
once run.

**Files touched:** `scripts/analysis/chain_decay_report.py`, output data file(s), this file
(findings appended).

---

## CDA-4 — Docs close

**Prerequisite:** CDA-1 through CDA-3 complete and committed.

- `CONTEXT.md` — new module entry if `src/analysis/` (or similar) was created.
- `DECISIONS.md` — one entry summarizing the empirical finding (delta-tracking accuracy, which
  strikes decay faster than theta predicts) — this is the actual answer to the question that
  started this story, record it somewhere durable, not just in a CSV nobody reads again.
- `TODOS.md` — session log line.
- `docs/plan/README.md` — update this story's row from "Not started" to its actual status.

No code changes in this task.
