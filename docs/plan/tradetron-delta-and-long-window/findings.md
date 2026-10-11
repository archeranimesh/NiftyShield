
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

Update 2026-10-10: after TDL-5, Animesh added a NiftyBees baseline run to TDL-8 and raised the ceiling to **₹100** (of which ₹20 is spent; wallet ₹140). Planned: PP, Collar and NiftyBees at ₹20 each,
one spare run.

## CC long-window run (TDL-5)

Run: template 999082574 (`NS CC Short Call POC v2`), window 2021-10-11 to 2026-10-01, `positional`, `Open` fill, 1-minute candles. Job `ttbt-999110942261010`, bt_id 999110942261010, report
`https://tradetron.tech/bt/view/4417598c213766612670be9cc5dc7755`. Price paid ₹20 (wallet ₹160 to ₹140; the submit response's billing block said ₹0 and was wrong, so trust the wallet). The first
confirm failed with `BT_FLEET_UNAVAILABLE` (nothing charged, token consumed, re-quoted at the same ₹20). The run then sat between queued and running for about 35 minutes before finishing. The
per-trade index ages out after a few days, so the paired round trips are saved in `cc_long_window_cycles.md` in this folder (196 rows: entry and exit time, expiry, strike, credit, exit price, ratio,
gross, set, inferred exit type). Gross P&L over the CSV is 52,877.50, equal to the report's gross.

Headline, report figures, 1 lot, nominal capital ₹100,000: **196 round trips** (195 rule exits plus one window-end close), gross ₹52,877.50, costs ₹2,074.70, net ₹50,802.80, win rate 71.9%, average
win ₹2,696, average loss ₹5,950 (win/loss 0.45), profit factor 1.16, maximum drawdown ₹43,375 net (43.4% of nominal capital, 1,069 days from 2023-04-19 to recovery on 2026-03-23). Worst single trip
₹19,393. Report caveats: `COVERAGE_PARTIAL` high severity (4 sessions had no data, 5 were skipped, so totals cover a shorter period than asked); Sharpe, Sortino and Calmar withheld by the report; MAE
and MFE not produced. Under the 30-round-trip flag this is not: 196 is well above it, but the coverage caveat and the lack of exit reasons mean this is a screen of rule viability and exit mix, not an
edge.

Exit mix by exit-price ratio, 195 rule exits (exit type is **inference** from ratio and DTE; the report has no exit-reason column):

<!-- lint-ignore-length -->
| Inferred exit | Rule | Trips | Share | Gross sum | Mean gross | Mean hold (days) |
|---|---|---|---|---|---|---|
| Target | ratio <= 0.30 | 139 | 71.3% | +375,622 | +2,702 | 9.6 |
| Loss | ratio >= 2.5 | 51 | 26.2% | -314,324 | -6,163 | 7.3 |
| DTE | exit within 5 days of expiry, ratio between | 4 | 2.1% | -3,416 | -854 | 19.2 |
| Other (0.55-delta candidate) | ratio between, DTE > 5 | 1 | 0.5% | -7,290 | -7,290 | 21.2 |

Untested paths that fired: **the 2.5x loss exit fired 51 times** (it never fired in the 6-trip archived run), the **DTE <= 5 exit 4 times**, and the **0.55-delta exit at most once** (the single Other
trip; the delta trigger cannot be told from the other exits without a reason column). The minimum entry credit was 21.5, so the "entry price >= 15" guard on the target never blocked a trip. The five
worst losses were 2026-04-02 (23900 CE, credit 105.35, exit 403.70, ratio 3.83, -19,393), 2026-01-28 (26250, -11,895), 2022-01-04 (-10,212), 2022-03-08 (-9,887) and 2026-06-09 (-9,035). Three of the
five exited at round-number prices (250, 200, 200), which looks like gap fills past the 2.5x trigger (inference). 89 of the 196 exits share their minute with the next entry (immediate same-minute
re-entry, the known flat-gate behaviour).

Regime split. **Correction to the story premise: Tradetron's data shows Tuesday monthly expiries from 2025-09-30, not April 2026.** The monthly expiries in the run read Thu through 2025-08-28, then
Tue on 2025-09-30, 10-28, 11-25, 12-30, 2026-01-27, 02-24, then Mon 2026-03-30 (a holiday shift), then Tue from 2026-04-28. `REFERENCES.md` says the change happened in April 2026; the two disagree and
this story does not edit that file. Flagged for Animesh. Pre-April Thursday monthlies resolve fine (the first fill is a 2021-10-28 contract), which answers the TDL-3 open question. Holiday-shifted
Mon, Wed and non-Thursday expiries occur throughout, so the split below is by expiry date.

<!-- lint-ignore-length -->
| Split | Trips | Gross | Win rate | Exit mix (target / loss / DTE / other) |
|---|---|---|---|---|
| Thursday era, expiry before 2025-09-01 | 155 | +7,829 | 68% | 106 / 45 / 3 / 1 |
| Tuesday era, expiry from 2025-09-30 | 40 | +42,764 | 85% | 33 / 6 / 1 / 0 |
| Entry before 2026-04-01 | 178 | +35,581 | 70% | 125 / 49 / 3 / 1 |
| Entry on or after 2026-04-01 (the repo's stated boundary) | 17 | +15,012 | 88% | 14 / 2 / 1 / 0 |

All gross figures above exclude the window-end trip (ex-FinalClose total +50,592.75). The Tuesday era carries 84% of the total gross on 40 trips, a single regime of about 13 months, so it is not
independent evidence of anything. The Thursday era made +7,829 over 155 trips.

Per set (set membership read from the fills' condition ids): **Set 1 (current month, entry DTE 14 to 31) made -20,368 gross over 112 trips**, win rate 70%, mix 77 target / 32 loss / 3 DTE. **Set 2
(next month, entry DTE 28 to 48) made +70,961 gross over 83 trips**, win rate 75%, mix 62 / 19 / 1 DTE / 1 other (+73,245 with the window-end trip). The report's own set arithmetic agrees in sign (Set
1 -21,474, Set 2 +72,277, net basis; the report says without Set 1 the arithmetic net would be 72,277 and max drawdown 24,015 instead of 43,394, and flags that this is arithmetic, not a re-run). So
the "nearest monthly with at least 14 DTE" rule sells the short-dated current-month calls in Set 1, and those lose over this window despite a 70% win rate.

Entry context, 196 trips: median credit 55.7 (range 21.5 to 125.7), median strike distance above spot +889 points (range +416 to +1,963), median entry DTE 27.

Overlap with paper (2026-08-11 onward, n = 6 Tradetron trips, 5 rule exits and 1 window-end close): the long run's six entries are the same six as archived run 2 and TDL-1 (08-12 25600, 08-19 25100,
09-02 24700, 09-09 24250, 09-16 24400, 09-25 23950), all five rule exits at the 30% target (ratios 0.289 to 0.299), so the template reproduces run 2 exactly and the strike comparison with paper is the
TDL-1 table (paper strikes 25400, 24200, 24200, 23900 on four dates, Upstox delta 0.160 to 0.199). Nothing new is claimed about paper here, and this overlap is 6 trips.

Limits: the 4 missing and 5 skipped sessions; one lot at Tradetron's flat 0.05% slippage and default costs, no fill-quality, bid-ask or margin view; rupee P&L across 2021 to 2026 mixes lot-size
regimes (every fill is quantity 65, so earlier rupee figures are on today's lot, not the lot of the day); exit types inferred. No profitability claim: this says the rule set produces many cycles, a
72% win rate with larger average losses than wins, and a drawdown close to the whole net gain.

## Live PP and Collar rule set (TDL-6)

Source of truth, read from code on 2026-10-11: `src/strategy/exit_signals.py` (`evaluate_pp` line 448 onward, `evaluate_crash_monetize`, `evaluate_cc`), `src/strategy/pp_overlay_v1.py`,
`src/strategy/collar_overlay_v1.py`, `src/strategy/collar_entry.py`, `src/strategy/reentry_mixin.py`, `scripts/strategies/three_track/paper_3track_overlay_entry.py` (`auto_pp_bootstrap`, line 714) and
`scripts/lookup/find_strike_by_delta.py`. Archived specs compared: `docs/archive/plan/paper_3track_overlay.md` (PP) and `docs/archive/plan/council-refactor/stories_collar.md` (Collar). The code is the
authority. Both strategies run under `strategy_name = paper_nifty_overlay`, with leg roles `overlay_pp`, `overlay_collar_put` and `overlay_collar_call`.

### PP (`overlay_pp`, long put)

<!-- lint-ignore-length -->
| Rule | Live value (source) | Archived spec | Status |
|---|---|---|---|
<!-- lint-ignore-length -->
| Put strike | Delta ladder 0.20, then 0.25, then 0.15; each rung filters |delta| to target +/- 0.02, ranks, applies the liquidity gate, first rung with a survivor wins (`paper_3track_overlay_entry.py:823-842`; `find_strike_by_delta.py:87`) | 8-10% OTM band, 9% target (`PP_OTM_*`) | DIFFERS. `PP_OTM_*` still sit in `constants.py:46-48` and `paper_3track_overlay.py`; the auto path does not use them (inference: the manual path may) |
| Expiry | Nearest monthly with DTE >= 14, no upper bound (`paper_3track_overlay_entry.py:766`; `lookup.get_expiry_candidates`) | quarterly, DTE 50 | DIFFERS |
<!-- lint-ignore-length -->
| IVR gate | Block when trailing 252-day IVR > 0.60 (`pp_overlay_v1.py:59,113`; `paper_3track_overlay_entry.py:133`). In `auto_pp_bootstrap` the gate is log-only by default (`log_only_gates=True`), so the routine roll proceeds regardless | not in spec | NEW. Effective entry gate is none |
| CRASH_MONETIZE | Put delta <= -0.80 OR mark >= 5.0 x entry debit; ACTION, closes the put (`exit_signals.py:422-423`) | not in spec | NEW |
<!-- lint-ignore-length -->
| ROLL_ELIGIBLE | DTE <= 5; ACTION; the same-day reopen is `auto_pp_bootstrap`, gated on `_PP_ROLL_DTE_THRESHOLD = 5` (`exit_signals.py:484`; `paper_3track_overlay_entry.py:138`) | `OVERLAY_ROLL_DTE = 5` | MATCH |
<!-- lint-ignore-length -->
| Re-entry after MONETIZE_PP | Mixin gate: DTE >= 14, then IVR <= 0.60 (PP override) (`pp_overlay_v1.py:290-296`; `reentry_mixin.py:179-182`). ROLL_PP deliberately skips the mixin (`pp_overlay_v1.py:278-288`) | not in spec | NEW |
| Profit target, loss stop, delta stop | None. A long put has no premium stop and no time stop | not in spec | n/a |
| Lot size | 65 (`constants.py`, `LOT_SIZE`) | n/a | MATCH |

### Collar (`overlay_collar_call` short, `overlay_collar_put` long)

<!-- lint-ignore-length -->
| Rule | Live value (source) | Archived spec | Status |
|---|---|---|---|
| Call strike | Ladder 0.18, 0.20, 0.15, band +/- 0.02 (`collar_entry.py:57`, `_find_candidates_for_ladder` line 82) | not in spec | NEW |
| Put strike | Ladder 0.20, 0.25, 0.15, band +/- 0.02 (`collar_entry.py:58`) | not in spec | NEW |
| Pair choice | Cross-product of call and put candidates, pick min abs(net premium) = call mid minus put mid (`collar_entry.py:116`, `_select_best_combo`) | not in spec | NEW |
| Expiry | Nearest monthly, DTE >= 14. If the position being closed had DTE <= 5, force the next month (`collar_entry.py:148`) | not in spec | NEW |
| Entry gates | DTE >= 14 and IVR >= 0.25, both hard; failure raises `CollarEntrySelectionError` and the collar stays flat (`collar_entry.py:60-61,185,298`) | not in spec | NEW |
| Profit target | Call mark <= 30% of call credit and credit >= 15 (via `evaluate_cc`, `exit_signals.py:310`); closes BOTH legs | 30% (stories_collar line 24) | MATCH |
| Loss stop | Call mark >= 2.5 x credit (`exit_signals.py:290-291,323`); closes both legs | 2.5x | MATCH |
| Delta stop | Call delta >= 0.55 (`exit_signals.py:338`); closes both. Delta warn at 0.45 is WARN only | 0.55 / 0.45 | MATCH |
| DTE | Call DTE <= 5 is an ACTION auto-close (`exit_signals.py:374`) | WARN only (stories_collar line 40) | DIFFERS (EC-5, 2026-08-02) |
| Time stop (21 days) | Removed from the collar action list (`collar_overlay_v1.py:35-42`) | `TIME_STOP` at 21 days (line 38) | DIFFERS |
| Put leg exit | Only CRASH_MONETIZE: delta <= -0.80 or mark >= 5 x debit (`collar_overlay_v1.py:249`). No other put-side exit | `[]` for the put (line 347) | DIFFERS |
<!-- lint-ignore-length -->
| Terminal action | Any winning ACTION closes both legs atomically, then reselects and opens a fresh pair (`CLOSE_AND_REENTER_COLLAR`). Priority: CRASH_MONETIZE, LOSS_STOP, PROFIT_TARGET, DTE_REVIEW, DELTA_STOP (`collar_overlay_v1.py:43-49`) | CLOSE_COLLAR, re-entry only after PROFIT_TARGET and TIME_STOP | DIFFERS |
| Liquidity gate | `_apply_liquidity_gate` on every candidate (`strike_selector.py:151`); `SPREAD_PCT_MAX = 3.0` (`constants.py:86`) | max(put, call spread) <= 3.0 | MATCH |

### Expressible on Tradetron, and gaps

Nothing below was tested on the platform; "expressible" is from the CC v2 template and `docs/reference/tradetron.md`, and TDL-7's `tt_validate_markdown` is what confirms it.

- **Expressible, reuse from CC v2:** nearest monthly with at least 14 DTE (two sets, flat gate); the DTE <= 5 close; the call-side exits for the Collar (30% target with credit floor 15, 2.5x loss,
  0.55 delta) via per-leg Entry anchors; one-lot sizing.
- **Expressible with care:** the PP CRASH_MONETIZE exit (mark >= 5x entry price through the Entry price keywords, as the 2.5x loss stop does for CC) and a put delta <= -0.80 read through `Delta(Traded
  Instrument Name('Entry', ...))`. Confirm the put's delta sign and units first (reference doc table note 3).
- **GAP, approximate:** the delta ladder (0.20 then 0.25 then 0.15 for puts, 0.18 then 0.20 then 0.15 for calls) has no if/else keyword. Use the first rung only (put 0.20, call 0.18) with `Find
  Strike(..., 'Delta', ...)`, which picks the nearest strike, so the +/- 0.02 band is not enforced. This is the likely source of strike differences against paper, as it was for CC.
- **GAP:** the Collar's min abs(net premium) pair search across a call by put cross-product; the liquidity gate (3% spread, OI ranking), because the BT engine has no bid-ask (inference, not looked
  up); the IVR gates (PP > 0.60 effectively unenforced, Collar >= 0.25), which need a trailing 252-day IVR of VIX that Tradetron may not provide (UNKNOWN, check in TDL-7). Omitting the Collar's IVR
  gate makes the template enter in low-vol periods where paper would stay flat; state this in TDL-8.
- **GAP, structural for the Collar:** closing both legs when either leg's rule fires, then reopening a fresh pair the same minute. A Universal Exit over both legs followed by the flat gate should do
  it (inference); the pair must also respect the margin-safe leg order (long put first).
- **Not modelled by Tradetron at all:** the NiftyBees stock leg, margin, the manual-close entries in the paper ledger.

## Paper PP and Collar ground truth (TDL-6)

Source: `paper_trades`, `strategy_name = paper_nifty_overlay`, roles `overlay_pp`, `overlay_collar_put`, `overlay_collar_call`, queried 2026-10-11 and aggregated in SQL. All quantities 65. Gross =
sell minus buy per unit times quantity; the ledger holds no charges. Window 2026-08-11 to 2026-10-11.

<!-- lint-ignore-length -->
| Leg | Instrument | Entry | Exit | Entry px | Exit px | Ratio | Gross | Exit type (inference) |
|---|---|---|---|---|---|---|---|---|
| PP | NSE_FO\|61604 (24000 PE, exp 2026-08-25) | 2026-08-11 | 2026-08-24 | 58.85 | 4.85 | 0.08 | -3,510 | manual close, BUG-031 B031.4 |
| PP | NSE_FO\|74009 (23700 PE, exp 2026-09-29) | 2026-08-20, 08-21 (2 lots) | 2026-08-24 | 93.00 avg | 83.85 | 0.90 | -1,190 | manual close, BUG-031 B031.4 |
| PP | NSE_FO\|74046 (23800 PE, exp 2026-09-29) | 2026-08-24 | 2026-08-24 | 97.375 | 99.85 | 1.03 | +161 | manual close, same day |
| PP | NSE_FO\|74004 (23600 PE, exp 2026-09-29) | 2026-08-25 | 2026-09-16 | 88.625 | 448.70 | 5.06 | +23,405 | `apply_action`, ratio above 5x so CRASH_MONETIZE |
| PP | NSE_FO\|51331 (22500 PE, exp 2026-10-27) | 2026-09-16 | open | 123.975 | n/a | n/a | open | n/a |
| Collar put | NSE_FO\|73994 (23500 PE, exp 2026-09-29) | 2026-08-12 | 2026-09-29 | 91.825 | 783.80 | 8.54 | +44,978 | expiry settlement at intrinsic, NIFTY close 22,716.20 |
| Collar put | NSE_FO\|51299 (21800 PE, exp 2026-10-27) | 2026-09-30 | open | 73.575 | n/a | n/a | open | n/a |
| Collar call | NSE_FO\|51368 (23400 CE, exp 2026-10-27) | 2026-09-30 | open | 69.20 (sell) | n/a | n/a | open | n/a |

Sample sizes. PP: 4 completed round trips, 1 open; 3 of the 4 closes are manual (BUG-031) and one is a rule exit. Collar put: 1 completed leg (settlement), 1 open. **Collar call: one row.** Before
2026-09-30 the ledger has no `overlay_collar_call`; the call half of the collar rode the `overlay_cc` role (for example 2026-08-12 25400 CE, id 177, same date as the first collar put). That is an
inference from the dates, and it means a clean two-leg collar cycle exists only from 2026-09-30 (0 completed cycles). The four PP and one collar-put closes are all long puts that gained in the same
2026-09 NIFTY fall (close 22,716.20 on 2026-09-29), so they are one regime and are not independent. Gross PP closed: +18,866 on 4 trips; collar put closed: +44,978 on 1 leg. Neither says anything
about edge at these counts.

What the DB does not hold: delta at entry or exit (`ivr_at_entry` is empty for all of these rows), the trigger behind each close (only the note "close via apply_action" or "manual close"), the chain
spot at entry (so strike distance cannot be recomputed from the ledger alone), charges, and which collar put belongs to which `overlay_cc` call. Reconciling a Tradetron run against this in TDL-8
therefore compares entry dates, strikes, expiry, fill prices and gross P&L only, on an overlap of about two months.

## PP and Collar templates (TDL-7)

Specs: `template_pp.md` and `template_collar.md` in this folder (CC v2 structure: two sets for the nearest-monthly-with-14-DTE rule, per-set exits, an open-position flat gate; one lot; Market Price;
exit shorts first). Both were built from the TDL-6 rule tables and validated with `tt_validate_markdown` (mode create) with zero errors on the first pass. Created 2026-10-11, not deployed.

<!-- lint-ignore-length -->
| Template | Tradetron id | edit_url | Validate | Pre-flight (`tt_check_backtestability`, 2021-10-01 to 2026-10-09) | Verdict |
|---|---|---|---|---|---|
<!-- lint-ignore-length -->
| NS PP Long Put POC v1 | 999135746 | https://tradetron.tech/strategies/999135746/edit | 0 errors, 2 warnings (UNBOUNDED_DAILY_REENTRY, one per set), 1 notice (blank Universal Exit) | `backtestable`, confidence high, no blockers, no warnings, no checks skipped; NFO / NIFTY 50 data and window coverage ran; recommended run type positional (strong) | GO |
<!-- lint-ignore-length -->
| NS Collar POC v1 | 999135750 | https://tradetron.tech/strategies/999135750/edit | 0 errors, 4 warnings (REPAIR_ONCE_PATTERN_LIKELY and UNBOUNDED_DAILY_REENTRY, one each per set), 1 notice | `backtestable`, confidence high, no blockers, no warnings, no checks skipped; same coverage result; positional (strong) | GO |

Read-back with `tt_get_strategy`: PP has 3 sets (two working sets plus Tradetron's universal set), 9 conditions and 2 legs (one long PE per working set); Collar has 3 sets, 9 conditions and 4 legs
(long PE and short CE per working set). Both match the specs. Price quote for a run on either template, from `tt_backtest_workbench`: 1 credit, amount 20, affordable, max 60 months, no run yet. No
spend was made in this task.

Warnings, accepted on purpose. UNBOUNDED_DAILY_REENTRY: the live code re-enters the same day after a close (the CC v2 template behaves the same), so no re-entry cap was added.
REPAIR_ONCE_PATTERN_LIKELY on the Collar: the validator expects a per-leg "exit the survivor at cost" shape; the live Collar closes both legs together on any trigger, which is what a set-level Exit
does.

Deviations from live code that TDL-8 must carry into the reconciliation (all inferences about effect, not measured):

- Strike selection uses only the first ladder rung (put delta -0.20, call delta 0.18) with `Find Strike(..., 'delta', ..., 'any')`, which takes the nearest strike with no distance cap and no +/- 0.02
  band, no liquidity or spread gate, and no fallback rungs (0.25 then 0.15 for puts; 0.20 then 0.15 for calls). Expect strike differences against paper, as with CC.
- No IVR gate on either template. Live PP has one (> 0.60) but it is log-only in `auto_pp_bootstrap`, so effectively none; the live Collar blocks entry when IVR < 0.25, which the template does not, so
  it will enter in low-vol stretches where paper stayed flat. Whether Tradetron exposes an IVR input was not looked up.
- The Collar's pair search (min abs net premium across call x put candidates) is replaced by two fixed delta targets.
- Put delta sign: `Find Strike` takes a negative target for a PE (`Number(-0.20)`) and the crash exit tests `Delta(put) <= -0.80`, per the keyword documentation; it is not yet seen in a fill.
- Exit on the Collar is one OR group per set over the call-side rules (30% of credit with credit >= 15, 2.5x, delta >= 0.55, DTE <= 5) and the put-side crash rule (5x debit, delta <= -0.80). The live
  `_REENTRY_ACTION_PRIORITY` ordering is irrelevant here because every trigger has the same result (close both, reopen).
- PP rolls by closing at DTE <= 5 and letting the next set reopen once the nearest monthly has >= 14 DTE; live code reopens the same day through `auto_pp_bootstrap`. Same-day reopen is expected from
  the flat gate, not observed.
- Not modelled on either: the NiftyBees stock leg, margin, and the paper ledger's manual closes (BUG-031).

One authoring lesson for this platform (kept here, not in the reference doc yet): `tt_check_backtestability` returned verdict `unknown` (confidence low, `data_coverage` and `coverage_window` skipped)
when legs carried no numeric instrument id, and `backtestable` (high) once `instrument: 1855` from the read-back was on each leg. Pass the id, or pre-flight the read-back body.

## PP and Collar runs (TDL-8)

Both runs: window 2021-10-11 to 2026-10-01, `positional`, `Open` fill, 1-minute candles, price ₹20 each (quote re-read from `tt_backtest_workbench` the same session; Animesh approved ₹40 in-session).
Wallet read ₹160 before and ₹120 after both runs; the earlier "₹140 after TDL-5" note was not seen again in this session, so the TDL-5 charge is unreconciled (inference: the balance display lagged).
Both reports carry the same high-severity `COVERAGE_PARTIAL` caveat as CC (4 sessions absent, 5 skipped), no Sharpe, Sortino or Calmar, no MAE or MFE.

<!-- lint-ignore-length -->
| Run | Template | Job id / bt_id | Report |
|---|---|---|---|
| PP | 999135746 | `ttbt-999113502261011` | https://tradetron.tech/bt/view/6c45f17a74c12a9e5cde13d9e0e18584 |
| Collar | 999135750 | `ttbt-999113506261011` | https://tradetron.tech/bt/view/58d20899e50cd70eb268eb00e54b8d3b |

Headline (report figures, 1 lot, nominal capital ₹100,000, round-trip count beside each):

<!-- lint-ignore-length -->
| Figure | PP (69 round trips) | Collar (391 round trips, 196 cycles of two legs) |
|---|---|---|
| Gross P&L | -47,528 | +42,516.50 |
| Costs | 1,499 | 6,521 |
| Net P&L | -49,027 | +35,996 |
| Win rate (trips) | 18.8% | 55.2% |
| Avg win / avg loss | 26,402 / -6,978 | 4,572 / -5,400 |
| Profit factor | 0.88 | 1.04 |
| Max drawdown (net, of nominal capital) | 136,382 (136%), not recovered | 134,736 (135%), not recovered |
| Worst rolling 6 months | n/a in report | -103,269, ending 2025-08-18 |
| Median hold | 28 days | 8 days |

Collar trips are leg-level (one put plus one call per cycle). Per leg: PE 194 trips, gross +15,021, win rate 39%; CE 197 trips, gross +27,495, win rate 71%. Per set: Set 1 lost 33,092 over 221 round
trips, Set 2 made 69,088 (report arithmetic, not a re-run). PP per set: Set 2 lost 31,189 over 60 trips; Set 1 has 9 trips, too thin to read. The drawdown exceeds the nominal capital on both runs, so
₹100,000 is not a workable base for either; read the shape, not the percentage.

PP exit mix, 69 trips (exit type is **inference** from the exit-price ratio; the report labels every exit "Take-profit", which is a generic tag, not a reason): 8 trips with ratio at or above 5.0 (the
`CRASH_MONETIZE` mark rule), gross +263,921; 56 with ratio below 1 (DTE <= 5 rolls that expire the premium); 5 between 1 and 5. The other 61 trips sum to -311,451. So the whole PP result is eight
events carrying a 61-trip bleed: win rate 19%, and the 8 crash exits are the only reason the run is not worse than -311k. The 8 events are in 5 regimes at most (Nov 2021, May 2022, Mar 2023, Jun 2024,
Apr 2025, Mar 2026, Sep 2026 by month), not independent samples. Median hold 27 days; PP trips are at one lot of 65. PP round trips saved in `pp_long_window_cycles.md` in this folder (69 rows; gross
sums to -47,530 against the report's -47,528 by rounding). The Collar's 391 paired round trips were not saved (about 100k tokens to page); the aggregates above are the report's, and the post-2026-08
fills below were read from the fill list.

### Reconciliation against paper (overlap 2026-08-11 onward)

Overlap sample sizes: PP 4 Tradetron trips (3 rule exits and the window-end close), against 5 paper PP rows (4 closed, 3 of them manual closes, BUG-031). Collar 7 Tradetron cycles, against 1 completed
paper collar put (settlement) and 1 open pair. Neither is a sample that supports a claim.

<!-- lint-ignore-length -->
| Date | Tradetron PP | Paper PP | Match |
|---|---|---|---|
| 2026-08-20 | buy 23700 PE exp 2026-09-29 at 97.40 | buy 23700 PE exp 2026-09-29 on 08-20 and 08-21, avg 93.00 (2 lots) | strike and expiry match, entry 4.40 higher, 1 lot against 2 |
| 2026-09-11 | exit at 487.30, ratio 5.00, gross +25,343 | none; paper held 23600 PE (bought 08-25 at 88.625) | different strike, different date |
<!-- lint-ignore-length -->
| 2026-09-16 | none; Tradetron already flat after 09-11 and reopened 22750 PE the same day | paper `apply_action` closed 23600 PE at 448.70, ratio 5.06, gross +23,405 (CRASH_MONETIZE) | exit rule the same (5x mark), dates five days apart, strike 100 points apart |
<!-- lint-ignore-length -->
| 2026-09-16 / 09-24 | 22750 PE exp 09-29 bought 09-11, rolled at DTE <= 5 on 09-24 (ratio 0.12, -4,192); next 22650 PE exp 2026-10-27 at 99.65 | 22500 PE exp 2026-10-27 at 123.975, still open | same expiry on the open leg, strike 150 lower on paper |
| 2026-10-01 | 22650 PE exits at 499.00, ratio 5.01, +25,958; opens 21550 PE at 107.75 and force-closes it at window end, -2,278 | open | Tradetron's 5x exit fires on a day paper had not closed |

The PP template reproduces paper's **mechanics** (the same nearest-monthly, DTE >= 14 expiry and a CRASH_MONETIZE 5x close that fires on the same fall) and the 08-20 strike and expiry exactly. It does
not reproduce entry strikes in general, as expected from the first-rung-only delta target (no +/- 0.02 band, no fallback rungs). Strike differences of 100 to 150 points on two of three comparable
entries.

<!-- lint-ignore-length -->
| Date | Tradetron Collar cycle (put long, call short) | Paper |
|---|---|---|
<!-- lint-ignore-length -->
| 2026-08-12 | 23750 PE at 118.00 and 25500 CE at 79.15, exp 09-29; closed 08-19, gross +6,009 | 23500 PE exp 09-29 at 91.825 (held to settlement, +44,978 gross); call half sat in role `overlay_cc` (25400 CE) |
| 2026-08-19 to 09-22 | five further cycles, each closed by a trigger within 4 to 14 days, gross +1,710, +10,946, +8,151, -1,518, +16,409 | paper held the 08-12 put unchanged to 09-29 |
| 2026-09-29 | 22050 PE at 109.95 and 23550 CE at 72.00 exp 10-27, closed at window end 10-01, +4,973 | 09-30: 21800 PE at 73.575 and 23400 CE at 69.20 exp 10-27, open |

Seven Tradetron cycles over seven weeks produce gross +46,680 on overlap fills (computed from the fill list, ties to the report's window-end 4,972.50); paper made +44,978 on one long put leg in the
same weeks with the call half booked elsewhere, so the two are not like for like. Tradetron re-cuts the pair about weekly because any one of the OR-ed triggers closes both legs and the flat gate
reopens it; paper holds until its own rule fires. That difference (a template-structure effect, inference) is what drives the 391-trip count against paper's near-absent cycles. Strike deltas on the
first Tradetron collar cycle (PE 23750 at 24,374.7 spot, 1.7% OTM; CE 25500, 4.6% OTM) differ from paper's chosen pair by 250 and 100 points. The 09-29 and 09-30 entries are one trading day apart,
22050 against 21800 for the put and 23550 against 23400 for the call.

### Verdicts, TDL-8 part 1

- **PP: reproduces partially.** Expiry rule, DTE roll and CRASH_MONETIZE exit are reproduced; strikes match once of three comparable entries. Over five years the run shows a 19% win rate and a net
  loss (-49,027 net on 69 trips) carried only by eight 5x events; paper's 4 closed trips cannot show this. Not an edge claim.
- **Collar: reproduces partially at best.** The pair, expiry and call-side exit set are expressed, but the template re-cuts weekly and enters in low-vol periods without the IVR gate, which live code
  would refuse (not measured per cycle). 391 trips (196 cycles) is above the 30-trip flag; the result is +35,996 net with a drawdown over the nominal capital and an uneven set split. A screen of
  viability, not an edge.
- Tradetron's `Delta` sign convention for puts was seen working: the PP 5x exit fired and the Collar crash rule is untested in isolation (the Collar report has no exit-reason column, `has_exit_reason`
  false), so whether the delta <= -0.80 branch fired cannot be told. Platform fact for the reference doc: PP's report names an exit, the Collar's does not.

### NiftyBees baseline and the combined table

The `tt_backtest_idea` Playground cannot hold for the window (`hold_days` is capped at 1 to 365, and its entry needs a crossing that never fired), so the baseline is a hand-built template: NS
NiftyBees Hold POC v1, id 999136810, one buy of 65 NIFTYBEES shares at 10:00 with a flat gate and a never-true exit. It validated with 0 errors (warnings accepted on purpose: UE placement on a single
set, unbounded re-entry that cannot fire because the position never closes) and pre-flighted `backtestable`, confidence high, no checks skipped. Run: job `ttbt-999113798261011`, same window and
settings, ₹20 (Animesh chose this route in-session; wallet ₹120 before, then the charge). Report: https://tradetron.tech/bt/view/684b2fe9c20efc5bbc52d0f424faa860.

Measured: **the first fill is 2022-01-03, not 2021-10-11.** The NiftyBees store has a 368-day hole from 2020-12-31 to 2022-01-03 (shown by the Playground preview), so the buy waited 12 weeks. One buy
at 189.19 per share (turnover 12,297.35) and one window-end close at 257.25 (16,721.25): gross +4,423.90, net +4,369.81 (costs 54.09), price return +35.97%. The report's own `COVERAGE_PARTIAL` (4
sessions absent, 5 skipped) applies too, and the Playground preview showed eight further holes from 2022-12 to 2024-06 (15 to 180 days each) that this run's single position is blind to. One round
trip: no statistic below it means anything. The report holds only the two end marks (series length 2), so a NiftyBees max drawdown, worst rolling 6 months and CAGR are **not obtainable** from the run;
the overlay series are also realized-basis (round trips booked on exit day), so a daily combined equity curve cannot be built from them either. The table below therefore uses end-to-end figures only.

**Sizing mismatch, stated plainly.** The spec asked for the NiftyBees position sized to the overlay lot count. The run holds 65 shares (about ₹12,300), which is about 1% of the notional of the one
NIFTY lot (65 units at the 2021-10-11 fill level of 17,966.2, about ₹1,167,800) every overlay run trades. So the rupee figures are not on a matching base; compare the percent column, which is a
fixed-notional approximation (overlay gross divided by ₹1,167,800, one notional for all five years, while NIFTY itself rose to about 22,400).

<!-- lint-ignore-length -->
| Book (2021-10-11 to 2026-10-01 unless noted) | Round trips | Gross P&L (Rs) | Net P&L (Rs) | Gross as % of one-lot notional | Max drawdown (report, net, Rs) | Worst rolling 6M |
|---|---|---|---|---|---|---|
| NiftyBees buy-and-hold, 65 shares, from 2022-01-03 | 1 | +4,424 | +4,370 | +35.97% (price return) | not obtainable | not obtainable |
| CC, 1 lot (TDL-5, `ttbt-999110942261010`) | 196 | +52,878 | +50,803 | +4.53% | 43,375 | not read |
| PP, 1 lot (`ttbt-999113502261011`) | 69 | -47,528 | -49,027 | -4.07% | 136,382 | not read |
| Collar, 1 lot (`ttbt-999113506261011`) | 391 | +42,517 | +35,996 | +3.64% | 134,736 | -103,269 (to 2025-08-18) |

Hold plus overlay, percent basis only (inference arithmetic, not runs): NiftyBees +35.97% plus CC +4.53% is about +40.5%; plus PP -4.07% is about +31.9%; plus Collar +3.64% is about +39.6%. Overlay
P&L counts only while a call or put is open, the overlays were run on different dates in the window than the baseline's 2022-01-03 start, and no row is an edge claim: the baseline has 1 round trip and
the PP, Collar and CC rows rest on 69, 391 and 196 round trips of which a few events carry the PP and the Collar's set 2. What the table does show: against a five-year hold of the underlying ETF, each
overlay's gross over the same window is a single-digit percent of one lot's notional, and PP is a net cost. The Collar's drawdown (over the whole nominal capital) is on the options legs alone, with no
stock leg modelled to offset it.

### Verdicts, TDL-8 part 2

- **NiftyBees baseline: obtained, with a late start and no drawdown series.** The engine's data hole starts the position 12 weeks late, and the report keeps no marks between entry and exit. Useful as
  a price-return anchor (+35.97%), not as a drawdown comparator.
- **TDL-8 done condition:** a finished run per template (PP, Collar, NiftyBees) is logged, PP and Collar are reconciled against paper on the overlap with sample sizes (4 PP trips, 7 Collar cycles),
  and the combined table is above, with its limits.
