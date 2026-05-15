# Overlay Lot-Sizing Analysis — 2026-05-12

## Context

NiftyBees (Spot) track experienced a sharp intraday loss on 2026-05-12. The 3-track overlay
framework (PP + CC + Collar applied simultaneously to `paper_nifty_spot`) partially offset the
loss. This note captures the per-strategy P&L breakdown and the lot-sizing math for full
loss coverage — as a reference for future position sizing decisions.

---

## Positions Active (entered 2026-05-11, 1 lot = 65 qty each)

| Leg | Type | Instrument Key | Entry Price | 2026-05-12 P&L |
|-----|------|---------------|-------------|----------------|
| `overlay_cc` | SELL CE | NSE_FO\|71474 | ₹221.38 | +₹6,722.95 |
| `overlay_collar_call` | SELL CE | NSE_FO\|71474 | ₹220.62 | +₹6,673.55 |
| `overlay_collar_put` | BUY PE | NSE_FO\|58627 | ₹92.12 | +₹3,654.95 |
| `overlay_pp` | BUY PE | NSE_FO\|58627 | ₹92.17 | +₹3,651.70 |
| **Total Overlay** | | | | **+₹20,703.15** |
| `base_etf` (NiftyBees) | Long ETF | | | **−₹31,370.45** |
| **Net P&L** | | | | **−₹10,667.30** |

Overlay absorbed **65.9%** of the base loss.

---

## Per-Strategy Per-Lot Contribution

| Strategy | P&L / lot (1 lot) | Lots to cover ₹31,370 | Rounded |
|----------|------------------|----------------------|---------|
| PP alone (BUY PE) | +₹3,651.70 | 8.59 | **9 lots** |
| CC alone (SELL CE) | +₹6,722.95 | 4.67 | **5 lots** |
| Collar (BUY PE + SELL CE) | +₹10,328.50 | 3.04 | **3 lots** |

---

## Key Structural Insight: CC Is Not Downside Protection

The CC (SELL CE) generated nearly 2× the P&L of the PP (BUY PE) yesterday because:

- The CE was sold for ₹221 — a high-premium strike reflecting elevated call skew.
- When Nifty fell, the CE eroded from ₹221 to ~₹118 — premium decay + delta collapse.
- This looks like protection, but the payoff profile is **inverted from what you want**.

If Nifty had risen 1% instead of falling, the CC would have shown ₹3,000–₹5,000 in losses,
compounding the problem rather than solving it. Running 5 lots of CC to "hedge" 1 lot of
NiftyBees creates 5× synthetic short exposure on the upside — that is an aggressive overwrite,
not a hedge.

**The ₹221 CE premium vs ₹92 PE premium asymmetry** is a call skew effect. It makes CC
appear more efficient at offsetting losses in a down-move scenario, but the protection is
incidental and directionally unreliable.

---

## Practical Conclusion

| Objective | Best instrument | Why |
|-----------|----------------|-----|
| Pure downside protection | **9 lots PP** | Full delta hedge via long PE; expensive but honest |
| Capital-efficient protection | **3 lots Collar** | Short CE funds the long PE; ETF position covers the CE cap |
| Income generation (not protection) | **5 lots CC** | Works in down/flat markets; creates upside liability |

**3 lots of collar is the most defensible answer for protection.** The short CE leg of the
collar is covered by the long ETF, so there is no uncapped upside liability. The CE premium
collected partially subsidises the PE cost, making the collar structurally cheaper than PP
alone at comparable coverage.

CC-only as a hedge is a false reading of yesterday's P&L. It paid because the market fell —
not because of a protection mechanism.

---

## Caveats

- All figures are from a single day's move. Lot sizing based on one realised move is not
  a robust sizing rule — the PE delta at entry was ~0.22, meaning the put only recovers
  ₹0.22 per ₹1 of spot move. A larger or faster drawdown improves PP efficiency; a slow
  grind down with theta decay erodes it.
- The CE and PE are on the same expiry. Roll costs and DTE matter for multi-month coverage.
- These are paper trade figures. Live execution will have bid-ask slippage, margin
  requirements per lot, and STT/brokerage that change the break-even lot count.

---

*Derived from live DB query on `paper_leg_snapshots` for `paper_nifty_spot`, date 2026-05-12.*
*Analysis session: 2026-05-13.*
