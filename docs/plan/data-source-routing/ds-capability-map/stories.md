# DS Capability Map — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## DSM-1 — Capability matrix

**Files to change / create:**
- `docs/plan/data-source-routing/ds-capability-map/capability_matrix.md` — the matrix. No checkboxes.
- `scratch/data_probes/<date>_<topic>.py` — only for probes that need a live call; follow `SCRATCH.md`, extract rather than re-derive. Read-only calls only.

**Before any code:**
- Read `docs/archive/plan/dhan-data-poc/findings.md` and the existing `scratch/data_probes/` scripts; reuse them.
- `search_code("dhan_access_token")`, `search_graph("DhanMarketClient")` — how the token is read today.

**What to produce:**

One row per capability x broker, columns: source, limits, token lifecycle, Greeks model, verification status (probe / doc / unverified), owner if unverified.

Capabilities: live LTP (single and batch ceiling), live option chain with Greeks, historical candles (daily, intraday, lookback), expired options, India VIX, instrument master (format, refresh), order
margin (single and basket), market stream (feed modes, limits), and the token / subscription lifecycle.

Questions that must be closed or explicitly left open:

1. **Dhan token renewal.** Can a token be renewed or minted programmatically (renew endpoint, API-key flow, TOTP flow)? If renewal needs a still-valid token, say so. Cite the primary doc page.
2. **India VIX on Dhan.** Segment and security id, or "not available".
3. **Batch LTP ceiling** on both brokers and the rate limit.
4. **Order margin on Dhan.** Endpoint and whether it needs the paid plan.
5. **805 / 806 behaviour.** Exact response shape and what a lapsed plan returns.
6. **Live feed.** Confirm against the primary page: modes, fields (confirm no Greeks), connection and instrument limits, whether it needs the paid plan.
7. **Upstox far-expiry Greeks flip.** DDP-5 (`docs/archive/plan/dhan-data-poc/findings.md`) measured one expiry: Dec 2026 deltas went from zero to non-zero between 2026-09-29 15:55 and 2026-09-30
   09:51 (DTE 91 to 90); Jun 2027 stayed zero on every stored day (DTE 343-382). Confirm on a second expiry from stored chains; Dec 2027 would flip at about 2027-09-29 if 90 DTE holds.
8. **Dhan MCP and Agent Skills.** Record only what the primary pages state and whether either is relevant to runtime; both are out of scope for the data path.

The primary pages may be unreachable from a cloud session (egress policy). If so, mark those cells `unverified — owner Animesh` rather than filling them from a summary.

**Tests:** none (docs and read-only probes).

**Commit:** `docs(plan): capability matrix for data-source routing`

---

## DSM-2 — Run the council

**Files to change / create:** none by Claude. Output lands at `docs/council/<date>_data-source-routing.md`.

**What to do (Animesh):**

1. Start the council server: `cd tools/llm-council && ./start.sh`.
2. If DSM-1 closed any question in `council/question.md` §Mechanics, update `question.md` first so the council is not asked about a settled fact.
3. `bash docs/plan/data-source-routing/council/submit.sh` (add `--dry-run` to the `ask_council` call for a preview).
4. Commit the output file.

**Commit:** `docs(council): data-source-routing ruling`

---

## DSM-3 — Absorb the ruling

**Files to change / create:**
- `DECISIONS.md` — one row per Summary Table decision, source = the council file.
- `docs/council/README.md` — a row in §"Topics Already Covered".
- `docs/plan/data-source-routing/ds-chain-seam/stories.md`, `ds-chain-monitoring/stories.md` — replace the "specced after council" stubs with full specs from the Summary Table.
- `docs/plan/data-source-routing/README.md` — amend open decisions 2 and 4 with the outcome.

**Before any code:** invoke `protocol-reference` §1; read Stage 3 first, then Dissenting Notes and Additional Rules Surfaced.

**What to do:**

1. Follow §1's mandatory post-read actions in order; do not spec any code task until `DECISIONS.md` reflects the ruling.
2. Log Dissenting Notes under "Noted, deferred".
3. If the ruling adds a persisted column, add a `schema.md` to the owning story and check `DB_REGISTRY.md` first.

**Tests:** none (docs-only).

**Commit:** `docs(decisions): absorb data-source-routing council ruling`
