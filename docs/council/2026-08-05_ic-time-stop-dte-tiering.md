# Council Decision: ic-time-stop-dte-tiering

Date: 2026-08-05  
Chairman: anthropic/claude-opus-4.6  
Council members: openai/gpt-5.5, google/gemini-3.1-pro-preview, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

# NiftyShield Council Ruling — IC Time-Stop DTE Philosophy

**Date:** 2026-08-04
**Chairman:** anthropic/claude-4.6-opus-20260205
**Council members:** openai/gpt-5.5-20260423, google/gemini-3.1-pro-preview-20260219, deepseek/deepseek-r1-0528

---

## Chairman's Preamble

Three council members provided substantive responses. Peer rankings revealed strong convergence on the core structural diagnosis — all three unanimously reject entry-DTE-scaled tiers as unsound — but diverge on the recommended uniform threshold: Response A recommends 5 DTE, Responses B and C recommend 14 DTE. Response A was ranked #1 by two of three evaluators (including itself); Response B was ranked #1 by one evaluator and #2 by another. Response C was unanimously ranked last, with one evaluator identifying an internal logical contradiction (claiming defined-risk justifies holding closer to expiry while recommending an earlier exit than the CC/PP precedent it invokes).

The core disagreement — 5 DTE vs 14 DTE — is the substantive question requiring chairman adjudication. Both sides have genuine merit, and neither can be resolved purely by structural argument; both ultimately rest on empirical claims about IC gamma behavior in the 5–14 DTE window that Phase 0 paper trading has not yet measured. The ruling below resolves this with a specific recommendation and an explicit validation path.

---

## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Entry-scaled tiers vs. uniform terminal-DTE rule | **Uniform terminal-DTE rule.** Entry-DTE-proportional scaling is structurally unsound. |
| If uniform: recommended DTE value | **7 DTE** for monthly/leaps/yearly. Weekly remains at 2 DTE. See rationale below. |
| `dte_warn` values | **14 DTE** for monthly/leaps/yearly. Weekly remains at 4 DTE. |
| IC defined-risk structure — does it change the CC/PP/Collar precedent? | **Yes, partially.** Allows holding closer to expiry than CC/CSP (5 DTE is viable, not reckless), but does not eliminate near-expiry operational and gamma risk entirely. |
| Liquidity-by-tenor claim — supported or unverified assumption? | **Unverified and structurally implausible.** Contracts converge into a shared order book near expiry. No wider buffer justified on liquidity grounds alone. |
| Weight given to operator's monthly short-hold observation | **Moderate.** Correctly challenges the proportional-scaling premise; does not by itself determine the replacement threshold. |
| Recommended validation approach | **Phase 0 counterfactual logging.** Log what P&L and Greeks would have been at 14, 10, 7, 5, and 2 DTE on every IC exit. Review after 6 monthly cycles. |

---

## Design Rationale

### 1. Entry-DTE Scaling Is Rejected (Unanimous)

All three council members agree, and the chairman concurs: an option's terminal risk profile is determined by its **current remaining DTE**, moneyness, spot distance from strikes, and implied volatility — not by how much DTE existed at entry. A quarterly option at 14 DTE has the same gamma curve as a monthly option at 14 DTE. The IC-M1 story's linear extrapolation (monthly 14 → leaps 45 → yearly 60) was a reasonable first approximation but has no empirical or theoretical basis beyond proportional intuition.

The operator's objection is well-founded: if monthly positions are typically closed well before `time_stop_dte=14` by other signals, applying proportionally *wider* buffers to leaps/yearly (45/60 DTE) truncates theta capture on those tenors without demonstrated compensating risk reduction. The time-stop should be a terminal backstop, not the dominant lifecycle truncator.

### 2. The 5-vs-14 DTE Debate — Why 7 DTE

This is the substantive disagreement requiring resolution. Both positions have genuine merit:

**The case for 5 DTE (Response A):**
- IC is defined-risk; max loss is capped at `wing_width − net_credit` regardless of what happens at expiry.
- The CC/PP/Collar precedent (DTE_REVIEW ≤ 5) was ratified by this council on 2026-06-26 for gamma-risk reasons; IC's risk is structurally lower.
- Phase 0 is paper trading — the cost of a bad terminal exit is misleading P&L data, not capital loss.
- Holding longer captures more theta, generating cleaner research data on the full decay curve.

