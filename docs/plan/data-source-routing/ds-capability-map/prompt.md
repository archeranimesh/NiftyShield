# DS Capability Map — prompt

> Verify what each broker can actually supply, run the council on the routing seam, and absorb the ruling so the code stories have a spec.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

`broker-abstraction/` BA-0 was meant to gate the abstraction on real data-quality differences and was never run. The archived Dhan POC answered part of it for Dhan. Several load-bearing facts are
still unknown or secondhand: whether the Dhan token can be renewed programmatically, whether India VIX and batch LTP work on Dhan, whether Dhan can serve order margin, and what the live feed and MCP
pages actually say (the pages were unreachable from the planning session; only summaries pasted by Animesh exist). Routing built on guesses repeats BA-0's failure mode.

## Scope guard

**In bounds:** docs under `docs/plan/data-source-routing/` and `DECISIONS.md` / `docs/council/README.md` rows after the council ruling; read-only probe scripts under `scratch/` (SCRATCH.md naming).

**Out of bounds:** any `src/` change; any credential, token or client id in a doc or fixture; calling any order endpoint; wiring the Dhan MCP connector or Agent Skills pack into the runtime.

## Design review

Docs-only story; no new module, class or seam. DSM-1 inputs the epic's capability protocols (ISP split) but does not define them.

## Session-start load hints

`docs/plan/data-source-routing/README.md`. `docs/archive/plan/dhan-data-poc/findings.md`. `REFERENCES.md` (instrument keys, India VIX key). `SCRATCH.md`. `docs/council/README.md`. Existing probes in
`scratch/data_probes/`.

## Task overview

DSM-1 capability matrix (verify the unknowns) → DSM-2 run the council (Animesh) → DSM-3 absorb the ruling and spec the code stories.

## Definition of done

`capability_matrix.md` has one row per capability x broker with source, limits, token lifecycle and Greeks model, each cell marked verified-by-probe / verified-by-doc / unverified; the council ruling
is in `DECISIONS.md`; `ds-chain-seam/stories.md` and `ds-chain-monitoring/stories.md` no longer say "specced after council".

## Perspectives not covered

Cost of the Dhan plan against value is not modelled beyond the two listed prices. Latency of Dhan LTP against Upstox LTP for the 30 s monitor cadence is not measured here unless DSM-1 adds a probe.
