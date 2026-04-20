# NiftyShield — Literature & Concept Reference

> **Purpose:** A knowledge base mapping every statistical, financial, and ML concept used in `BACKTEST_PLAN.md` to its original academic source and its practical implementation in this project.
>
> **Not a reading list.** A lookup table. When a `BACKTEST_PLAN.md` task references `LIT-XX`, find the entry here for context, source, and "what to do with it."
>
> **For Animesh:** You don't need to read all of this. You need to know what exists so you can look things up when they become relevant. The entries are ordered by when you'll need them in the plan, not by importance.
>
> **For Claude/Cowork:** When implementing a task that cites `LIT-XX`, load that entry's "Implementation notes" before writing code. The notes describe the *specific form* of the concept to implement — most of these techniques have several variants and we've committed to specific choices.

---

## How to Read This File

Each entry has a fixed structure:

```
### LIT-XX — <Concept Name>

**One-liner:** What it is, in one sentence.

**Source:** Original paper / book with year.

**What it actually does:** Plain-language explanation, ~150 words.

**Why it matters for NiftyShield:** How it's used in our system.

**Where in the plan:** Which `BACKTEST_PLAN.md` task(s) reference it.

**Implementation notes:** Specific variant / formula / parameters we've chosen.

**Further reading:** Follow-ups if you want to go deeper.

**Common misconceptions:** Traps to avoid.
```

When a concept has multiple relevant sources, the primary source is listed first.

---

## Section 1 — Epistemology & Mindset (read first, before anything else)

These aren't techniques. They're the intellectual foundation without which the techniques produce overconfidence.

### LIT-01 — Randomness, Survivorship, and Fooled Evidence

**One-liner:** Most apparent "skill" in finance is survivorship and randomness; recognising this is prerequisite to measuring genuine edge.

**Source:** Nassim Nicholas Taleb, *Fooled by Randomness* (2001), *The Black Swan* (2007). Popular-press but rigorous in argument.

**What it actually does:** Taleb catalogs the ways finite-sample evidence leads traders to believe they have edge when they have noise. Core concepts: survivorship bias (we only hear from winning traders), the narrative fallacy (we construct stories after the fact), asymmetric consequences (a strategy with 99% win rate and 1% ruin probability is still ruinous), and the fundamental unknowability of tail events.

**Why it matters for NiftyShield:** The SEBI data says 93% of retail F&O traders lose money across capital sizes. Without Taleb's framing, every technical book in this reference will seduce you into thinking you're in the 7%. With it, you read them as risk-management tools first and edge-generation tools second. This changes sizing, kill criteria, and willingness to accept negative experiment results — all of which show up in the plan.

**Where in the plan:** Phase 0 (before writing any strategy spec); referenced implicitly in every kill-criteria and variance-check task.

**Implementation notes:** Read *Fooled by Randomness* cover to cover before deploying Phase 2.2 (first live strategy). The technical books in §2-§5 are not substitutes.

**Further reading:** Taleb's *Antifragile* (2012) is applicable but less directly. Skip *Skin in the Game* — polemical and less useful for traders.

**Common misconceptions:** "Taleb is anti-quant." He's not; he was a quant. He's anti-overconfident-quant. The distinction matters.

---

### LIT-02 — Kelly Criterion (Optimal Sizing)

**One-liner:** Given known edge and odds, the mathematically optimal bet size that maximises long-run log wealth.

**Source:** Kelly, J. L. (1956). "A New Interpretation of Information Rate." *Bell System Technical Journal*. Popularised for finance by Edward Thorp in *Beat the Dealer* (1962) and *Beat the Market* (1967).

**What it actually does:** For a binary bet with probability `p` of winning `b` rupees per rupee risked, the Kelly fraction is `f* = (bp - (1-p)) / b`. Betting `f*` of bankroll maximises expected log wealth growth; betting more leads to eventual ruin; betting less leads to suboptimal growth. For trading strategies with continuous payoffs, the formula generalises (see Optimal f, LIT-03).

**Why it matters for NiftyShield:** The single most important mathematical concept for retail traders. It answers "how much should I risk per trade" with a non-negotiable number given honest inputs. Most retail blowups happen at 3-5× Kelly sizing. Fractional Kelly (0.25 to 0.5 of full Kelly) is the practitioner standard because win-rate and win/loss-ratio are estimates, not known constants.

