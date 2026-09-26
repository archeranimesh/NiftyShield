# Council Question 8 — Nifty Long Instrument Comparison: ETF vs Futures vs ITM Option as Base for Protection Strategy Overlay

## Why This Is Council-Worthy

1. **Load-bearing and costly to reverse.** The choice of base "Nifty long" instrument is the
   foundation of the entire 3-track paper trading and backtesting framework. It determines:
   (a) which protection strategies are structurally available on each track (covered calls
   require a deliverable underlying — futures cannot support them cleanly; synthetics create
   a pre-existing short put that interferes with CSP overlay); (b) the backtest infrastructure
   needed (futures require roll-cost modelling, ITM calls require time-value-decay modelling);
   (c) capital efficiency and tax outcomes that are structurally different across instruments.
   Getting this wrong means 6+ months of paper trading on a suboptimal base instrument.

2. **Three defensible approaches with materially different outcomes.** NiftyBees ETF: full
   capital deployment (₹15-16L), pledgeable, LTCG-taxed at 12.5% above ₹1.25L threshold,
   no roll cost, perfect collateral for all three overlay strategies. Nifty Futures: margin-
   only capital (~₹1.2-1.5L SPAN), rest of capital earns risk-free return, taxed as
   non-speculative business income at applicable slab (currently 30% for most retail traders),
   monthly roll cost embeds cost-of-carry (~0.35-0.60% per roll based on futures premium
   to spot). ITM Call option: partial capital deployment (~₹2-3L for deep ITM call at
   delta ~0.90), no roll cost per se but theta decay is a structural drag (~₹100-200/lot/day
   at 30 DTE for a 2000-point ITM call), cannot be pledged as futures-equivalent collateral.
   These three have structurally different cost structures, strategy overlay constraints, and
   tax treatment — not cosmetically different.

3. **Spans multiple disciplines simultaneously.** Options microstructure (how does buying a
   protective put on a deep ITM long call effectively create a bull call spread — the combined
   Greeks are different from a simple "long + protective put" on futures/ETF); capital markets
   theory (cost-of-carry, basis risk, roll yield on futures); Indian tax law (non-speculative
   business income vs STCG vs LTCG — the after-tax comparison materially changes which
   instrument is optimal); NSE-specific constraints (lot size changes over history affect
   futures and options equivalently but ETF position sizing is continuous); and collateral
   efficiency (NiftyBees is pledgeable as margin collateral — running futures on top
   consumes additional SPAN margin without offsetting the collateral benefit).

---

## Background Context

The operator (Animesh) currently holds:
- NiftyBees ETF (~5,725 units, ₹15.5L, pledgeable as margin collateral)
- Active paper strategy: `paper_csp_nifty_v1` (short Nifty put, 25-delta, monthly)

The proposed new research framework runs 3 separate comparison tracks in paper trading,
each representing a different way to hold "1 lot equivalent Nifty long exposure":
- **Track A:** Long 1 lot equivalent NiftyBees ETF (~5,725 units at ₹271/unit ≈ ₹15.5L)
- **Track B:** Long 1 lot Nifty Futures (near-month, always rolled; margin ~₹1.2-1.5L)
- **Track C:** Long 1 lot Nifty via ITM option (structure to be determined by council)

On top of each track, test these overlay strategies:
1. Protective puts (buy Nifty OTM put — standard hedge)
2. Covered calls (sell Nifty OTM call — yield extraction from the long position)
3. CSP (short Nifty put — in correlation with the existing `paper_csp_nifty_v1` strategy)
4. Council-suggested additional protection/yield structures

The goal: a daily P&L report covering each track's base position MTM plus overlay strategy
P&L, so the three tracks can be directly compared over the same paper window.

---

## Command

