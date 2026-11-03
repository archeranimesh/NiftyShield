# DS Chain Monitoring — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

Source of truth: the ruling in `DECISIONS.md` ("Data source routing …, 2026-10-07, council"), including Animesh's 2026-10-07 Q4 clarification. Where this file and the ruling disagree, the ruling wins.
The 2026-07-02 ruling (`docs/council/2026-07-02_paper-delta-source-architecture.md`) still holds: callers resolve a `position_deltas` map; `src/risk/` stays pure and gets no I/O.

---

## DSN-1 — Token-staleness alert

**Files to change / create:**
- `src/auth/dhan_verify.py` (or the existing token-verify path — find it with `search_graph("dhan_verify")`) — expose token age / validity without logging the token.
- `scripts/healthcheck.py` — add a Dhan token line.
- `src/client/source_health.py` (from DSC-3) — wire the 806 / stale-token alert; the alert is once per incident, not per call.
- `tests/unit/` — alongside the touched modules.

**Before any code:** `LOGGING.md`; `get_code_snippet` for the healthcheck structure; `src/notifications/CLAUDE.md` (non-fatal contract, MarkdownV2 escaping). `DSM-1` `roll_checks.md` for response
shapes.

**What to implement:** detect a missing, expired or invalid token (and 806) before a Dhan chain call, alert via Telegram once, mark chain-on-Dhan unhealthy through the DSC-3 health state, and show
token age in the healthcheck. **Alert only; programmatic renewal is post-roll (`ds-router-migration/` DSR-4).**

**Tests:** stale-token fixture alerts once; 806 fixture alerts once; token value never appears in a captured log line; a notifier failure does not raise.

**Commit:** `feat(client): alert on stale Dhan token or lapsed subscription`

---

## DSN-2 — Yearly monitor and snapshot read path, with provenance

**Files to change / create:**
- The yearly monitor and snapshot code path (locate with `trace_path` from `StrategyMonitor` and `paper_snapshot`; the yearly book arrives with `yearly-ops-wiring/`, so this task wires the injected
  `ChainSource` and persistence, not new strategies). Sequence after `yearly-foundation` YF-5: both edit `track_snapshot` / `paper_snapshot` namespace sites (28 in `paper_3track_snapshot.py`,
  `yearly-foundation/audit.md`), so doing DSN-2 first duplicates or conflicts with that work. DSN-3 and DSN-5 also act on the yearly monitor and follow `yearly-ops-wiring/` registration, or use a test
  harness until it lands.
- `src/paper/store.py` — additive columns per `schema.md`, migration following the existing pattern.
- `docs/plan/data-source-routing/ds-chain-monitoring/schema.md` — already written; tick nothing there.
- `tests/unit/paper/`, `tests/unit/strategy/` — extend.

**Before any code:** read `DB_REGISTRY.md` first; `get_code_snippet("PaperLegSnapshot")` and the overlay snapshot model; `src/paper/CLAUDE.md`; `src/strategy/CLAUDE.md`.

**What to implement:**

1. The yearly monitor and snapshot paths take an injected `ChainSource`; delta for held contracts is looked up by `ContractRef`, not by broker key.
2. Build the `position_deltas` map (keyed by Upstox `instrument_key`) from the `ChainSnapshot` and pass it to `PortfolioDeltaTracker.aggregate_delta` unchanged.
3. Persist `delta_source` and `delta_asof` per leg and `chain_source` and `chain_fetched_at` per overlay snapshot, for both the monthly and the yearly book from DSN-2 onward (decided 2026-11-03;
   monthly rows record `upstox`). Rows written before DSN-2 stay `NULL`.
4. A pre-existing yearly position must have an explicit recorded source before the monitor acts on its delta.
5. New yearly code adds no direct `UpstoxMarketClient` chain import.
6. Monthly `greeks_freshness_bound_s` stays 184 s (2 x 90 s cadence + one 4 s Dhan slot), signed off by Animesh 2026-11-03. It is a deliberate floor: monthly reads Upstox, whose Greeks are live, so
   the bound only gates a future Dhan fallback. Do not tighten it or special-case monthly; `validate_tenor_policy` rejects anything below the formula minimum.

**Tests:** yearly leg delta comes from Dhan when Upstox is all-zero and the row records it; monthly path writes `upstox` provenance and its routing, gates and decisions are otherwise unchanged (any
test pinning a monthly snapshot row is updated deliberately for the new fields); an old row reads as unknown provenance.

**Review:** `code-reviewer` and `greeks-analyst`.

**Commit:** `feat(paper): record chain and delta provenance for yearly legs`

---

## DSN-3 — Stale-Greeks policy by action class