**Where in the plan:** Phase 1.5b (`src/analytics/sizing.py`), Phase 2 and beyond (sizing all live strategies).

**Implementation notes:**
- Implement both `kelly_fraction(win_rate, win_loss_ratio)` and `fractional_kelly(..., fraction=Decimal('0.25'))`.
- **Default to 0.25× Kelly for all live strategies** until 100+ trades of realised data confirm the input estimates. Ratchet up to 0.33× only after. Never exceed 0.5× Kelly without a written justification.
- For options strategies with defined risk (IC), use max-loss-per-trade as the denominator for the "risked per trade" input. For CSP, use the margin deployed.
- Log the Kelly fraction in every `backtest_metrics` row so it's tracked as strategies evolve.

**Further reading:** Thorp's *A Man for All Markets* (2017) — Kelly made readable, plus autobiographical context on why it matters. Poundstone's *Fortune's Formula* (2005) — narrative history of Kelly's adoption and rejection by the finance industry.

**Common misconceptions:** "Kelly is too aggressive." This is true of *full Kelly* only when inputs are estimates. Fractional Kelly addresses it. "Kelly doesn't apply to options." Partially true — use Optimal f (LIT-03) for asymmetric payoffs. Both address the same problem.

---

### LIT-03 — Optimal f and Risk of Ruin

**One-liner:** Generalisation of Kelly for asymmetric-payoff strategies; paired with risk-of-ruin formulas that compute the probability of bankruptcy at any given sizing.

**Source:** Ralph Vince, *Portfolio Management Formulas* (1990), *The Mathematics of Money Management* (1992).

**What it actually does:** Kelly assumes binary outcomes. Optimal f numerically finds the fraction of capital that maximises terminal wealth given the actual historical distribution of trade outcomes. Risk-of-ruin formulas compute, for a given sizing and historical win/loss distribution, the probability of losing a threshold amount of capital (e.g., 30%) over unlimited trades.

**Why it matters for NiftyShield:** Every options strategy has asymmetric payoffs. Pure Kelly underestimates the correct size for strategies with frequent small wins and rare large losses (which describes every premium-selling strategy). Risk-of-ruin is the brutal honesty layer — it tells you "at your current sizing, you have a 15% probability of losing 30% of capital within the next 500 trades." That number is uncomfortable and correct.

**Where in the plan:** Phase 1.5b (`src/analytics/sizing.py::optimal_f`, `::risk_of_ruin`).

**Implementation notes:**
- `optimal_f(trades)` iterates candidate `f` values from 0.01 to 0.99 in 0.01 steps, computes terminal wealth for each, returns argmax.
- `risk_of_ruin(win_rate, win_loss_ratio, fraction_risked, ruin_threshold)` — classic formula: `((1-edge)/(1+edge))^(capital_units)`. Returns `Decimal` probability.
- **Run risk_of_ruin before deploying any strategy at any size.** If computed risk of 30% loss is >5%, reduce size. This is a hard check, not an advisory.

**Further reading:** Vince's books are dense and somewhat self-promoting. The core formulas are also in Chan's *Quantitative Trading* (2008) more readably.

**Common misconceptions:** "Risk of ruin is theoretical." It's empirical — computed from your own historical win rate and win/loss ratio. If your strategy changes, recompute. "Optimal f is the same as Kelly." Close but not identical; Optimal f is numerically derived from actual trade distribution and handles fat tails Kelly misses.

---

## Section 2 — Strategy Evaluation Metrics

### LIT-04 — Sharpe Ratio

**One-liner:** Mean return in excess of risk-free, divided by standard deviation of returns. Standard measure of risk-adjusted return.

**Source:** William F. Sharpe (1966). "Mutual Fund Performance." *Journal of Business*.

**What it actually does:** `(mean_return - risk_free_rate) / std_dev_of_returns`, annualised by multiplying by `√(periods_per_year)`. Interpretation: Sharpe > 1 is good, > 2 is excellent, > 3 is rare and usually a sign of overfit or short sample. Penalises volatility symmetrically — upside and downside volatility count equally.