```bash
python scripts/ask_council.py \
    --topic nifty-long-instrument-comparison-protection \
    --template strategy_parameters \
    --context docs/strategies/niftyshield_integrated_v1.md \
    --context docs/strategies/csp_nifty_v1.md \
    --context docs/plan/signals-eval-core/stories.md \
    --context MISSION.md \
    --context REFERENCES.md \
    --question "This question designs a 3-track paper trading and backtesting comparison framework for Nifty long exposure combined with protection strategies. The operator already holds NiftyBees ETF (~5,725 units, ₹15.5L, pledgeable as margin collateral), and runs CSP paper trading on Nifty monthly puts. The new framework runs 3 separate tracks simultaneously in paper trading: Track A = Long NiftyBees ETF (1 lot equivalent, ~₹15.5L physical holding), Track B = Long Nifty Futures (1 lot, near-month, rolled monthly), Track C = Long Nifty via ITM option (structure TBD by council). On top of each track: protective puts (buy OTM Nifty put), covered calls (sell OTM Nifty call), CSP (short Nifty put at ~25 delta in correlation with existing paper strategy), and any additional structures the council recommends. FOUR QUESTIONS FOR THE COUNCIL: (1) ITM OPTION STRUCTURE FOR TRACK C: The operator wants to simulate Nifty futures exposure via an option. Three candidates: (a) Deep ITM call at ~2000-2500 points ITM, delta ~0.90, premium ~₹2-3L, single leg — has theta decay but no roll cost; (b) Synthetic long (buy ATM call + sell ATM put at same strike, near-zero net premium, delta ~1.0, margins like futures) — true futures proxy but the short put leg creates overlap with the CSP overlay strategy (CSP + synthetic long = 2 short puts at different strikes); (c) Near-ATM call at ~1000-1500 points ITM, delta ~0.70, premium ~₹1-1.5L — cheaper but more theta drag and lower delta fidelity. Which structure is most cost-effective for a 12-month paper trading comparison where the purpose is to overlay protection strategies (protective put, covered call, CSP) and compare with Track A/B? Cost-effectiveness must account for: total cost of carry including theta decay, margin capital locked, interaction with the CSP overlay (avoid creating unintended double short-put positions), and how cleanly the protective strategies work on each structure. (2) OVERLAY STRATEGY INTERACTION MATRIX: For each of the 3 base instruments, describe how each overlay strategy changes the combined portfolio Greeks and P&L characteristics: (a) Long NiftyBees + protective put: standard protective put, delta decreases as Nifty falls below strike — textbook. (b) Long NiftyBees + covered call: standard covered call, upside capped — textbook. (c) Long Nifty Futures + protective put: same delta profile as (a), but futures P&L is linear (no intrinsic value, no theta on the base position) — the combination is a synthetic long call. (d) Long Nifty Futures + covered call: futures + short call = synthetic short put — creates significant downside risk without the protective put present. (e) Long deep-ITM call (delta 0.90) + protective put: effectively a bull call spread (long high-delta call + long low-delta put is equivalent to long call spread after Greek decomposition). The combined Vega and theta change dramatically. (f) Long deep-ITM call + covered call (short OTM call): calendar diagonal spread or vertical spread depending on expiry. Are there any combinations in this matrix that are structurally dangerous (e.g., create unlimited downside) or that are redundant (e.g., the combination of overlay + base instrument is equivalent to a simpler structure that can be entered directly at lower cost)? (3) ADDITIONAL PROTECTION STRUCTURES: Beyond protective puts, covered calls, and CSP, what other structures are worth paper-trading and backtesting in this framework, given the operator's profile (retail, single operator, Nifty 50 index options, 1-lot scale, ₹1.2cr collateral pool)? Specifically evaluate: collars (protective put + covered call simultaneously — net cost lower than protective put alone), ratio spreads (buy 1 ATM put, sell 2 OTM puts — zero cost but creates a net short put below the lower strike), and any structure that benefits from Nifty's well-documented negative skew (IV premium on puts vs calls) while providing defined downside protection. (4) DAILY P&L REPORT DESIGN: For a daily mark-to-market report covering all 3 tracks + their overlays, what metrics are essential for the comparison to be meaningful? Specifically: (a) should base position P&L and overlay strategy P&L be reported separately within each track (so you can see 'NiftyBees lost ₹8,500 today, protective put gained ₹12,000, net ₹3,500') or as a combined single-track P&L? (b) Should the report include a cross-track comparison (which track is ahead on total P&L, which has the lowest drawdown) and if so, how should the capital basis be normalised across tracks (NiftyBees requires ₹15.5L capital, futures requires only ₹1.5L margin — the raw P&L comparison is misleading without capital normalisation)? (c) What is the minimum set of Greeks (delta, theta, vega at portfolio level per track) that should be reported daily to make the comparison actionable rather than just historical?"
```

