# Dhan Far-Expiry Chain (Dec 2027 adapter + daily capture) — epic index

> Brings Dhan's live option chain into the system as a Greeks source for far-dated expiries where Upstox returns zero, captures it daily so liquidity history exists, and turns that history into a
> coded liquidity gate and roll window. One epic because adapter, capture and gate form one chain and the capture has a hard calendar deadline.

## Why this epic exists

Upstox returns zero Greeks for far expiries (zero on every row for Dec 2026 until 2026-09-21, about 99 DTE; the exact flip is not pinned down). The yearly overlays (`yearly-overlays/`) must open Dec
2027 legs after Dec 2026 expires, and Animesh's working assumption is that Dec 2027 gains enough liquidity once Dec 2026 is gone. Dhan's live chain has deltas where Upstox does not, but it is a
snapshot with no history, so liquidity can only be observed forward — daily, from now.

## Scope decisions

Decided with Animesh on 2026-10-06:

- **2026 stays on Dec 2026; Dec 2027 takes over after it expires.** Dhan is needed only for Dec 2027; the Dec 2026 chain should work from Upstox (confirm with the DA-1 check).
- **Assumption, to be tested not trusted:** Dec 2027 liquidity will be sufficient after Dec 2026 closes. The capture is the test; the gate is how "adjust based on liquidity" is applied in code.
- **Capture is forward only.** Dhan's expired-options data has no delta or bid/ask and nothing past about 90 DTE (POC verdict, archived at `docs/archive/plan/dhan-data-poc/findings.md`); it cannot
  backfill.

## Verified facts that shape the design (POC findings, 2026-10-05)

- Live chain returns every listed strike with LTP, IV, OI, volume, top bid/ask, delta, gamma, theta, vega. 18 expiries listed to 2031-06-24.
- Rate limit: one unique request per 3 s; error 805 seen at a 3.2 s gap, so allow 4 s or more. Plan lapses 2026-11-04 and auto-renews.
- Dec 2026 chain: 249 strikes, delta 0.15 on both sides, liquid. Dec 2027: 39 strikes, 22 with real quotes; call deltas absent below about 0.4-0.5 from Sep 2027 on (puts fine).
- There is no Dhan chain client in `src/` (`src/dhan/` is holdings/positions only). Probes live in `scratch/data_probes/` (`2026-09-22_dhan_option_chain_probe.py`, `2026-10-05_*`) — SCRATCH.md says
  extract, not re-derive.
- Existing prior art to extend, not duplicate: `src/instruments/strike_selector._apply_liquidity_gate` (spread % of mid only), `parse_upstox_option_chain` + `OptionChain`/`OptionLeg`, `src/backtest`
  `ChainWriter`/`ChainReader` (Parquet + DuckDB).

## Architecture and design review

- **DIP / ISP:** callers depend on a small chain-source `Protocol`; Upstox and Dhan are implementers; a composite picks Dhan only when Upstox Greeks are all zero. No caller learns about brokers.
- **SRP:** the rate limiter is its own injectable collaborator; parsing is a pure function; the capture writer owns persistence; the gate owns thresholds.
- **Prior-art audit before storage:** `far-expiry-capture/` FC-1 decides Parquet (`ChainWriter`) versus a SQLite table against `DB_REGISTRY.md` before any DDL; a `schema.md` is added only if SQLite
  wins.
- **OCP:** gate thresholds are per-expiry-type config; the existing gate's callers keep their default behaviour.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `dhan-chain-adapter/` | Renewal decision, fixtures, `DhanMarketClient`, chain-source selection | 🔄 In progress | — | — |
| `far-expiry-capture/` | Storage decision, daily capture entrypoint, cron, liquidity report | 🔄 In progress | `dhan-chain-adapter` | — |
| `far-expiry-liquidity-gate/` | Calibrated gate with fallback ladder, roll-window decision | ⬜ Not started | `far-expiry-capture` (data) | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`.

## Open decisions for Animesh

1. **Plan renewal.** The Dhan data plan lapses 2026-11-04 and auto-renews unless cancelled. Keeping it through at least the Dec 2026 roll is recommended (tracked as DA-0).
2. **Capture length before calibrating.** Default: at least 15 trading days of captured Dec 2027 history before FG-1 proposes thresholds; adjust if you want a longer window.
3. **Storage.** Default recommendation for FC-1: reuse `ChainWriter` Parquet if it can hold bid/ask/Greeks per strike per snapshot, otherwise one SQLite table. FC-1 reports back before building.

## Cross-cutting constraints

- Default `pytest` is offline; the live Dhan token is used only by marker-gated tests and by the cron entrypoints. No credentials, tokens or client ids in docs, fixtures or logs.
- Every chain call is at least 4 s after the previous one; a 805 response backs off and is logged, never retried in a tight loop.
- Monetary and Greek values are `Decimal` end to end; stored as `TEXT` if SQLite.
- New entrypoints follow `LOGGING.md` (`_SCRIPT_NAME`, `setup_logging()`); new package directories carry `__init__.py` and trigger a graph re-index.
- Changes touching option-chain parsing or delta/gamma fields trigger `greeks-analyst`.

## Supersession / coordination

- Supplies Greeks to `yearly-overlays/` for Dec 2027; `yearly-overlays/yearly-validation/` YV-5 lists this epic's outputs as roll preconditions.
- FG-3 writes the yearly `roll_dte` into the policy registry created by `yearly-overlays/yearly-foundation/` YF-3.
- The POC story `dhan-data-poc` is closed and archived; this epic builds on its findings and does not reopen it.
- `data-source-routing/` (2026-10-07) takes over the seam work this epic's DA-4 handed off: contract identity, `ChainSnapshot` and capability routing. `far-expiry-capture/` keeps calling
  `DhanMarketClient` directly and must not wait on it. The capture store is the candidate last-known-delta cache for the stale-Greeks policy, and Dhan token freshness (`ds-chain-monitoring` DSN-1) is
  a precondition for the capture cron staying healthy.

## Epic done when

- **dhan-chain-adapter** — `DhanMarketClient` returns an `OptionChain` for Dec 2027 offline from a fixture; the composite source falls back to Dhan only on all-zero Upstox Greeks; renewal decision
  recorded.
- **far-expiry-capture** — one capture per trading day runs from cron, 4 s spacing, with a heartbeat the healthcheck reads; the daily report shows target-delta strike liquidity.
- **far-expiry-liquidity-gate** — gate thresholds come from captured data; the fallback ladder is tested; yearly `roll_dte` set with the evidence recorded.
