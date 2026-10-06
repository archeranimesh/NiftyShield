# Dhan Chain Adapter — prompt

> A `DhanMarketClient` that returns the repo's `OptionChain` from Dhan's live chain, and a chain-source selector that uses Dhan only where Upstox Greeks are all zero.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Upstox returns zero Greeks for far expiries; Dhan does not. There is no Dhan chain client in `src/` today, only scratch probes. This story promotes the probe into a tested client and gives callers one
chain-source seam so the yearly overlays never need to know which broker supplied the Greeks.

## Scope guard

Read-only market data. No orders, no holdings. No storage (that is `far-expiry-capture/`). No threshold logic (that is `far-expiry-liquidity-gate/`). Never log or commit tokens or client ids.

## Design review

DIP/ISP: a small chain-source `Protocol`; Upstox and Dhan implement it; a composite does the fallback. SRP: injectable rate limiter, pure `parse_dhan_option_chain`. Prior-art: read the two probes and
`parse_upstox_option_chain` before writing a parser; reuse `OptionChain`/`OptionLeg`, add no new chain model.

## Session-start load hints

`docs/archive/plan/dhan-data-poc/findings.md` (rate limit, fields, error codes), `scratch/data_probes/2026-09-22_dhan_option_chain_probe.py`, `src/client/CLAUDE.md`, `src/auth/dhan_login.py` (token
flow), `SCRATCH.md`, `REFERENCES.md`.

## Task overview

DA-0 renewal decision (Animesh) → DA-1 fixtures + Upstox Dec 2026 check → DA-2 client + parser → DA-3 chain-source selection.

## Definition of done

Offline: Dec 2027 fixture parses to an `OptionChain` with non-zero deltas; the composite uses Dhan only on all-zero Upstox Greeks; a 805 response backs off. Live: one marker-gated read works.

## Perspectives not covered

Dhan token lifecycle: the manual daily token login is outside this story; an expired token must fail loudly, not silently fall back to zero Greeks.