---

## Parameters Summary

| Parameter  | Value                                                                        |
|------------|------------------------------------------------------------------------------|
| `--topic`  | `nifty-long-instrument-comparison-protection`                                |
| `--template` | `strategy_parameters`                                                      |
| `--context` | `docs/strategies/niftyshield_integrated_v1.md`                             |
| `--question` | See command above (long-form, all 4 sub-questions included)                |

---

## Additional Context Files (load before submitting)

- `docs/strategies/csp_nifty_v1.md` — the existing CSP overlay being run in paper trading;
  the council answer must ensure Track C's ITM option structure does not create unintended
  overlap with this strategy's short put leg
- `MISSION.md` — Principle IV (segregate pools): the comparison framework must not blur the
  line between the trading book (overlay strategies) and the collateral book (NiftyBees ETF)
- `docs/plan/signals-eval-core/stories.md` §SE4.x (Covered Call Overlay is Strategy 4 in the
  investment pipeline — 15-delta OTM call on pledged NiftyBees, same entry window as CSP).
  The council answer for Track A's covered call must be compatible with this existing spec
  or explicitly supersede it.
- `REFERENCES.md` — Nifty lot size (currently 65 units as of Jan 2026; verify before
  submitting; Nifty Futures has the same lot size as options for the same expiry cycle)

---

## What This Decision Unlocks

- New paper strategy prefix conventions:
  - `paper_nifty_etf_v1` (Track A — NiftyBees base)
  - `paper_nifty_futures_v1` (Track B — Futures base, requires roll logic in `record_paper_trade.py`)
  - `paper_nifty_itm_v1` (Track C — ITM option base, structure per council answer)
- Overlay strategies recorded under each track prefix with distinct `leg_role`:
  - `base_long`, `protective_put`, `covered_call`, `csp_short_put`, `collar_put`, `collar_call`
- A new daily report script: `scripts/nifty_long_comparison_report.py` — generates per-track
  and cross-track MTM with capital-normalised comparison (council answer on normalisation method
  drives the report design)
- The Nifty Futures roll logic in `scripts/roll_leg.py` / `scripts/record_paper_trade.py`:
  futures need a systematic roll event at a defined DTE before expiry — council answer may
  specify the roll convention
- `src/paper/models.py` extension: futures and ITM options as paper positions require slightly
  different P&L calculations than equity/ETF positions currently modelled

---

## My Recommendation on ITM Option Structure (for context when reviewing council output)

Before the council responds, the structural argument for each option:

**Recommend: Deep ITM call at ~2000-2500 points ITM (delta ~0.90)**
- Reasoning: Single leg. Does not pre-load a short put (synthetic long would). Delta ~0.90
  provides near-futures exposure. Premium ~₹2-3L vs ₹15.5L for NiftyBees — significant
  capital efficiency. The theta drag (~₹60-120/lot/day at 30 DTE for a call this deep ITM)
  is the paper trading cost being measured, not a hidden flaw. Most importantly, it keeps
  the protective put and CSP overlays clean — you can add a short put (CSP) without it
  interacting with a pre-existing short put leg from a synthetic.

**Against synthetic long:** The short put in a synthetic long already creates short-delta
exposure below the strike. Stacking a CSP (another short put at ~25 delta) means you have
two short puts in the same expiry cycle. The Greeks are not additive in a linear way — the
combined position resembles a 1-2 put ratio spread. This destroys the clean comparison
the framework is designed to provide.
