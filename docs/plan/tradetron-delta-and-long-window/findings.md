
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

## Live Greeks probe (TDL-2)

Probe: template 999089294 ("NS Greeks Probe v2", a copy of 999078810 because the original had a running deployment), deployed Live Offline by Animesh as SID **999204818**, run 1, one snapshot at
2026-10-07 04:00:00 UTC (09:30 IST). Tradetron spot 22624.35, `strike_spot` 22600. Upstox side: `data/historical/option_chain/intraday/2026/10/07/upstox_0930_<bucket>.parquet`, `snapshot_ts` 04:00:02
UTC, spot 22620.35 (4 points below Tradetron's; the two readings are seconds to a minute apart, inference). Expiries Tradetron resolved: weekly 2026-10-13, `Current Month` offsets 0/1/2 = 2026-10-27 /
2026-11-23 / 2026-12-29. Strikes: ATM-SPOT 22600 for all three expiries; the `dx` pair is ATM-SPOT +4 CE = 22800 (LTP 596.0 exact match) and -4 PE = 22400 (LTP 338.65 exact match; strike inferred from
the LTP, not recorded).

<!-- lint-ignore-length -->
| Instrument | TT delta | UP delta | Δ | TT IV | UP IV | TT LTP | UP LTP |
|---|---|---|---|---|---|---|---|
| 10-13 22600 CE | 0.5183 | 0.5507 | -0.032 | 13.33 | 12.33 | 168.80 | 168.35 |
| 10-13 22600 PE | -0.4799 | -0.4551 | -0.025 | 13.26 | 14.25 | 146.55 | 147.85 |
| 10-27 22600 CE | 0.5493 | 0.5509 | -0.002 | 13.25 | 13.38 | 325.70 | 324.30 |
| 10-27 22600 PE | -0.4513 | -0.4491 | -0.002 | 13.49 | 13.39 | 247.15 | 249.45 |
| 12-29 22600 CE | 0.6001 | 0.6038 | -0.004 | 12.55 | 12.41 | 710.00 | 710.00 |
| 12-29 22600 PE | -0.4003 | -0.3977 | -0.003 | 12.62 | 12.64 | 405.00 | 405.00 |
| 12-29 22800 CE | 0.5426 | 0.5457 | -0.003 | 12.42 | 12.32 | 596.00 | 596.00 |
| 12-29 22400 PE | -0.3477 | -0.3451 | -0.003 | 12.95 | 12.95 | 338.65 | 338.65 |

Dec gamma, theta and vega also agree closely (22600 CE: TT 0.00028 / -3.18 / 42.26, UP 0.0003 / -3.14 / 42.17).

Measured results, n = 8 instruments, one timestamp:

- **Far-dated contract: Tradetron returns nonzero Greeks, and so does Upstox.** On 2026-10-07 09:30 the 2026-12-29 contracts near the money have real Upstox Greeks in both the quarterly and the yearly
  bucket (the two buckets hold identical rows). The "yearly bucket all-zero Greeks" pattern from 2026-07-22 and 2026-08-06 did **not** reproduce at these strikes today. Where Upstox does show zeros
  today it is deep ITM, not all-zero: of 176 Dec rows with LTP > 0, 20 have IV 0 and delta ±1.0 (CE 16000 to 21350, PE 24150 and above, e.g. CE 19000 LTP 3827, OI 262535).
- **Monthly and Dec deltas agree within 0.004** (Tradetron slightly lower in absolute terms on CE and PE alike); IV within 0.14 vol points; Dec LTP identical.
- **The weekly pair is the outlier**: delta differs by 0.025 to 0.032 and IV by about 1 vol point in opposite directions on CE and PE (TT 13.33 / 13.26, UP 12.33 / 14.25). Tradetron's CE and PE IV
  agree with each other, Upstox's do not (CE and PE IV 2 points apart), which looks like Upstox's weekly reading, but that is an inference from one pair.
- Tradetron's `Delta()` therefore matches Upstox's to about 0.004 on monthly and far-dated near-ATM contracts. Together with TDL-1 (0.145 at its 0.15 picks) this supports using Tradetron delta as
  agreeing with Upstox at strike level.
- Upstox lists no 2026-11-23 expiry (only 10-13, 10-27, 12-29), while Tradetron's `Current Month` offset 1 resolves to 2026-11-23. Offset 2 reaches December.

Reference for `greeks-bs-fallback` GF-1 and GF-5 (input only; that story's files are untouched): this is a third-party delta on Dec 2026 contracts that agrees with Upstox to ~0.004 near the money, so
for these strikes today a Black-Scholes fallback would have had nothing to correct. Limits: one timestamp, four Dec strikes, Tradetron's delta methodology unknown (another model, not ground truth),
and the zero-Greek condition that motivated GF was absent on the day, so this does not test the fallback on the case it exists for. A re-run on a day the yearly bucket shows zeros would.
