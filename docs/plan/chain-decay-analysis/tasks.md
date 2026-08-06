# Chain Delta/Decay Analysis — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/chain-decay-analysis/stories.md`.

---

- [ ] **CDA-1** — Reader/loader helper: pull a trading day's earliest and latest intraday
      snapshot (within market hours) for the monthly bucket via `ChainReader`, join into a single
      per-(strike, option_type) frame with both timestamps' fields. Excludes degenerate rows
      (`abs(delta) == 1.0 and gamma == 0.0`, the confirmed "no tradeable quote" pattern).
- [ ] **CDA-2** — Decomposition math: `expected_move = delta*Δspot + 0.5*gamma*Δspot**2`,
      `theta_component = theta*Δt`, `vega_component = vega*ΔIV`, `residual = actual_premium_change
      - expected_move - theta_component - vega_component`. Pure function(s), no I/O.
- [ ] **CDA-3** — Aggregate residual by strike / moneyness bucket across all available trading
      days (2026-06-01 onward), monthly bucket only. Output: a table (CSV or similar) plus a short
      written summary of which strikes/moneyness bands show residual decay in excess of what
      theta/vega explain.
- [ ] **CDA-4** — Docs close: `CONTEXT.md` module entry (if a new `src/` module was added rather
      than a one-off `scripts/analysis/` script), `DECISIONS.md` entry summarizing the finding
      (does premium move track delta or not, which strikes decay faster), `TODOS.md` session log
      line, and update this story's row in `docs/plan/README.md` to reflect status.
