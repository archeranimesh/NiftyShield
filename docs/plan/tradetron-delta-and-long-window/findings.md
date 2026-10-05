
# Tradetron delta check and long-window validation — findings

> Reference file for the story. No task checkboxes. Record measured values and mark inferences as inferences. Context: `prompt.md`; the archived CC story is
> `docs/archive/plan/tradetron-cc-backtest-poc/findings.md`.

## Own-data delta check (TDL-1)

Question: the CC backtest's `Find Strike` on delta 0.15 picked strikes 50 to 200 points above paper's on 4 of 5 cycles. Is that because Tradetron's delta differs from the Upstox chain delta?

Source: stored Upstox intraday chain snapshots, `data/historical/option_chain/intraday/2026/<MM>/<DD>/upstox_<HHMM>_<bucket>.parquet` (columns include `strike`, `option_type`, `ltp`, `delta`), read
read-only with the project venv and `pyarrow`; coverage runs from 2026-06-01 to 2026-10-05, so all six dates are covered. For each of the six run-2 entry minutes I took the snapshot file nearest in
time that holds the target expiry. Decimal columns were cast to float for this comparison only. No DB table was queried (`DB_REGISTRY.md` read first; it has no per-strike chain Greeks outside these
files).

<!-- lint-ignore-length -->
| Entry (run 2) | Expiry | Tradetron strike | Upstox delta of that strike | Snapshot LTP vs Tradetron fill | Snapshot file, gap | Paper strike (same date) | Upstox delta of paper strike | Paper credit vs snapshot LTP |
|---|---|---|---|---|---|---|---|---|
| 08-12 10:00 | 09-29 | 25600 | 0.139 | 62.50 vs 63.50 | 1010 quarterly, 10 min | 25400 | 0.194 | 86.725 vs 95.55 |
| 08-19 11:02 | 09-29 | 25100 | 0.145 | 57.30 vs 57.00 | 1100 monthly, 2 min | none (paper entered 08-26) | n/a | n/a |
| 09-02 15:12 | 09-29 | 24700 | 0.152 | 51.40 vs 49.15 | 1255 monthly, 137 min | none | n/a | n/a |
| 09-09 10:00 | 09-29 | 24250 | 0.142 | 42.40 vs 42.40 | 1000 monthly, 0 min | 24200 | 0.160 | 53.900 vs 48.80 |
| 09-16 10:00 | 10-27 | 24400 | 0.145 | 67.15 vs 66.70 | 1000 monthly, 0 min | 24200 | 0.199 | 97.475 vs 99.75 |
| 09-25 10:00 | 10-27 | 23950 | 0.150 | 55.15 vs 55.15 | 1000 monthly, 0 min | 23900 | 0.168 | 64.425 vs 63.60 |

Measured results, n = 6 Tradetron picks and 4 paper strikes:

- **Tradetron's picks sit at Upstox delta 0.139 to 0.152 (mean 0.145).** On these six entries the two vendors' deltas agree within about 0.01 at the chosen strike. The 09-02 row is weaker evidence:
  the nearest snapshot is 137 minutes away.
- **Tradetron's fill prices match the Upstox snapshot LTP closely** (identical on two entries, within 2.25 on the rest), so its backtest prices and Upstox's quotes agree at those minutes.
- **Paper's strikes carry Upstox delta 0.160 to 0.199 (mean 0.180), above the 0.15 target.** Two of four (0.194 on 08-12, 0.199 on 09-16) are above the 0.12 to 0.18 band that TCP-1 read from
  `paper_cc_entry.py:197-212`. The paper strike is higher-delta, closer to the money, and collects more credit, which is the direction of the P&L gap found in the archived story.
- **The paper entry time is not in the DB**, and paper credits agree with the snapshot LTP at the same minute on two of four dates (09-16: 97.475 vs 99.75; 09-25: 64.425 vs 63.60) and not on the other
  two (08-12: 86.725 vs 95.55 at a snapshot 10 minutes after the entry; 09-09: 53.90 vs 48.80). So the time-of-day explanation fits some rows and not others.
- **One scan caution:** on 08-19 a nearest-to-0.15 search over every strike returned 25850, an off-grid strike with an odd delta, while neighbours around Tradetron's 25100 are monotone (25000 at
  0.1755, 25100 at 0.1445, 25200 at 0.1189). A "closest to 0.15" scan over the whole chain is not robust to such rows; this comparison reads the chosen strikes directly.

Verdict: **the archived inference does not hold at these points.** The 2026-10-05 CC story attributed the strike gap to Tradetron's delta methodology differing from the Upstox chain delta. These six
snapshot readings point the other way: Tradetron's 0.15 pick has an Upstox delta of about 0.145, and it is paper's strike that sits higher, at Upstox delta 0.16 to 0.20. Inference only, not
established: paper's entry strikes were not chosen as the closest strike to 0.15 at the minute I checked. Candidate reasons, none verified: a different entry time (the DB has none), an operator choice
of strike, the remainder of `paper_cc_entry.py` after line 215 (not read in TCP-1) applying other ranking, or a different delta field. TDL-6 reads that code and the paper entry notes for the cause.

Limits: n = 6 for the Tradetron side and 4 for the paper side, one regime, snapshot gaps from 0 to 137 minutes, and a delta check at the chosen strike only, not across the whole chain. This does not
test far-dated contracts (TDL-2) or Tradetron's Greeks beyond the strike it selected.

Consequence for the open items: the P&L gap should be re-read as "paper sold nearer the money than 0.15" (more credit and more risk), not as a Tradetron bias. The 2026-10-05 `DECISIONS.md` entry and
the reference-doc note carry the old inference and are corrected in the same commit as this finding.