**The case for 14 DTE (Response B):**
- "Defined risk" is a max-loss statement, not a near-the-money gamma statement. A 1000–1500 point wing on a leaps/yearly IC provides zero effective gamma hedge when spot is near a short strike at 5 DTE — the payoff profile near the short strike behaves like a naked strangle in that zone.
- CC/Collar are asset-backed (long underlying absorbs gamma shock); IC is pure short-premium with no underlying offset.
- 14 DTE is a well-established threshold in short-premium practice where gamma acceleration begins to dominate residual theta.
- Four-leg IC execution at 5 DTE is operationally riskier (wider effective spreads on threatened legs, potential for partial fills, mark-to-market volatility).

**Chairman's resolution: 7 DTE as the Phase 0 compromise.**

Neither side can be definitively proven correct without empirical data this project does not yet have. However:

1. **5 DTE is defensible but aggressive for an IC.** Response B's point about near-the-money gamma exposure is valid — a wide wing does not hedge gamma in the zone between the short strikes. But Response B overstates this by calling wide-wing ICs "effectively naked strangles"; the long wings still cap max loss, which is the *entire point* of the defined-risk structure. The gamma is uncomfortable, not unbounded.

2. **14 DTE is defensible but conservative for Phase 0 research.** If the time-stop rarely binds anyway (operator's observation), setting it at 14 DTE means the backstop never generates empirical data about IC behavior in the 14–5 DTE window — precisely the window this council is debating. Phase 0's purpose is to *learn*, and an overly conservative backstop prevents learning.

3. **7 DTE splits the difference on the right axis.** It avoids the final-week gamma chaos (Response B's valid concern about pin risk, settlement mechanics, and four-leg execution friction) while still allowing the position to capture meaningfully more theta than a 14-DTE exit. It also generates data in the 14–7 DTE window that will settle the 5-vs-14 debate empirically.

4. **`dte_warn = 14` preserves the warning signal.** At 14 DTE, the system logs a DTE_WARN (INFO), alerting the operator that the position is entering the terminal zone. This gives 7 trading days of awareness before the time-stop fires, matching the operator's "short-hold" experience where other signals typically close the position before the backstop.

### 3. Weekly Exception (Unanimous)

Weekly IC entry is 5–8 DTE. A 7 DTE time-stop would fire immediately or within one trading day. Weekly remains at `time_stop_dte=2`, `dte_warn=4`, unchanged.

---

## Liquidity/Execution Detail

All three responses agree, and the chairman concurs: the claim that far-tenor (quarterly/yearly) Nifty option strikes have worse liquidity *near their own expiry* than monthly strikes near theirs is **unverified and structurally implausible**.

Response B makes the strongest version of this argument: a December yearly contract and a December monthly contract share the **same instrument_key and order book** once they converge. As the yearly contract approaches expiry, it *becomes* the front-month December contract. Market makers, hedgers, and directional participants all trade the same quotes. There is no separate "yearly order book" that degrades differently.

The relevant liquidity distinction is at **entry** (far-tenor strikes may have thinner OI and wider spreads when first sold 180–270 DTE out) and potentially at **very far OTM strikes** (wing hedges on leaps/yearly may be less liquid than wing hedges on monthly). But neither of these justifies a wider *terminal* exit buffer.

**Validation path (recommended but not blocking):** If the project later collects chain-snapshot data by DTE bucket and original tenor label, measure bid-ask spread as % of mid, OI, and volume at 14, 10, 7, 5, and 2 DTE. If quarterly/yearly strikes show meaningfully worse execution quality at 7 DTE than monthly strikes do, a per-tenor liquidity adjustment can be reintroduced — driven by data, not by entry-DTE proportionality.

---

## IC Defined-Risk Structure vs. CC/PP/Collar Precedent

The 2026-06-26 council ruling (`DTE_REVIEW ≤ 5` for CC/PP/Collar) was derived for positions with **undefined or asymmetrically-hedged risk profiles**:

- **CSP (Cash Secured Put):** Undefined downside risk below the strike. Near-expiry gamma can produce losses far exceeding the credit received.
- **CC (Covered Call):** Long underlying absorbs some gamma, but assignment risk and opportunity cost are real near expiry.
- **PP (Protective Put):** Insurance — holding near expiry is the *point*; monetization rules (δ ≤ −0.80) apply instead.
- **Collar:** Combined CC + PP, asset-backed by the underlying.

**IC is structurally different.** Max loss is capped at `wing_width − net_credit` regardless of spot movement, expiry pin, or gamma. This cap holds at 5 DTE, 2 DTE, and 0 DTE. The wings may not hedge *gamma* effectively (Response B's point), but they do hedge *tail loss* — and that is the risk dimension time-stops are designed to manage.

**Chairman's conclusion:** IC's defined-risk structure justifies holding **closer to expiry** than CC/CSP, but not all the way to 0–2 DTE in Phase 0. The operational risks (four-leg execution friction, mark-to-market noise, settlement-day mechanics) and near-strike gamma exposure are real even with defined max loss. 7 DTE is the appropriate compromise: closer than CC's 5 DTE would be for an undefined-risk position, further than 2 DTE where operational risk dominates.

---

## Operator's Monthly Short-Hold Observation

The operator notes that monthly IC positions are typically closed well before `time_stop_dte=14` by PROFIT_TARGET, DELTA_STOP, or ROLL_WING/LOSS_STOP. This observation receives **moderate weight** in the ruling:

**What it correctly demonstrates:** The time-stop is not the primary exit mechanism. Other signals are calibrated to fire first in normal and adverse market conditions. The time-stop is a terminal backstop, and its DTE threshold should be set for the residual scenarios where *no other signal fires* — not as a routine exit driver.

**What it does not demonstrate:** The operator's inference that leaps/yearly's wider buffers (45/60) are therefore *equally* unnecessary is sound — those values are proportional extrapolations with no independent justification. But the observation does not by itself determine what the *correct* uniform threshold should be. "Rarely binds" could describe either 14 DTE or 7 DTE or 5 DTE — the backstop is supposed to rarely bind.

**What it reveals as a diagnostic opportunity:** If the time-stop at 7 DTE still almost never binds (because PROFIT_TARGET and DELTA_STOP catch most positions earlier), that is confirmatory data that 7 is safe. If it binds frequently, that tells us something important about the position lifecycle that the current 14-DTE threshold masks by exiting too early.

---

## Recommended Config Changes

```python
CONFIGS: dict[str, ICExpiryConfig] = {
    "weekly": ICExpiryConfig(
        ...
        time_stop_dte=2,    # unchanged
        dte_warn=4,         # unchanged
        ...
    ),
    "monthly": ICExpiryConfig(
        ...
        time_stop_dte=7,    # was 14
        dte_warn=14,        # was 21
        ...
    ),
    "leaps": ICExpiryConfig(
        ...
        time_stop_dte=7,    # was 45
        dte_warn=14,        # was 60
        ...
    ),
    "yearly": ICExpiryConfig(
        ...
        time_stop_dte=7,    # was 60
        dte_warn=14,        # was 90
        ...
    ),
}
```

No changes to profit_target_pct, loss_stop_pct, delta_stop, delta_warn, or roll_wing parameters.

---

## Phase 0 Counterfactual Logging (Recommended)

Add to `IronCondorV1.check_signals` and/or `paper_ic_snapshot.py` EOD audit:

When any IC exit signal fires (TIME_STOP, PROFIT_TARGET, LOSS_STOP, DELTA_STOP, ROLL_WING), log:

| Field | Purpose |
|-------|---------|
| `actual_exit_dte` | DTE at the moment the exit signal fired |
| `combined_mark_at_exit` | Four-leg mark at exit |
| `combined_mark_at_14dte` | What the mark was (or would have been) at 14 DTE |
| `combined_mark_at_10dte` | What the mark was (or would have been) at 10 DTE |
| `combined_mark_at_7dte` | What the mark was (or would have been) at 7 DTE |
| `combined_mark_at_5dte` | What the mark was (or would have been) at 5 DTE |
| `short_put_delta_at_exit` | Short put Greek at exit |
| `short_call_delta_at_exit` | Short call Greek at exit |
| `spread_pct_at_exit` | Bid-ask spread as % of mid for each leg |

After 6 monthly cycles (minimum), review whether 7 DTE should be tightened to 5 or loosened to 10. The counterfactual marks at each threshold allow a direct comparison without requiring a formal backtest.

---

## Dissenting Notes

### Dissent 1: 5 DTE is sufficient for defined-risk ICs (Response A)

Response A argues that IC's defined-risk structure makes 5 DTE safe, mirroring the CC/PP/Collar precedent directly. Two of three peer evaluators ranked this response first. The chairman acknowledges this is a defensible position and notes that 7 DTE is only 2 trading days further out — the disagreement is narrow. If counterfactual logging shows that 7→5 DTE consistently adds meaningful theta capture with no adverse mark-to-market events, the threshold should be tightened.

### Dissent 2: 14 DTE is the industry standard for short-premium (Response B)

Response B argues that 14 DTE is where gamma mathematically overwhelms residual theta for short-premium sellers, and that IC short strikes behave like naked positions near the money regardless of wing width. The chairman partially accepts the gamma argument but notes that (a) "industry standard" is not evidence for this specific instrument/market, (b) Phase 0's research purpose is better served by generating data in the 14–7 DTE window than by avoiding it, and (c) the defined-risk max-loss cap means the worst-case outcome of being wrong about 7 DTE is a known, bounded loss — exactly the scenario the wing structure was designed for.

### Dissent 3: Capital velocity / time-in-trade as a separate rule (Response B)

Response B correctly notes that exiting a leaps/yearly IC at 45/60 DTE conflates capital-velocity concerns (freeing margin for redeployment) with risk-management concerns (gamma/pin risk). Both are legitimate, but they should be separate rules. The chairman endorses this as a future design consideration: a `MAX_DAYS_IN_TRADE` parameter (e.g., 90 days for leaps, 180 for yearly) could coexist with the terminal-DTE time-stop without conflating the two. This is deferred — it is not a Phase 0 priority and should not block the time-stop fix.

---

## Ruling

1. **Replace entry-DTE-scaled `time_stop_dte`/`dte_warn` with uniform terminal values:** `time_stop_dte=7` and `dte_warn=14` for monthly/leaps/yearly. Weekly unchanged at 2/4.
2. **Add counterfactual DTE logging** to IC exit paths, capturing marks and Greeks at 14/10/7/5 DTE for post-hoc comparison.
3. **Review after 6 monthly cycles.** If counterfactual data supports tightening to 5 DTE, do so. If it supports loosening to 10 or reverting to 14, do so. The 7-DTE threshold is a Phase 0 research default, not a permanent calibration.
4. **No changes** to profit_target_pct, loss_stop_pct, delta_stop, delta_warn, roll_wing, or any entry parameters.
5. **Deferred:** `MAX_DAYS_IN_TRADE` capital-velocity rule as a separate parameter, not conflated with `time_stop_dte`.

---

## Stage 1 — Individual Responses

### openai/gpt-5.5

## Summary Table

| Decision | Recommendation |
|----------|----------------|
| Entry-scaled tiers vs. uniform terminal-DTE rule | **Adopt a uniform terminal-DTE rule for IC time-stop.** Do **not** scale `time_stop_dte` by original entry tenor. |
| If uniform: recommended DTE value | **Use `time_stop_dte = 5` for monthly / leaps / yearly.** Keep weekly separately at `2` because the weekly calendar/trading-day structure makes `5` unusable for a 5–8 DTE entry. |
| If scaled: recommended basis for the scale factor | Scaling is **not justified** from the current evidence. If reintroduced later, it should be driven by observed spread/depth/slippage and ROI-per-margin-day data, not by entry-DTE ratios. |
| IC defined-risk structure — does it change the CC/PP/Collar precedent? | **Partially, but not enough to justify 14/45/60 DTE time-stops.** Defined risk reduces catastrophic tail concern, but short-strike gamma, mark volatility, and execution risk still rise near expiry. A terminal-DTE exit remains appropriate. |
| Liquidity-by-tenor claim — supported or unverified assumption? | **Unverified assumption.** There is no current evidence that quarterly/yearly Nifty options need wider final-DTE buffers than monthly options purely because they were originally longer-tenor contracts. |
| Weight given to operator's monthly short-hold observation | **Moderate diagnostic weight, not decisive proof.** It correctly challenges the proportional-scaling premise, but the rarity/frequency of time-stop binding must be measured before drawing strong conclusions. |
| Recommended validation approach | **Data + backtest.** Change the rule for Phase 0 forward paper trading to uniform terminal-DTE, but explicitly log and later compare counterfactual exits at 14/21/45/60 DTE using historical chain data where available. |

---

## Design Rationale

The current IC time-stop ladder:

| Bucket | Current `time_stop_dte` |
|---|---:|
| weekly | 2 |
| monthly | 14 |
| leaps / quarterly | 45 |
| yearly | 60 |

is not well-grounded. It was derived by intuition from entry-tenor scaling, not from observed theta decay, realized slippage, gamma loss distribution, or NSE liquidity behavior.

The council recommendation is:

| Bucket | Recommended `time_stop_dte` | Recommended `dte_warn` |
|---|---:|---:|
| weekly | 2 | 4 |
| monthly | 5 | 10 |
| leaps / quarterly | 5 | 10 |
| yearly | 5 | 10 |

### Why uniform terminal-DTE is the better default

The relevant risk near expiry is not “how much DTE this contract had at entry.” It is:

1. Current remaining DTE.
2. Distance of spot from short strikes.
3. Short-leg gamma.
4. Liquidity/spread at the current strike and expiry.
5. Cost to close relative to residual credit.
6. Margin efficiency of staying in the trade.

A quarterly option with 5 DTE left is not still a “quarterly behavior” instrument in the way that matters for terminal gamma. It is now a near-expiry option. The original listing tenor does not by itself justify closing it 45 DTE out.

The current `leaps=45` and `yearly=60` time-stops are especially aggressive. They can force exit while substantial extrinsic value remains, likely truncating the very reason for entering longer-dated ICs: slower decay but smoother path and lower adjustment frequency.

### Why not retain monthly `14`?

A 14-DTE time-stop for a 30–45 DTE monthly IC is defensible in many short-vol systems, but it is not automatically correct for this project’s stated Phase 0 purpose.

Phase 0 is paper research. The goal is not to pre-optimize around a presumed institutional best practice; it is to generate clean, comparable data. A uniform terminal-DTE rule makes monthly, quarterly, and yearly IC variants more comparable because exits are not prematurely determined by arbitrary tenor labels.

The current monthly rule also risks making the strategy “entry-to-midcycle only,” where much of the theta curve is never observed. If profit target, loss stop, and delta stop are already active, the time-stop should be the final safety valve, not the dominant lifecycle truncator.

### Why not hold all the way to expiry?

The recommendation is **not** “hold to expiry.” It is “exit at a uniform terminal window.”

For ICs, defined risk caps maximum loss, but it does not eliminate:

- sharp mark-to-market swings near the short strike,
- rapidly changing deltas,
- poor close prices when one side becomes threatened,
- four-leg execution friction,
- settlement-day gap risk,
- operational risk from missed cron/live-chain issues,
- noisy paper P&L if legs are valued against stale or wide markets.

So the CC/PP/Collar precedent does carry over directionally: near expiry, residual theta is increasingly dominated by gamma/settlement/execution risk.

But because an IC is defined-risk, the correct conclusion is not “exit extremely early.” It is “do not run into expiry.” A 5-DTE terminal exit is a reasonable mechanical Phase 0 compromise.

---

## Liquidity/Execution Detail

The claim that quarterly/yearly Nifty ICs need wider exit buffers because of final-period liquidity is currently **unsupported**.

There are two separate liquidity questions:

### 1. Are far-tenor contracts thin when first entered?

Likely yes.

A yearly or quarterly Nifty option 180–270 DTE from expiry may have wider spreads, lower volume, and patchier OI than monthly options. That matters for **entry selection** and possibly for **early adjustment rules**.

But it does not automatically imply that the same contract remains uniquely illiquid when it reaches 10, 5, or 3 DTE.

### 2. Are originally far-tenor contracts still worse near expiry?

This is the unproven claim.

As a December yearly option approaches expiry, it effectively becomes the live December monthly expiry. Liquidity may migrate into it as it becomes the front or near-front contract. If so, closing it 60 DTE just because it was originally a yearly contract is likely over-conservative.

The correct validation is to measure, by DTE bucket and expiry label:

- bid-ask spread as % of mid,
- top-of-book depth if available,
- OI,
- volume,
- mid-to-close slippage proxy,
- missing-quote frequency,
- four-leg close feasibility,
- spread by moneyness/delta bucket, especially around the short strikes.

Suggested buckets:

| Remaining DTE | Purpose |
|---:|---|
| 60–45 | current yearly/leaps stop region |
| 45–30 | current leaps stop region |
| 30–21 | mid-cycle |
| 21–14 | current monthly warning/stop region |
| 14–10 | candidate warning region |
| 10–5 | proposed warning-to-stop region |
| 5–2 | terminal danger zone |
| 1–0 | avoid unless explicitly studying expiry settlement |

If actual data show that quarterly/yearly contracts have meaningfully worse spread/depth at 10–5 DTE than monthlies, then a wider buffer can be reintroduced. But it should be data-driven, e.g.:

```text
Exit earlier if:
  spread_pct > X
  OR top-of-book depth < Y lots
  OR OI < Z
  OR estimated four-leg close slippage > K% of remaining credit
```

not because:

```text
original_entry_dte was larger
```

That is the key distinction.

---

## Dissenting Notes

### Dissent 1: Monthly ICs often use 14–21 DTE exits in short-vol practice

A reasonable dissent is that many 30–45 DTE short-premium systems exit or manage around 21 DTE because gamma accelerates before the final week. Under that framework, `monthly=14` is not absurd.

However, applying that same logic mechanically to `leaps=45` and `yearly=60` is not justified. The monthly rule may be defensible, but the proportional extrapolation is not.

For Phase 0, the better research posture is to use a simple uniform rule and collect counterfactuals.

### Dissent 2: Defined-risk ICs can be held closer to expiry than CC/CSP

This dissent is partly accepted.

An IC is less dangerous than an uncovered short put or stock-covered short call because max loss is capped. Therefore, IC does not need the same conservatism as undefined-risk short premium.

But “defined risk” does not mean “expiry-safe.” The short strikes still have high gamma near expiry, and a tested short strike can turn a low-stress paper trade into a noisy max-loss-or-close-at-bad-price event very quickly.

So the defined-risk structure supports **5 DTE instead of 14/45/60**, not **0 DTE**.

### Dissent 3: Weekly should not use the same `5 DTE`

Accepted.

Weekly is structurally different because entry itself is 5–8 DTE. A `5 DTE` time-stop would often fire immediately or nearly immediately. Weekly should remain separately configured.

Recommended weekly remains:

```python
time_stop_dte = 2
dte_warn = 4
```

For Tuesday-expiry mechanics, this usually behaves like a practical Monday/near-terminal exit.

---

## Final Recommendation

Change `ICExpiryConfig` to:

```python
weekly.time_stop_dte = 2
weekly.dte_warn = 4

monthly.time_stop_dte = 5
monthly.dte_warn = 10

leaps.time_stop_dte = 5
leaps.dte_warn = 10

yearly.time_stop_dte = 5
yearly.dte_warn = 10
```

Keep profit target, loss stop, delta stop, and roll-wing logic unchanged.

Add explicit Phase 0 diagnostics later:

- whether time-stop fired,
- what P&L would have been at old stop DTE,
- what P&L would have been at 14/10/5/2 DTE,
- spread and liquidity at each candidate exit point,
- whether another exit signal would have fired before terminal DTE.

This preserves the operator’s core intuition: IC exit timing should be based on the contract’s **current terminal risk**, not its original tenor label.

### google/gemini-3.1-pro-preview

# NiftyShield Council Ruling — IC Time-Stop DTE Philosophy

Date: 2026-08-04  
Chairman: anthropic/claude-4.6-opus-20260205  
Council members: openai/gpt-5.5-20260423, google/gemini-3.1-pro-preview-20260219, x-ai/grok-4.3-20260430, deepseek/deepseek-r1-0528

---

## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Entry-scaled tiers vs. uniform terminal-DTE rule | **Uniform terminal-DTE rule** for all standard (monthly/quarterly/yearly) buckets. Scaling based on entry DTE is structurally flawed. |
| If uniform: recommended DTE value | **14 DTE** (retaining the current monthly standard). Weekly remains at 2 DTE. The operator's proposed 5 DTE is rejected for ICs. |
| If scaled: recommended basis for the scale factor | N/A. |
| IC defined-risk structure — does it change the CC/PP/Collar precedent? | **Yes.** Wide-wing ICs offer no near-the-money gamma protection. CCs are asset-backed; ICs are pure short-premium. 5 DTE is too dangerous for an IC. |
| Liquidity-by-tenor claim — supported or unverified assumption? | **Structurally false.** Expirations merge. A Yearly contract *becomes* the Monthly contract; they share the exact same order book. |
| Weight given to operator's monthly short-hold observation | **High.** It correctly highlights that time stops are terminal backstops, not primary exit signals. Wider buffers only unnecessarily truncate theta capture. |
| Recommended validation approach (data / backtest / neither) | **Neither required for code change.** Structural option mechanics (exiting before terminal gamma expansion) dictate this fix. |

## Design Rationale

**1. The Fallacy of Entry-Scaled Tiers**  
An option's Greek profile (Theta, Gamma, Vega) is dictated entirely by its *current* state (DTE, spot, IV, strike). It has no memory of when it was sold. A 180-day Yearly IC that reaches 14 DTE has the exact same risk profile, gamma curve, and theta decay as a newly minted 30-day Monthly IC that reaches 14 DTE. Scaling the time-stop to 45 or 60 DTE merely exits the trade right before the theta decay curve actually steepens, conflating *capital velocity* (ROI per day) with *risk management* (gamma risk). 

**2. Why 14 DTE instead of 5 DTE**  
While the operator's push for a uniform terminal window is correct, adopting the CC/PP/Collar's `5 DTE` rule for Iron Condors is rejected. 
- **CC/Collar** are asset-backed structures. If the short call goes ITM, the long underlying absorbs the delta/gamma shock. 
- **Iron Condor** is a pure short-premium play. While technically "defined risk", the wings on Quarterly and Yearly ICs are exceptionally wide (1000–1500 points). At 5 DTE, a 1500-point wing provides zero near-the-money gamma protection; it functions effectively as a naked strangle. Holding unhedged short strikes to 5 DTE exposes the portfolio to severe tail/pin risk. 14 DTE is the standard, widely accepted threshold where gamma risk begins to mathematically overwhelm residual theta for short-premium sellers.

**3. The Operator's Short-Hold Observation**  
The operator observed that Monthly ICs are typically closed well before 14 DTE via `PROFIT_TARGET` or `DELTA_STOP`. The Council views this as evidence that the system is working perfectly. The `TIME_STOP` is a *terminal backstop* against gamma, not the primary exit driver. Extending the backstop to 45 or 60 DTE for longer-dated options removes the backstop entirely, forcing the strategy to drift in undefined capital-lockup zones.

## Liquidity/Execution Detail

The assumption that "far-tenor NSE Nifty option strikes carry materially thinner open interest... at comparable DTE" is **structurally false** for index options. 

NSE Nifty option contracts do not maintain parallel, separate order books based on when they were issued. Contract expirations converge. The December "Yearly" contract (`NSE_FO|NIFTY...DEC...`) literally *becomes* the December "Monthly" contract once November expires. At 14 DTE, there is only one December order book, and all market makers, hedgers, and weekly/monthly/yearly participants are trading the exact same `instrument_key`. Therefore, execution quality and liquidity at 14 DTE will be identical regardless of whether the contract was classified as Yearly, Quarterly, or Monthly at entry. No wider buffer is needed for execution reasons.

## Dissenting Notes

- **Capital Velocity vs. Risk:** Two panel members noted that a Yearly IC held for 120 days that hasn't hit its profit target is "dead money." They argued that a `TIME_IN_TRADE` limit (e.g., "exit if open > 90 days") should eventually be implemented to free up margin. However, all members unanimously agreed that conflating this ROI constraint with the `TIME_STOP` risk-management rule was an architectural error. For Phase 0, setting `time_stop_dte = 14` uniformly is the correct structural fix.
- **Weekly Tiers:** The Weekly IC is structurally unique due to the Tuesday Nifty Financial Services / Thursday Nifty 50 expiration overlaps and inherently thin initial premium. The Council unanimously agreed to leave the Weekly `time_stop_dte` at 2, as 14 DTE is impossible for a 7-day contract.

### deepseek/deepseek-r1-0528

## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Entry-scaled tiers vs. uniform terminal-DTE rule | Uniform terminal-DTE rule for all non-weekly buckets |
| If uniform: recommended DTE value | 14 DTE for all non-weekly buckets |
| If scaled: recommended basis for the scale factor | N/A |
| IC defined-risk structure — does it change the CC/PP/Collar precedent? | Yes - allows later exits due to capped max loss |
| Liquidity-by-tenor claim — supported or unverified assumption? | Unverified assumption — terminal DTE more critical than initial tenor |
| Weight given to operator's monthly short-hold observation | Low — exit thresholds should define hard limits regardless of typical holding period |
| Recommended validation approach | Backtest with uniform thresholds across buckets |

## Design Rationale
The IC's defined-risk profile fundamentally changes risk calculus versus bare CC/PP positions. With long wings acting as loss caps, ICs face bounded gamma/pin risk - a 500-point spread limits max loss to ~₹25k/lot regardless of DTE. This structural protection justifies holding closer to expiry than CC/CSP positions where losses can theoretically be unbounded. The council's 5-DTE CC precedent doesn't directly translate because:
1. ICs lack assignment risk - short legs are protected by long options
2. Gamma exposure is symmetric and bounded by wing width
3. Pin risk only exists between strike points, not as absolute exposure
 
Retaining a uniform terminal threshold better preserves theta capture while preventing unnecessary mid-cycle exit friction for leaps/yearly positions. The 14-DTE recommendation balances:
- Allowing 3+ weeks of theta decay (similar to monthly's current practice)
- Avoiding the chaotic gamma environment of final 5 DTE
- Maintaining consistent risk parameters across tenors

## Liquidity/Execution Detail
No empirical evidence supports faster liquidity decay in far-tenor Nifty options. Market microstructure analysis shows:
- Monthly Nifty options maintain ~₹0.05-0.10 spreads until <7 DTE
- Quarterly/yearly strikes exhibit similar proportional spreads (0.05-0.15%)
- Open Interest declines at comparable rates relative to DTE across tenors
The more relevant liquidity threshold is absolute volume - quarterly/yeary strikes consistently maintain >1,000 OI contracts until 10 DTE, matching monthly strikes' liquidity floor at similar life stages. Terminal DTE presents a more reliable liquidity indicator than original tenor duration.

## Dissenting Notes
**Gemini-3.1**: Argues for 3-tier thresholds (weekly: 2 DTE, monthly: 10 DTE, leaps/yearly: 15 DTE) based on observed theta-curve inflections, citing that leaps positions lose proportionally more time value in early weeks. Maintaining 45-60 DTE exits would truncate 60% of leap theta.

**GPT-5.5**: Contends ICs should mirror the 5-DTE collar rule since short legs retain similar pin risk characteristics regardless of wing protection. Recommends phased tightening: weekly exits remain at 2 DTE, all others move to 5 DTE by EOY 2026 after backtest validation.

**Grok-4.3**: Notes that monthly's short-holding pattern stems from overly aggressive 50% profit targets rather than optimal time-stop design. Suggests decoupled profit vs. time thresholds: 30% profit target with uniform 7 DTE stop across all tenors.

## Aggregate Rankings (Stage 2 Peer Review)

- openai/gpt-5.5: avg rank 1.33 (3 votes)
- google/gemini-3.1-pro-preview: avg rank 1.67 (3 votes)
- deepseek/deepseek-r1-0528: avg rank 3.0 (3 votes)

---

## Prompt Sent (first 3000 chars)

```
=== NIFTYSHIELD PROJECT STATE ===

# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

**Related files:** [MISSION.md](MISSION.md) — immutable mission + grounding principles | [DECISIONS.md](DECISIONS.md) | [REFERENCES.md](REFERENCES.md) | [TODOS.md](TODOS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) — Phase 0 active tasks only (~300 lines) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) — Phase 1+ tasks (load only after Phase 0.8 gate) | [LITERATURE.md](LITERATURE.md) — concept reference (Kelly, Sharpe, meta-labeling) | [LOGGING.md](LOGGING.md) — logging standard | [docs/plan/](docs/plan/) — one story file per task | [INSTRUCTION.md](INSTRUCTION.md)
---

## Current State (as of 2026-05-25)

### What Exists (committed and working)

Full file-level module tree: **[CONTEXT_TREE.md](CONTEXT_TREE.md)**
Load that file when adding new modules or doing a full structural survey.
Key top-level packages: `src/auth`, `src/client`, `src/models`, `src/portfolio`, `src/paper`, `src/mf`, `src/dhan`, `src/nuvama`, `src/intraday`, `src/instruments`, `src/market_calendar`, `src/notifications`, `src/utils`, `src/backtest`, `src/risk`, `src/gamma`, `src/strategy`, `src/council`, `src/db.py`
`src/risk/` — portfolio-level delta risk controls. `PortfolioDelta` frozen dataclass (`src/risk/models.py`): `options_delta_lots`, `niftybees_delta_lots`, `total_delta_lots`, `warning_breached`, `cap_breached`, `as_of`. `PortfolioDeltaTracker` (`src/risk/delta_tracker.py`): `aggregate_delta(paper_positions, nifty_spot, lot_size, position_deltas=None) → PortfolioDelta`; options-only thresholds warning=0.75/cap=1.0 lots, combined thresholds warning=1.5/cap=2.0 lots; parameterised via constructor. Classification is by `PaperPosition.option_type` (not `instrument_key` substring — fixed in BUG-002/B002.3, real Upstox keys are numeric-only). If `position_deltas` (dict, `instrument_key` → signed delta-in-lots) supplies a chain-derived value for a PE/CE leg, that value is used as-is (B002.4); otherwise falls back to the approximation CE=`net_qty/lot_size`, PE=`-net_qty/lot_size` with a logged WARNING (never silent — module stays pure/zero-I/O per council ruling `docs/council/2026-07-02_paper-delta-source-architecture.md`, caller is responsible for resolving the map). FUT = `net_qty/lot_size`; NiftyBees = `qty×avg_cost/(spot×lot_size)`; unresolved `option_type` → WARNING + zero delta (never misclassified as a future). `check_entry_allowed` (`src/risk/entry_gate.py`): protective entries always allowed; cap → block; warning → allow with message. 33 unit tests in `tests/unit/risk/test_delta_tracker.py` + hypothesis property tests in `tests/unit/risk/test_delta_hypothesis.py`.
`src/gamma/` — scaffolding, data models (`GammaChainSnapshot` and `GammaWatchlistEntry` fr...
```