**Files to change / create:**
- A pure policy module (placement decided with the `OverlayTenorPolicy` registry from YF-3; staleness is policy data, not a branch in the monitor).
- The monitor's action dispatch for yearly legs.
- `tests/unit/strategy/` — new policy tests.

**Before any code:** `DECISIONS.md` ruling table (Q4 row); `get_code_snippet("OverlayTenorPolicy")` once YF-3 exists.

**What to implement (ruling Q4 + Animesh clarification):**

1. **Delta-dependent actions** — new entries, rolls and re-entries gated on delta, delta-stop exits, `check_entry_allowed` — run on live routed delta only. With none: do nothing and alert.
2. **Delta-independent automation** — profit target, DTE and time exits, expiry settlement, LTP P&L — keeps running without Greeks. "Delta available" is always the shared `has_usable_delta(chain,
   held_refs)` from DSC-1; do not write a second zero-delta check. Config rule for this story and DSN-4: values that differ by tenor (cadence, backstop multiple, flip tolerance, staleness limits) live
   in the `OverlayTenorPolicy` registry; only global switches live in `Settings`. DSN-4's `greeks_*` names follow that rule.
3. **Last-known delta from the capture store** serves degraded aggregation (age up to 1 trading day) and labelled display (up to 3). Beyond 3 trading days: unavailable, fail closed.
4. **The +/-1 approximation is banned** from yearly gates, stops and roll decisions; it may be computed for a diagnostic line only.
5. **Alert** when the newest usable delta is older than 1 trading day.
6. **Backstop (alert-only in paper):** while Greeks are unavailable, watch each open yearly short leg on a delta-independent trigger — premium multiple (LTP vs entry premium) or spot distance to
   strike — and alert when breached. Decided 2026-11-03: premium multiple only, alert at LTP >= 2.5x entry premium on the CC and the Collar's short call (copied from monthly CC, tuned from paper
   data); no spot-distance trigger yet; PP and the Collar's put leg get no backstop (hedges). The 2.5 lives in the yearly tenor policy registry.
7. Trading-day ages use `src/market_calendar/`.
8. No local Black '76 or other model here.

**Tests:** each fallback step and both cutoffs; delta-dependent action refuses and alerts, delta-independent action proceeds; the +/-1 value never reaches `check_entry_allowed`; backstop fires on a
fixture breach and is silent below threshold.

**Review:** `code-reviewer` and `greeks-analyst`.

**Commit:** `feat(strategy): stale-Greeks policy by action class for yearly legs`

---

## DSN-4 — Monitor cadence

**Files to change / create:**
- `OverlayTenorPolicy` registry (YF-3) — add a cadence field; yearly value set here (decided 2026-11-03: 3600 s, hourly), monthly pinned to today's value.
- The cadence, freshness bound, cache and action ages (3 and 1 trading days) are tenor-dependent, so they sit in the `OverlayTenorPolicy` registry with the cadence field; `src/config.py` gains only a
  global override if one is needed, named in the same style as DSC-4. Do not state the same value in both places.
- `tests/unit/` — extend.

**What to implement:** freshness bound = at least 2 x cadence plus one 4 s throttle slot; validate at startup and reject inconsistent config (for example a 120 s bound with a 300 s cadence). One Dhan
chain call per cycle, through the shared throttle (DSC-5); the 4 s slot is read from `market_data.chain.dhan_min_interval_s`, not restated.

**Tests:** monthly cadence pinned; yearly cadence keeps calls at least 4 s apart; inconsistent bound rejected.

**Commit:** `feat(strategy): yearly monitor cadence and freshness-bound validation`

---

## DSN-5 — Source-flip seam

**Files to change / create:** the monitor's source-selection step, the persistence added in DSN-2, `tests/unit/strategy/`.

**What to implement (ruling Q3):**

1. While a position is on Dhan Greeks, the monitor also reads the Upstox chain (dual read) to detect recovery.
2. Flip the position's active Greeks source Dhan to Upstox only after **2 consecutive trading days** of non-zero Upstox delta on its **held** `ContractRef`s, checked with `has_usable_delta(chain,
   held_refs)` (DSC-1). No DTE trigger. The two source ids are `SourceId` values and the 0.05 / 25% band below is a registry value, not a literal in the monitor.
3. On the flip snapshot persist both deltas. If they differ by more than 0.05 absolute or 25% relative, suppress delta stops, delta re-entry and delta entry gates for that position for **that session
   only**, log a WARNING, and still snapshot both numbers.
4. Collar legs sharing an expiry use the same source.
5. The first dual-read week is logged with both providers' values so the provisional band can be revised.

**Tests:** 2-day trigger (1 day does not flip); suppression applies only to the flip session; both deltas persisted; collar legs flip together.

**Review:** `code-reviewer` and `greeks-analyst`.

**Commit:** `feat(strategy): switch yearly Greeks source at a logged seam`
