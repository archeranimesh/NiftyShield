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