**Why it matters for NiftyShield:** Industry-standard metric; every report includes it. But it has known weaknesses for options strategies (asymmetric payoffs mean upside volatility is good and shouldn't be penalised). Use Sortino alongside it.

**Where in the plan:** Phase 1.5b (`src/analytics/ratios.py::sharpe_ratio`).

**Implementation notes:**
- Annualise daily returns with `√252`. Monthly returns with `√12`.
- Risk-free rate: match the horizon. For monthly strategies, use 91-day T-bill yield. Currently ~6.5-7% in India.
- **Crucial:** Sharpe has massive sampling error. Report alongside its confidence interval (see LIT-07, Probabilistic Sharpe).

**Further reading:** Sharpe's 1994 revision ("The Sharpe Ratio") is the canonical reference. Freely available as a PDF.

**Common misconceptions:** "Higher Sharpe = better strategy." Not always — a strategy with Sharpe 1.2 and max DD 10% can be preferable to one with Sharpe 1.8 and max DD 35%. Sharpe doesn't capture tail risk. "Sharpe of 2 means the strategy works." Not if sample size is 30 trades — the confidence interval swamps the point estimate.

---

### LIT-05 — Sortino Ratio

**One-liner:** Like Sharpe but only penalises downside volatility.

**Source:** Frank Sortino & Lee Price (1994). "Performance Measurement in a Downside Risk Framework." *Journal of Investing*.

**What it actually does:** `(mean_return - target_return) / downside_deviation`, where downside_deviation is std-dev of returns below target only. For any strategy with asymmetric payoff distributions (all options strategies), Sortino is the more honest measure because it doesn't penalise the occasional 4% up-month that happens after a boring 1% up-month.

**Why it matters for NiftyShield:** Default to Sortino over Sharpe for options strategy evaluation. Report both but interpret Sortino as primary.

**Where in the plan:** Phase 1.5b (`src/analytics/ratios.py::sortino_ratio`).

**Implementation notes:**
- Target return (MAR, Minimum Acceptable Return): default 0 (nominal). Some practitioners use risk-free rate. Both defensible; make it a parameter.
- Target Sortino: ≥1.5 for a strategy worth running live.

**Further reading:** Pedersen's *Efficiently Inefficient* (2015) has a good comparison of return metrics including Sortino and Calmar.

**Common misconceptions:** "Sortino is always higher than Sharpe." True when returns are right-skewed (good for you). Can be lower if returns are left-skewed (strategy has more downside than upside variation — which is a red flag for most strategies).

---

### LIT-06 — Calmar Ratio & Ulcer Index

**One-liner:** Calmar = annual return / max drawdown. Ulcer Index = RMS of drawdowns, capturing depth *and* duration.

**Sources:**
- Calmar: Terry W. Young (1991), *Futures* magazine.
- Ulcer Index: Peter Martin & Byron McCann, *The Investor's Guide to Fidelity Funds* (1989).

**What they actually do:**
- Calmar is "how much did I make per unit of worst-case pain" — directly interpretable. Target ≥1.0; strong at ≥1.5.
- Ulcer Index squares the drawdown at each point, takes the mean over the period, square-roots it. Captures the *integrated discomfort* of a drawdown path — two strategies with the same max DD can have very different Ulcer Index if one recovers quickly.

**Why it matters for NiftyShield:** Calmar is the metric your non-technical stakeholders understand. Ulcer is the one that captures "how miserable was the year" — correlates with whether you actually stick to the strategy during drawdowns.

**Where in the plan:** Phase 1.5b (`src/analytics/ratios.py::calmar_ratio`, `::ulcer_index`).

**Implementation notes:**
- Calmar: `annualised_return / abs(max_drawdown_pct)`. If no drawdown in period, return `None` (don't inflate to Infinity).
- Ulcer Index: `sqrt(mean(drawdown_from_peak_pct ** 2))` over the full period.

**Further reading:** Martin's original paper is hard to find; the formula is clearly described in Chan's *Algorithmic Trading* (2013).

**Common misconceptions:** "Max DD is enough." Max DD is one number from one day — uninformative about the path.

---

### LIT-07 — Probabilistic Sharpe Ratio (PSR)

**One-liner:** The probability that a strategy's *true* Sharpe exceeds a benchmark, accounting for sample size and return distribution shape.

**Source:** David H. Bailey & Marcos López de Prado (2012). "The Sharpe Ratio Efficient Frontier." *Journal of Risk*.

**What it actually does:** Point-estimate Sharpe has huge sampling error. A Sharpe of 1.2 over 50 trades has a 95% CI of roughly [0.4, 2.0]. PSR converts this into a probability: given observed Sharpe, sample size, skew and kurtosis of returns, what's the probability the true Sharpe exceeds (say) 1.0? Returns a value in [0, 1].

**Why it matters for NiftyShield:** Stops you from getting excited about a Sharpe of 2.1 over 30 trades (which could easily be a true Sharpe of 0.8). PSR ≥ 0.95 is the threshold for "statistically significant edge at the 5% level."

**Where in the plan:** Phase 1.5b (`src/analytics/ratios.py::probabilistic_sharpe_ratio`).

**Implementation notes:**
- Formula involves the standard normal CDF applied to a sample-size-adjusted statistic; implementable in a few lines of Python with scipy.
- Default benchmark Sharpe: 0 (edge vs random). For "is this strategy worth running" use benchmark = 1.0.
- Mandatory: display PSR alongside every raw Sharpe in reports.

**Further reading:** López de Prado's *Advances in Financial Machine Learning* (2018), Chapter 14.

**Common misconceptions:** "PSR tells me my strategy works." No — it tells you the probability that your *observed data is consistent with* a strategy that works. Sample size matters more than you want.

---

### LIT-08 — Deflated Sharpe Ratio (DSR)

**One-liner:** PSR, corrected for the selection bias introduced by testing many strategies and picking the best.

**Source:** David H. Bailey & Marcos López de Prado (2014). "The Deflated Sharpe Ratio." *Journal of Portfolio Management*.

**What it actually does:** If you backtest 20 strategies and pick the best one, its Sharpe is inflated by selection bias. DSR adjusts: "given that I searched among N strategies, what's the probability the winner's true Sharpe beats the benchmark?" Requires tracking `num_trials`.

**Why it matters for NiftyShield:** Critical as the plan evolves into a multi-strategy basket. If you test 5 conditioning rules and pick the best, raw Sharpe says "this works"; DSR says "after correcting for the selection, probability of real edge is 40%." Without this correction, every extension of the backtest pipeline is a potential overfit.

**Where in the plan:** Phase 1.5b (`src/analytics/ratios.py::deflated_sharpe_ratio`); Phase 3.5b (regime conditioning experiment — must report DSR of the conditioned version).

**Implementation notes:**
- Track `num_trials` globally. Increment for every config change / parameter tuning that's been tested. Under-reporting is the common failure mode.
- **If you don't track num_trials honestly, DSR is useless.** The point is the discipline, not the formula.

**Further reading:** Bailey & López de Prado's paper is freely available on SSRN. Worth reading directly — short and clearly written.

**Common misconceptions:** "I only tested 1 strategy, so DSR = PSR." Every parameter tweak is a trial. If you iterated on stop-loss levels, each variation counts. Easy to undercount; conservative counting is the safer error.

---

### LIT-09 — R-Multiples and Trade Quality Metrics

**One-liner:** Normalise each trade's P&L by the amount risked on that trade; evaluate the distribution of R-multiples rather than raw rupees.

**Source:** Van K. Tharp, *Trade Your Way to Financial Freedom* (1999). Original concept; later refined by Chuck LeBeau and others.

**What it actually does:** For each trade, `R = realised_pnl / risk_taken`. A +2R trade made twice the amount risked; a −1R trade lost exactly the risk amount; a −3R trade overshot the stop (slippage or gap). Tharp's thesis: professional traders optimise the R-multiple distribution (positive expectancy, fat right tail) rather than absolute rupee P&L.

**Why it matters for NiftyShield:** Makes strategies with different position sizes comparable. CSP trades at ₹50K risk and IC trades at ₹20K risk can't be directly compared in rupees, but their R-multiple distributions can. Also highlights execution quality — losses >1R indicate slippage or override of stop-loss rules.

**Where in the plan:** Phase 1.5b (`src/analytics/trade_metrics.py::r_multiple_distribution`). Required input: `risk_per_trade` field in every `Trade` or `PaperTrade` record.

**Implementation notes:**
- Extend `Trade` model to include `intended_risk` field (Decimal, optional for historical trades but required for new ones).
- Report: mean R, std R, % trades > +1R, % trades < −1R (the latter indicates stop-loss misses).

**Further reading:** Tharp is pop-trading-psychology; R-multiples themselves are rigorous but the book is padded. Skip unless specifically interested.

**Common misconceptions:** "R-multiples replace rupee P&L." They complement — both matter.

---

## Section 3 — ML for Finance (Phase 4 material)

### LIT-10 — Meta-Labeling

**One-liner:** Use ML to decide whether to act on signals from a rule-based primary strategy, not to generate signals.

**Source:** Marcos López de Prado, *Advances in Financial Machine Learning* (2018), Chapter 3.

**What it actually does:** Primary strategy generates signals via existing rules (CSP entry rule fires). Secondary binary classifier, trained on regime features + signal strength + recent P&L context, predicts whether *this specific signal instance* will be profitable. The classifier filters signals; it doesn't generate them. Published results show 20-40% Sharpe improvement on primary strategies with meta-labeling overlay. Requires ≥500 labeled historical signals.

**Why it matters for NiftyShield:** This is the one ML application with serious academic backing that applies to retail-accessible data. It augments rather than replaces the rule-based strategies the whole plan is built around. Appropriate for Phase 4, not before.

**Where in the plan:** Phase 4.3.

**Implementation notes:**
- Label definition: did the primary signal hit its profit target before hitting its stop? Binary outcome.
- Features: regime classifier output (3.5), recent strategy P&L z-score, time-since-last-loss, IV rank at signal time.
- Model: gradient boosting (XGBoost, LightGBM). Linear classifiers underfit financial data. Neural nets overfit retail data volumes.
- Cross-validation: **purged k-fold only** (LIT-11). Standard k-fold leaks future information through sample overlap.
- Evaluation: Deflated Sharpe (LIT-08) on meta-labeled returns vs raw strategy returns. Selection bias correction is non-negotiable here.

**Further reading:** López de Prado's book, Chapters 3, 6, 7, 14 are the core reading. Dense; expect to reread. His lectures on YouTube are free and good.

**Common misconceptions:** "Meta-labeling predicts trades." It predicts *signal quality given that a signal has already fired*. Without the primary signal it has no input. "Meta-labeling is easy because it's just classification." The data pipeline (label generation, purged CV, feature alignment) is 80% of the work; the model fitting is 20%.

---

### LIT-11 — Purged Cross-Validation

**One-liner:** Cross-validation method for financial time-series that prevents information leakage from overlapping samples.

**Source:** López de Prado, *Advances in Financial Machine Learning* (2018), Chapter 7.

**What it actually does:** In financial data, labels often depend on future outcomes (e.g., "did this signal hit its 30-day profit target"). Standard k-fold splits can place training samples that overlap with test samples, leaking the answer. Purged CV explicitly removes training samples that overlap with the test period in label-horizon space. Also introduces an embargo period to prevent near-boundary leakage.

**Why it matters for NiftyShield:** Any ML validation that doesn't use purged CV is likely overfit. The most common failure mode of retail ML-for-finance is standard k-fold producing optimistic validation metrics that collapse in production.

**Where in the plan:** Phase 4.3 (`src/ml/purged_cv.py`).

**Implementation notes:**
- Implement `PurgedKFold(n_splits, t1_series, pct_embargo)` mirroring sklearn's `KFold` API.
- `t1_series` = DatetimeIndex of label expiration times per training sample.
- Default embargo: 1% of total sample period.

**Further reading:** Chapter 7 of López de Prado 2018 has complete code.

**Common misconceptions:** "sklearn's TimeSeriesSplit solves this." No — TimeSeriesSplit respects temporal order but doesn't handle label-horizon overlap. Use purged CV.

---

## Section 4 — Regime & Signal Indicators

### LIT-15 — ADX (Average Directional Index)

**One-liner:** Trend strength indicator; measures whether a market is trending or ranging, without indicating direction.

**Source:** J. Welles Wilder, *New Concepts in Technical Trading Systems* (1978).

**What it actually does:** Uses directional movement (high − prior high vs prior low − low) smoothed over a window (default 14 periods). Outputs a single value in [0, 100]. ADX > 25 → strongly trending (either direction). ADX < 20 → ranging. Does not indicate direction — pair with 50-SMA-vs-200-SMA for direction.

**Why it matters for NiftyShield:** The "is Nifty trending?" question needs a quantitative answer to drive the regime classifier. ADX is the standard, widely-backtested, well-understood choice. 48 years of practitioner use across every liquid market.

**Where in the plan:** Phase 3.5 (`src/signals/trend.py::adx`).

**Implementation notes:**
- Window: 14 days (Wilder's original; practitioner standard).
- Compute `+DI` and `−DI` alongside; the regime classifier uses all three.
- Threshold for "trending": ADX > 25 (standard).

**Further reading:** Wilder's book is the primary source but dated in presentation. Most modern TA textbooks repeat the formulas cleanly.

**Common misconceptions:** "ADX tells me the direction of the trend." No — only strength. Direction comes from `+DI vs −DI` or from SMA relationships.

---

### LIT-16 — Kaufman's Efficiency Ratio

**One-liner:** Ratio of directional price movement to total price movement; measures how "efficient" the market is moving.

**Source:** Perry J. Kaufman, *Smarter Trading* (1995), *Trading Systems and Methods* (5th ed., 2013).

**What it actually does:** `ER = abs(close_today - close_N_days_ago) / sum(abs(daily_changes))` over N days. Output in [0, 1]. ER = 1 → perfectly directional move. ER = 0 → pure noise (all up/down cancels out). Complements ADX — ADX measures direction strength on a scale, ER measures path efficiency.

**Why it matters for NiftyShield:** Cross-checks ADX. If ADX says "trending" but ER is low, the trend is zigzaggy and options conditioning on trend will underperform. Two-signal confirmation reduces false positives.

**Where in the plan:** Phase 3.5 (`src/signals/trend.py::efficiency_ratio`).

**Implementation notes:**
- Default window N: 10 days.
- Threshold: ER > 0.3 for strong efficiency.

**Further reading:** Kaufman's *Trading Systems and Methods* is the most comprehensive trading-systems reference available; use as a library.

---

### LIT-17 — IV Rank and IV Percentile

**One-liner:** Where current implied volatility sits in its recent historical range (IVR) or distribution (IVP).

**Source:** Practitioner lore, formalised by tastytrade (Tom Sosnoff et al.) around 2012. No single academic source; documented across broker education platforms.

**What it actually does:**
- IVR = `(current_IV - IV_low_52w) / (IV_high_52w - IV_low_52w) * 100`. Output [0, 100].
- IVP = `% of days in the last 252 where IV < current_IV`. Output [0, 100].

IVR is sensitive to outliers (one big spike year inflates the denominator). IVP is robust to outliers but less sensitive to recent structure. Use both.

**Why it matters for NiftyShield:** The best-documented edge in premium selling is "sell when IV is rich, not when it's cheap." IVR and IVP operationalise "rich." Rule of thumb: premium selling favored at IVR > 50; aggressive at IVR > 70; skip at IVR < 30.

**Where in the plan:** Phase 3.5 (`src/signals/options_structure.py::iv_rank`, `::iv_percentile`).

**Implementation notes:**
- Compute from India VIX for index-wide IV state; from specific option chain for strategy-specific IV state.
- 252-day lookback = 1 trading year.
- Update daily via the Dhan chain snapshot job (Phase 1.10).

**Further reading:** Tastytrade research team has published extensively on IVR thresholds and historical win-rate conditioning. Their studies are promotional but the empirical methodology is sound.

**Common misconceptions:** "High IVR means sell options." Necessary but not sufficient — also need a reasonable term structure and absence of imminent catalyst. IVR is one filter, not the whole decision.

---

### LIT-18 — Volatility Skew and Smile

**One-liner:** Pattern of implied volatility across strikes at a single expiry.

**Source:** Academic literature extensive; Derman & Kani (1994), Dupire (1994), Heston (1993) for the theoretical models. Practitioner overview: Rebonato, *Volatility and Correlation* (2004).

**What it actually does:** In liquid index options (including Nifty), OTM puts trade at higher IV than ATM, and OTM calls at lower IV than ATM — the "skew." Measurable as the IV difference between 25-delta put and 25-delta call. Skew widens during fear regimes. The term structure (IV at 30 DTE vs 90 DTE) carries information about expected event volatility.

**Why it matters for NiftyShield:** Skew and term structure are the bread and butter of volatility-aware option strategies. Detecting skew extremes can inform strategy selection (e.g., sell expensive puts during high-skew periods, roll to calls during low-skew periods).

**Where in the plan:** Phase 3.5 (`src/signals/options_structure.py::skew_25d`, `::term_structure_slope`).

**Implementation notes:**
- 25-delta skew: `iv(25d_put) - iv(25d_call)` at the nearest monthly expiry. Positive = normal, negative = rare (backwardation in vol surface).
- Term structure slope: `iv(30d_ATM) - iv(90d_ATM)`. Positive = contango (normal), negative = backwardation (event stress).

**Further reading:** For depth, Rebonato's book is the canonical reference but mathematically demanding. Natenberg's *Option Volatility and Pricing* (2014) is the practitioner standard and much more accessible.

**Common misconceptions:** "Skew is the same as vol smile." Skew is the directional tilt of the smile; smile is the full curve. Use skew as a scalar indicator.

---

## Section 5 — Behavioral & Process Research

### LIT-25 — Trading Process Metrics

**One-liner:** Professional trading firms track *process* KPIs (adherence, override rate, decision latency) separately from *outcome* KPIs (P&L, Sharpe).

**Source:** Brett N. Steenbarger — *Enhancing Trader Performance* (2007), *The Daily Trading Coach* (2009), *Trading Psychology 2.0* (2015). Practitioner-rigorous rather than academically rigorous.

**What it actually does:** Steenbarger argues that retail traders overwhelmingly fail due to execution inconsistency, not strategy inadequacy. He proposes measuring and optimising execution quality via process metrics: adherence to written rules, outcome-audit of rule overrides, time-between-signal-and-action, position-sizing consistency.

**Why it matters for NiftyShield:** Your engineering background is a massive advantage here — you can instrument these metrics automatically. Most retail traders rely on memory and self-reports, which are systematically biased toward self-flattery. `src/analytics/process.py` turns this into empirical data.

**Where in the plan:** Phase 1.5b extension (future — not in initial scope). Consider adding in Phase 2 after first 30 live trades.

**Implementation notes (for eventual build):**
- Adherence rate: % of trades that followed written spec without override. Compute from `Trade.notes` field with override tags.
- Override outcome: for each override, did it help (positive P&L delta vs spec-followed counterfactual) or hurt?
- Decision latency: time between signal generation (in logs) and order placement.

**Further reading:** *Enhancing Trader Performance* is the most useful of Steenbarger's books for this purpose. *Trading Psychology 2.0* is longer and more meditative.

**Common misconceptions:** "This is touchy-feely psychology." It's quantitative measurement of decision-making quality. The fact that the measured entity is human behavior doesn't make the measurement subjective.

---

### LIT-26 — Skill vs Luck Decomposition

**One-liner:** Framework for determining how much of observed performance is skill vs luck, with implications for how long a track record must be before it's informative.

**Source:** Michael J. Mauboussin, *The Success Equation* (2012).

**What it actually does:** Mauboussin distinguishes "paradox of skill" (as average skill rises, variation in skill compresses, and luck dominates short-term results) from "hot hand" (persistence of skill signals over time). Quantifies how many trades / games / quarters are needed before a performance difference is statistically informative. For stock-picking, the answer is often "more than a career."

**Why it matters for NiftyShield:** Calibrates expectations for the first 2-3 years of live trading. If your basket produces 12% annualised in Year 1, this is not evidence of a 12%-annualised strategy — it's evidence of a strategy that produced 12% in a specific regime. Mauboussin's framework prevents premature conclusions in either direction.

**Where in the plan:** Implicit throughout Phase 2 and Phase 3. Referenced in kill criteria decision-making.

**Implementation notes:** No code. Read the book, internalise the framework, apply it to interpretation of live results.

**Further reading:** Mauboussin's other books (*More Than You Know*, *Think Twice*) are complementary but repetitive if you've read this one.

---

## Section 6 — Indian Market Specific

### LIT-30 — SEBI F&O Retail Performance Studies

**One-liner:** Regulator-published studies on profit/loss distribution of Indian retail F&O traders. Base rate for failure.

**Sources:**
- SEBI (2023). "Analysis of Profit and Loss of Individual Traders dealing in Equity F&O Segment." January 2023.
- SEBI (2024). "Updated SEBI Study Reveals 93% of Individual Traders Incurred Losses in Equity F&O between FY22 and FY24." September 2024.
- SEBI (2025 follow-up). July 2025 update covering FY24-25.

**What they actually do:** Population-level analysis (near-census coverage) of retail F&O P&L outcomes. Consistent finding: ~90% of retail F&O traders lose money; loss rate invariant to capital size; institutional/algo traders extract most of the winnings.

**Why it matters for NiftyShield:** This is the base rate you're competing against. Every sizing decision, kill criterion, and strategy spec exists in the context of this distribution. Anchors expectations: 8-15% annualised on a defined-risk, disciplined basket is the top-quartile outcome, not the median.

**Where in the plan:** Implicit throughout. Explicit reference in Phase 4 (basket performance evaluation).

**Implementation notes:** Review the most recent SEBI study annually. Update expectations if the base rate shifts materially.

**Further reading:** Capitalmind's analysis ("Five Lessons from SEBI's F&O Study", 2024) is a well-done summary if the original report is too dry.

---

### LIT-31 — Indian Options Market Microstructure

**One-liner:** Collection of practitioner research on Nifty options specifics — expiry mechanics, STT treatment, pin risk, retail flow concentration.

**Sources:** Scattered; no single definitive text. Worth tracking:
- NSE working papers (nseindia.com).
- Zerodha's Varsity modules on options (free, well-written).
- Sensibull research notes (practitioner-level, India-specific).
- Academic papers on Nifty option pricing from IIM and ISB (search Google Scholar).

**Why it matters for NiftyShield:** Generic options literature is US-market biased. Indian-market specifics affect strategy design: last-Tuesday monthly expiry, ITM STT trap (partially resolved in 2024), weekly expiry day changes, lot-size changes, retail concentration in weekly OTM options.

**Where in the plan:** Referenced throughout — cost model (Phase 1.4), expiry handling (Phase 0.3), strategy specs.

**Implementation notes:** Treat as living research. Update `REFERENCES.md` as new material is reviewed.

---

## How the Plan Uses This File

Every time a `BACKTEST_PLAN.md` task cites a `LIT-XX` code, this file is the context. Specifically:

- **Phase 1.5b** (`src/analytics/`) implementation references LIT-02 through LIT-09.
- **Phase 3.5** (`src/signals/`, `src/regime/`) implementation references LIT-15 through LIT-18.
- **Phase 3.5b** (conditioning experiment) references LIT-08 (DSR) for evaluation.
- **Phase 4.3** (meta-labeling) references LIT-10 and LIT-11.
- **Phase 2 and Phase 4 gate reviews** reference LIT-01, LIT-25, LIT-26 for mindset calibration.

The LIT-XX codes are stable — if this file is reorganised, codes do not renumber.

---

## Reading Plan (Prioritised — if you only read some of this)

**Month 1** (before any live deployment): LIT-01 (Taleb). Non-negotiable.

**Month 2-3** (Phase 0/1 development): LIT-02 (Thorp's Kelly). The mathematical foundation.

**Month 4-6** (Phase 1 implementation): LIT-04 through LIT-09 (evaluation metrics). Pick and choose from the papers directly — they're short. No book required.

**Month 7-12** (Phase 2 live trading begins): LIT-25 (Steenbarger) and LIT-26 (Mauboussin). You'll need the behavioral framework after your first drawdown.

**Year 2+** (Phase 4 ML consideration): LIT-10 and LIT-11 (López de Prado's book). Only if Phase 3 performance justifies the investment.

**Optional / ongoing:** LIT-18 (Natenberg) as a reference for options strategy depth. LIT-30 (SEBI studies) annually.

You do not need to read all of this before starting. You need to know it exists and where to find it.

---

*End of reference. Append new entries using the fixed structure above. LIT-XX codes are permanent.*
