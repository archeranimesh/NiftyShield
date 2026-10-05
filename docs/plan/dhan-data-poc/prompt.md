
# Dhan data API POC — prompt

> Buy one month of Dhan's historical options data as a proof of concept, check which strikes and expiries it covers, validate it against the data we already hold, and decide whether a full-year
> purchase is worth it.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Animesh (2026-10-05) will buy the Dhan Data API for a one-month POC before committing to a year. The purchase comes with a historical dataset; what it covers (strikes, expiries, fields) is unknown
until it is inspected. The story answers whether that dataset is good enough to backtest and validate the paper strategies (CC, PP, Collar, IC) and to settle the contract questions below. It sits
beside `docs/plan/tradetron-delta-and-long-window/`, whose TDL-4 asks for a comparator and TDL-10 for the data-purchase verdict; this story is the paid option that verdict weighs. The two stories
cross-reference each other and neither edits the other's files.

Two things the data should help settle, both found on 2026-10-05 from the stored Upstox chain (`data/historical/option_chain/intraday/`, one 09:00 file per day sampled; the flip date is unknown):

- **Old-data validation.** Our stored Upstox chain Parquet (from 2026-06-01), the bhavcopy, and the paper trades (from 2026-08-12) have never been checked against an independent source. TDL-1 showed
  the Tradetron strike picks sit at Upstox delta 0.139 to 0.152, so the Upstox side looked sane at six points; that is not a validation.
- **The Dec 2026 and other far-dated contract behaviour.** Upstox's Dec 29 2026 chain had zero delta on every row through 2026-09-21 and 160 to 180 nonzero rows by 2026-10-01. The "yearly" bucket
  pointed to 2027-06-29 in early July and to 2026-12-29 from 2026-07-24. `docs/plan/greeks-bs-fallback/` was written against the zero-Greeks state; it may have changed, and an independent delta source
  in the zero window would tell us what the fallback should target. The cause of the flip is an inference (days to expiry, or a wider chain), not established.

## Scope guard

In scope: reading Dhan's data API documentation; recording the plan, price and dataset shape; a small sample pull into `scratch/` per `SCRATCH.md`; a coverage inventory against the strikes the
strategies trade; read-only comparison against stored Upstox chain, bhavcopy and paper tables (`DB_REGISTRY.md` first); findings. A reusable fetch or comparison becomes a tested CLI in `scripts/dev/`
only if it will be re-run, and only after the SOLID triggers in `docs/refactor/design-principles.md` and the prior-art audit in `docs/refactor/code-deduplication-and-taxonomy.md` (check `src/dhan/`
first; it is the holdings and intraday reader, not a data-API client).

Out of scope: any change to `src/` unless DDP-6 recommends one and Animesh approves it as a follow-up story; editing `greeks-bs-fallback` or the Tradetron story's files; any live order path; a
full-year purchase (DDP-6 only recommends). Never record credentials, API tokens, client ids or payment links in any file.

Spend rule: Animesh buys the POC himself (DDP-2); no task buys or subscribes on his behalf. Record the plan name and the price he states, never an estimate.

## Design review

No new module, class or seam in the planned tasks. If DDP-3 or DDP-4 yields a reusable CLI, record the SOLID-trigger and prior-art outcome here before it is written.

## Session-start load hints

Always: `CONTEXT.md`, `tasks.md`, the current task in `stories.md`, `DB_REGISTRY.md` before any `portfolio.sqlite` query (aggregate in SQL, named columns, `LIMIT 10`), `REFERENCES.md` (expiry rules:
monthly expiry moved from Thursday to Tuesday in April 2026; Dec 2026 monthly is 2026-12-29). Per task:

- DDP-1: Dhan's public data-API docs (web); `src/dhan/CLAUDE.md` for what the repo already uses.
- DDP-3, DDP-4: the stored chain under `data/historical/option_chain/intraday/` (columns `snapshot_ts`, `expiry_date`, `strike`, `option_type`, `spot`, `ltp`, `bid`, `ask`, `oi`, `volume`, `iv`,
  `delta`, `gamma`, `theta`, `vega`), `src/backtest/` via the graph (`ChainReader`, bhavcopy loader), and `docs/archive/plan/tradetron-cc-backtest-poc/findings.md`.
- DDP-5: `docs/plan/greeks-bs-fallback/prompt.md` and `REFERENCES.md` (yearly-expiry Greeks note); read only.

## Task overview

- **DDP-1** — Free docs read: what the Dhan data API and its historical dataset offer, and the price; pass or fail against the POC criteria before Animesh pays.
- **DDP-2** — Animesh buys the POC; record the plan, price and access method (no secrets).
- **DDP-3** — Coverage inventory on the real dataset: expiries, strike range per expiry, fields (delta, IV, OI), date range and candle size, against the strikes each strategy trades.
- **DDP-4** — Old-data validation: Dhan against the stored Upstox chain, bhavcopy and paper trades on overlapping dates.
- **DDP-5** — Contract questions: Dec 2026 and Jun 2027 zero-Greeks behaviour, the yearly-bucket relabelling, and what Dhan shows in the zero window.
- **DDP-6** — Verdict on the full-year purchase, and what feeds back into the Tradetron story's TDL-4 and TDL-10.

POC pass criteria (set before buying; DDP-1 and DDP-3 test them): the dataset covers the expiries and the 0.12 to 0.18 delta strikes the CC, PP, Collar and IC rules pick; it reaches back past April
2026 so both expiry regimes appear; it carries delta or IV (a model delta from IV is acceptable only if stated as such); and on overlapping dates it agrees with what we hold.

Where results go: run facts and tables in `findings.md` here (no task checkboxes). The purchase decision and any rule change go to `DECISIONS.md` at DDP-6. Status in `docs/plan/README.md` and
`TODOS.md` per Step 5a. Record only what was measured; mark inferences as inferences.

## Definition of done

DDP-1 to DDP-6 ticked with SHAs. `findings.md` holds the docs read, the coverage inventory, the validation tables with sample sizes, the contract findings, and a plain answer on the full-year
purchase. The story is archived per §Conventions *Completion → archive*.

## Perspectives not covered

A one-month sample cannot show seasonal or regime variety, so it can pass coverage and agreement tests and still say nothing about a year of data; the verdict states that limit. Agreement with Upstox
on one month shows the two sources are consistent, not that either is right. A vendor delta may be a computed model value, not an exchange field, so a match shows methodology agreement and not ground
truth. Fill quality, bid-ask and liquidity are only as good as the quotes Dhan stores; if it holds OHLC without bid and ask, it cannot answer fill-quality questions either.
