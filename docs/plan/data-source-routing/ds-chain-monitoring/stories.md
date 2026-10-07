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
  `ChainSource` and persistence, not new strategies).
- `src/paper/store.py` — additive columns per `schema.md`, migration following the existing pattern.
- `docs/plan/data-source-routing/ds-chain-monitoring/schema.md` — already written; tick nothing there.
- `tests/unit/paper/`, `tests/unit/strategy/` — extend.

**Before any code:** read `DB_REGISTRY.md` first; `get_code_snippet("PaperLegSnapshot")` and the overlay snapshot model; `src/paper/CLAUDE.md`; `src/strategy/CLAUDE.md`.

**What to implement:**

1. The yearly monitor and snapshot paths take an injected `ChainSource`; delta for held contracts is looked up by `ContractRef`, not by broker key.
2. Build the `position_deltas` map (keyed by Upstox `instrument_key`) from the `ChainSnapshot` and pass it to `PortfolioDeltaTracker.aggregate_delta` unchanged.
3. Persist `delta_source` and `delta_asof` per leg and `chain_source` and `chain_fetched_at` per overlay snapshot, from the first Dec 2027 read.
4. A pre-existing yearly position must have an explicit recorded source before the monitor acts on its delta.
5. New yearly code adds no direct `UpstoxMarketClient` chain import.

**Tests:** yearly leg delta comes from Dhan when Upstox is all-zero and the row records it; monthly path writes `NULL` provenance and is otherwise unchanged; an old row reads as unknown provenance.

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
2. **Delta-independent automation** — profit target, DTE and time exits, expiry settlement, LTP P&L — keeps running without Greeks.
3. **Last-known delta from the capture store** serves degraded aggregation (age up to 1 trading day) and labelled display (up to 3). Beyond 3 trading days: unavailable, fail closed.
4. **The +/-1 approximation is banned** from yearly gates, stops and roll decisions; it may be computed for a diagnostic line only.
5. **Alert** when the newest usable delta is older than 1 trading day.
6. **Backstop (alert-only in paper):** while Greeks are unavailable, watch each open yearly short leg on a delta-independent trigger — premium multiple (LTP vs entry premium) or spot distance to
   strike — and alert when breached. Thresholds come from the yearly tenor policy (open decision 1 in `yearly-overlays/README.md`); until set, the backstop is off and the task records that.
7. Trading-day ages use `src/market_calendar/`.
8. No local Black '76 or other model here.

**Tests:** each fallback step and both cutoffs; delta-dependent action refuses and alerts, delta-independent action proceeds; the +/-1 value never reaches `check_entry_allowed`; backstop fires on a
fixture breach and is silent below threshold.

**Review:** `code-reviewer` and `greeks-analyst`.

**Commit:** `feat(strategy): stale-Greeks policy by action class for yearly legs`

---

## DSN-4 — Monitor cadence

**Files to change / create:**
- `OverlayTenorPolicy` registry (YF-3) — add a cadence field; yearly value set here (proposal: 300 s or slower), monthly pinned to today's value.
- `src/config.py` — `yearly_chain_monitor_cadence_s`, `greeks_fresh_max_age_s`, `greeks_cache_max_age_trading_days` (3), `greeks_action_max_age_trading_days` (1).
- `tests/unit/` — extend.

**What to implement:** freshness bound = at least 2 x cadence plus one 4 s throttle slot; validate at startup and reject inconsistent config (for example a 120 s bound with a 300 s cadence). One Dhan
chain call per cycle, through the shared throttle (DSC-5).

**Tests:** monthly cadence pinned; yearly cadence keeps calls at least 4 s apart; inconsistent bound rejected.

**Commit:** `feat(strategy): yearly monitor cadence and freshness-bound validation`

---

## DSN-5 — Source-flip seam

**Files to change / create:** the monitor's source-selection step, the persistence added in DSN-2, `tests/unit/strategy/`.

**What to implement (ruling Q3):**

1. While a position is on Dhan Greeks, the monitor also reads the Upstox chain (dual read) to detect recovery.
2. Flip the position's active Greeks source Dhan to Upstox only after **2 consecutive trading days** of non-zero Upstox delta on its **held** `ContractRef`s. No DTE trigger.
3. On the flip snapshot persist both deltas. If they differ by more than 0.05 absolute or 25% relative, suppress delta stops, delta re-entry and delta entry gates for that position for **that session
   only**, log a WARNING, and still snapshot both numbers.
4. Collar legs sharing an expiry use the same source.
5. The first dual-read week is logged with both providers' values so the provisional band can be revised.

**Tests:** 2-day trigger (1 day does not flip); suppression applies only to the flip session; both deltas persisted; collar legs flip together.

**Review:** `code-reviewer` and `greeks-analyst`.

**Commit:** `feat(strategy): switch yearly Greeks source at a logged seam`
