# Dhan Far Expiry Chain Findings

## DA-0 Renewal Decision (Animesh)
<!-- Empty section for DA-0 -->

## DA-1 Discovery Results
Date: 2026-10-06

**Upstox Dec 2026 Check**
- Expiry Date: 2026-12-29
- Exact DTE: 84
- Greeks Present: True

**Dhan No-Delta Encoding** In the raw Dhan JSON chain, missing or uncomputable Greeks are encoded by providing the `"greeks"` dictionary but with `"delta": 0` (and `0` for other Greeks like theta,
gamma, vega). Populated rows have floating-point values for `"delta"`.

## DA-4 Relocation (2026-10-07, Animesh)
DA-4 (wire `CompositeChainSource` into the overlay bootstraps) is **not** a drop-in swap and moves to `yearly-overlays/yearly-foundation/` YF-6.
- `ChainSource.get_chain` returns a parsed `OptionChain`; `auto_cc_bootstrap` / `auto_collar_bootstrap` / `auto_pp_bootstrap` consume the **raw Upstox row list** (`filter_strikes_by_delta`,
  `rank_strikes`, `_apply_liquidity_gate`, `run_collar_mode`) because `OverlayConfig` needs `instrument_key`. `OptionLeg` has no `instrument_key`, and Dhan identifies contracts by security id.
- Wiring therefore needs a (strike, side, expiry) -> Upstox `instrument_key` resolver (BOD `lookup`) and an `OptionChain` -> raw-row adapter.
- The bootstraps hardcode the monthly tenor, and Upstox already returns Greeks there (Dec 2026, DTE 84), so the Dhan fallback has no consumer until a far-expiry tenor exists (YF-4).
- Option 1 (adapter now) and option 3 (rewrite selection on `OptionChain`) were rejected; build the resolver once against the real yearly consumer.
