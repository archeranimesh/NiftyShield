# DS Router Migration — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## DSR-1 — Prior-art audit and cluster plan

**Files to change / create:**
- `docs/plan/data-source-routing/ds-router-migration/audit.md` — table: site (file:line), capability used (quote / candles / chain / parse), disposition (migrate / exception), cluster id. No
  checkboxes.
- `docs/plan/data-source-routing/ds-router-migration/tasks.md` — append one `DSR-n` line per cluster (at most 3 files each).

**Before any code (graph queries):**
- `search_code("from src.client.upstox_market import")` scoped outside `src/client/`, `search_code("parse_upstox_option_chain")`, `search_graph("UpstoxLiveClient")`.
- `trace_path` for any site whose capability is unclear.
- Read `docs/refactor/code-deduplication-and-taxonomy.md`; note any existing helper that already abstracts a fetch.

**What to implement:**

1. Enumerate every site (recon on 2026-10-07: 27 importers, 15 parser callers; re-count, do not trust).
2. Classify each by capability and flag any that compares values across sources.
3. Group into clusters of at most 3 files that can migrate and be tested together; mark deliberate exceptions with a reason (for example a script that must stay Upstox-only).
4. Append the cluster task lines.

**Tests:** none (docs-only).

**Commit:** `docs(plan): audit direct upstox importers for router migration`

---

## DSR-2 .. DSR-last (outline — specced from the DSR-1 audit and the absorbed ruling)

- **DSR-2:** `QuoteSource` / `CandleSource` implementations for Upstox (wrap `UpstoxLiveClient`) and Dhan (`DhanMarketClient` quote and candle calls, 4 s / rate-limit aware), a registry-`dict` router
  and config in `src/client/` + `src/config.py` + `factory.py`. Default config reproduces Upstox-only behaviour.
- **DSR-3..n:** per cluster — inject the router instead of constructing `UpstoxMarketClient`; no behaviour change under default config.
- **DSR-last:** a health tracker per capability: 806 or stale token marks the capability unhealthy, falls back to the next source, alerts once, and re-probes on a backoff. Reuses DSN-1's alert path.
