
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

## Long-window pre-flight (TDL-3)

Template 999082574 (`NS CC Short Call POC v2`), read with `tt_get_strategy`: 2 entry/exit sets plus a blank Universal Exit, leg instrument id 1855 (NIFTY 50). Wallet read first with
`tt_wallet_balance` on 2026-10-10: **₹160**, backtest price ₹20, prepaid pack 0 spendable (cycle ended 2023-07-24). The template has **no finished run**; `tt_backtest_workbench` shows `runs.count` 0,
so nothing is readable for free yet.

<!-- lint-ignore-length -->
| Window | Check call | Verdict (verbatim) | Confidence | Skipped checks | Quote |
|---|---|---|---|---|---|
| 2021-10-11 to 2026-10-01 (60 months), leg instrument id omitted by mistake | `tt_check_backtestability` | `unknown` (warning `EXCHANGE_UNRESOLVED`) | low | `data_coverage`, `coverage_window` | n/a |
| 2021-10-11 to 2026-10-01 (60 months), with instrument id | `tt_check_backtestability` | `backtestable` | high | none | credits 1, amount 20 |
| 2015-01-01 to 2026-10-01 (about 141 months, probe for a data floor) | `tt_check_backtestability` | `backtestable` | high | none | not quoted |
| 2026-04-01 to 2026-10-01 (post expiry change) | `tt_backtest_workbench` only | not pre-flighted; the check ignores the window on this template | n/a | n/a | credits 1, amount 20 |

Measured results:

- **Blockers and warnings: none** once the instrument id is present. `checks_run` includes `data_coverage`, `underlying_data_coverage` and `coverage_window`; `keyword_surface` found `Find Strike`,
  `Delta`, `Current Month Expiry`, `Select Expiry` and `Days Difference` all in the BT engine. `run_type_recommendation` is `positional`, strong, evidence: Exit references days-difference and NRML
  legs.
- **A template without instrument ids silently skips the coverage checks.** The first call returned `unknown`, not an error. Pass the leg `instrument` field when pre-flighting a hand-built body; this
  is a platform fact for the reference doc.
- **The check does not say where NIFTY option data starts.** A window starting 2015-01-01 passed `coverage_window` with no warning, so either coverage reaches back that far or the gate does not test
  NIFTY options. The output carries no `coverage_from` value. That the first call's `EXCHANGE_UNRESOLVED` text says per-exchange `coverage_from` gates exist is all we learn. Data start is therefore
  **not established**; the funded run's first fill is what will show it.
- **The check does not mention the April 2026 Thursday-to-Tuesday expiry change.** TDL-3's question cannot be answered from the check. The archived CC run already traded the 2026-09-29 and 2026-10-27
  Tuesday monthlies, so the Tuesday regime resolves; whether pre-April Thursday monthlies resolve through `Current Month Expiry` is untested until the run.
- **`max_months` is 60** in the workbench, yet the 141-month probe was not declined by the check; `decline_reason` was null on every workbench call. Treat 60 months as the cap a submit will enforce
  (inference; the submit tool is the authority).
- **Price is flat.** Every window quoted credits 1, amount ₹20; no per-month scaling appeared. The 2026-04-01 window is a subset of the 60-month window, so it needs no run of its own: the post-April
  split in TDL-5 is a free slice of one 60-month run, by entry date.

Caveats a long window will hit (inferences, none tested): NIFTY lot size changed over 2021 to 2026 (the template sizes by lots, so rupee P&L is not comparable across the window; read price ratios, not
rupees); 1-minute candles over 60 months is a large run, runtime unknown; the Thursday-expiry era has 4 DTE and weekly structure the live rule set never saw; and the skipped-delta paths (0.55 delta,
DTE <= 5, 2.5x) will fire or not on this data, which is the point of the run.

**Decision (spend waits for TDL-4):** one run of template 999082574, window 2021-10-11 to 2026-10-01, `type=positional`, `trade_price=Open`, 1-minute candles. Quote ₹20 (Tradetron's `next_run.quote`,
credits 1). Expected CC runs: 1, rising to 2 only if the first run fails on pre-April expiry resolution and a later start date is needed. Wallet ₹160 covers it.

## Comparator and budget (TDL-4)

Read-only inventory on 2026-10-10 (`DB_REGISTRY.md` read first; file date ranges from `pyarrow` aggregates, DB figures from one grouped `paper_trades` query). Graph confirms the readers exist:
`ChainWriter`, `ChainReader` (`get_eod_snapshots`, `get_intraday_snapshots`, `get_strike_delta_series`), `bhavcopy_ingest` (`parse_bhavcopy`, `download_bhavcopy`, `write_to_parquet`),
`bhavcopy_loader.load_options_ohlcv`, `vix_ingest`, `compute_ivr`, `equity_bhavcopy_ingest` (equity and index).

<!-- lint-ignore-length -->
| Own-side data | Location | Range found | Size |
|---|---|---|---|
| NIFTY options OHLCV (F&O bhavcopy, parquet) | `data/offline/options_ohlcv/` | 2016-01 to 2017-05 and 2026-05 to 2026-06 only; 19 files, 685,452 rows, 330 trade dates | 7.9 MB `data/offline` total |
| NIFTY futures OHLCV | `data/offline/futures_ohlcv/` | 2026-06 only | 1 file |
| NIFTY index and equity daily | `data/offline/nifty_index/`, `equity_ohlcv/` | 2025-07 to 2026-09 | 15 files each |
| Upstox chain, intraday (with delta) | `data/historical/option_chain/intraday/` | 2026-06-01 to 2026-10-07 | 273 MB with `eod` |
| Upstox chain, EOD | `data/historical/option_chain/eod/` | 2026-06 to 2026-10, 249 files | |
| India VIX daily | `data/historical/ohlc/india_vix/` | 2016 to 2026 yearly parquet, plus two NSE CSVs | 192 KB |
| Raw bhavcopy CSV outside the repo | `~/Documents/trade/fno-bhav/` | `fo060224.csv`, `op060224.csv` (one day, 2024-02-06) | 2 files |
| Paper CC, Collar and PP legs | `paper_trades`, strategy `paper_nifty_overlay` | 2026-08-11 to 2026-10-07, 25 rows (all overlay roles together) | |

Findings:

- **No own-side data covers 2021-10 to 2026-04, about 55 of the 60 months in the TDL-3 window.** The options bhavcopy has a 17-month block in 2016 to 2017 and a 2-month block in 2026; the Upstox chain
  with delta starts 2026-06-01; paper starts 2026-08-11. Only 2026-05 to 2026-10 has any overlap with a Tradetron run.
- **A CC, PP or Collar cycle list cannot be built offline today** over the window. It would need the bhavcopy backfilled for 2021-10 to 2026-04 (the existing bootstrap CLI, `bhavcopy_bootstrap`,
  defaults to 2016-01-01 and can fetch it; not run here) and then a delta source. Bhavcopy has no Greeks, so a model delta would be needed, which overlaps `greeks-bs-fallback` and is out of scope for
  this story.
- **Comparator for a long Tradetron run: none outside 2026-08-11 onward** (paper), and the stored Upstox chain from 2026-06-01 for strike-level delta checks. A long run is therefore interpretable only
  as a **screen of rule viability, cycle count and exit mix**, with rupee P&L scale unreliable (lot-size changes, TDL-3). It cannot be reconciled against anything for the pre-2026 years.
- **Go or no-go: GO for TDL-5 as a screen**, on that limited reading. TDL-8 depends on PP and Collar templates that do not exist yet (TDL-6, TDL-7), so its go is deferred to TDL-7's verdicts.

Budget proposed (Tradetron's own quote is ₹20 per run for the CC template; PP and Collar quotes are unknown until those templates exist and must be re-read from `tt_backtest_workbench`):

<!-- lint-ignore-length -->
| Item | Runs | At quote | Condition |
|---|---|---|---|
| TDL-5 CC, 2021-10-11 to 2026-10-01 | 1 | ₹20 | funded after in-session reconfirmation |
| TDL-5 contingency, later start date if pre-April expiry fails | 1 | ₹20 | only if run 1 fails |
| TDL-8 PP, same window | 1 | ₹20 if quote unchanged | only if TDL-7 gives GO or PARTIAL |
| TDL-8 Collar, same window | 1 | ₹20 if quote unchanged | only if TDL-7 gives GO or PARTIAL |
| **Ceiling** | **4** | **₹80** | of ₹160 wallet read 2026-10-10 |

Committed now: ₹20 (TDL-5 run 1). Everything else is conditional and needs its own in-session confirmation, per the story's spend rule.

**Approval: given by Animesh on 2026-10-10** for the ceiling of ₹80 (4 runs at the ₹20 quote), "use what is required". The story's spend rule still applies: each run is reconfirmed in-session against
its workbench quote and the wallet balance before submit, and a quote above ₹20 stops the run for a new approval.
