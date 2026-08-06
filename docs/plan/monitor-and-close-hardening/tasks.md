# Monitor & Close-Path Hardening — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line, top to bottom. That is your only task
> for this session. Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full spec for each task is inline below (no separate `stories.md` — grouped items are small
> enough to spec directly here).

Grouped rationale: all four tasks below touch `StrategyMonitor`'s tick loop or the auto-close/
leg-resolution path that feeds it — degraded observability (MC-1, MC-2) and degraded leg
resolution (MC-3, MC-4) are the same class of "the daemon silently loses fidelity on some
positions" risk. Each task is independently landable; no shared files between them.

---

- [x] **MC-1** — Dedupe `strategy_monitor.expiry_unresolved` firing twice per tick per
  unresolvable position. Spawned from TODOS.md (deferred from the 2026-07-20 silent-failure
  logging pass). `_fetch_chains` and `_group_positions_by_expiry` both independently call
  `_get_position_expiry` on the same position list each tick, so a degraded position logs the
  same WARNING twice with identical fields. Not a correctness bug (idempotent, no control-flow
  impact) but doubles log volume and could misread as two separate failures during incident
  triage. Flagged by advisory `@code-reviewer` pass (2026-07-20, persona-based).

  **Fix:** add a per-tick memoization cache on `_get_position_expiry` (keyed by
  `instrument_key`, cleared at the start of each tick), or consolidate the two call sites into
  one shared pre-computed dict passed to both. Prefer the memoization cache — smaller diff,
  no change to either caller's control flow.

  **Files:** the module owning `StrategyMonitor`'s tick loop (`get_code_snippet("StrategyMonitor")`
  first to confirm current location — CONTEXT.md/module tree may have moved since the TODOS.md
  entry was written), its test file.

  **Before any code:**
  ```
  git log --oneline -10 <StrategyMonitor file>
  search_graph("StrategyMonitor")
  search_code("_get_position_expiry")
  ```

  **Tests:** one asserting `_get_position_expiry` is called once per `(tick, instrument_key)`
  even when both `_fetch_chains` and `_group_positions_by_expiry` need the value; one confirming
  the WARNING itself still fires exactly once for a genuinely unresolvable position.

  **Commit:** `fix(strategy): dedupe expiry_unresolved double-log per tick` | SHA: 1239591

---

- [x] **MC-2** — Audit how long exit-signal gating was degraded across strategies other than
  `paper_ic_nifty_v1_monthly`. Spawned from TODOS.md (deferred from the 2026-07-20 `lookup`
  wiring fix). `scripts/monitor_daemon.py` never passed `lookup=` into `StrategyMonitor`, so
  `PROFIT_TARGET`/`LOSS_STOP`/any combined-mark-based signal was silently suppressed for every
  numeric-keyed position the daemon monitored — not just the one strategy that surfaced it. CSP,
  overlays, and all four IC V1/V2 expiry variants share the same `_get_position_expiry` path.

  **This is an audit, not a code fix** — no source change expected unless the audit finds a
  live position that sat past its threshold unnoticed, in which case open a new bug entry
  (do not silently correct P&L inline).

  **Steps:**
  1. Confirm the `lookup=` wiring fix itself is still in place (`git log`/`search_code("lookup=")`
     in `scripts/monitor_daemon.py` — do not assume the TODOS.md description is still current).
  2. Query `paper_trades`/`get_positions()` for every strategy's current combined-mark vs.
     threshold — pre-aggregate per Rule 1 (project `CLAUDE.md` Rule 1 — no raw dumps).
  3. Cross-reference against `logs/monitor_daemon.log` history for how far back the
     wrong-expiry `chain_fetched` pattern goes (see `DECISIONS.md` 2026-07-20 entry for the
     original find).

  **Deliverable:** a short findings note appended to `DECISIONS.md` (or a new
  `docs/bugs/bugs.md` entry if a real missed exit is found) — not a code commit unless a fix is
  required, in which case split that into its own task rather than bundling.

  **Commit (docs-only, if no fix needed):** `docs(strategy): audit exit-signal gating degradation window` | SHA: 500cd29

---

- [x] **MC-3a** — BUG-023: resolve the `ROLL_WING`/`PROFIT_LOCK_ZONE2` replacement leg's real
  `instrument_key` via BOD, instead of the current fabricated symbol-style key. Split out of the
  original MC-3 (2026-08-05 pre-implementation investigation) — see `docs/bugs/bugs.md` BUG-023
  for full root-cause detail. **Must land before MC-3b** — MC-3b's persistence would otherwise
  write an unresolvable key to `paper_trades`.

  **Affects:** `src/strategy/ic_nifty_v1.py::IronCondorV1._select_wing_roll_target`,
  `src/strategy/ic_nifty_v2.py::IronCondorV2._roll_result_to_signal`.

  **Before any code:**
  ```
  get_code_snippet("InstrumentLookup.search_options")   # reusable resolver, 3 existing callers
  git log --oneline -10 src/instruments/lookup.py
  ```

  **Fix:** replace the `f"NSE_FO|NIFTY{int(strike)}{option_type}"` construction in both files
  with `InstrumentLookup.search_options(underlying="NIFTY", strike=..., option_type=..., expiry=...)`
  (BOD-backed, already-resolved IC expiry as the filter); a strike absent from the same-expiry
  BOD file is treated as a failed candidate (same handling as an existing liquidity-gate miss),
  not an exception.

  **Tests:** BOD resolves a valid candidate strike to its real numeric key; strike present in
  the live chain scan but absent from BOD for that expiry is rejected as a candidate (not a
  crash); existing V1/V2 roll-target tests updated to assert against a real key shape, not the
  symbol-style placeholder.

  **Commit:** `fix(strategy): resolve ROLL_WING/PROFIT_LOCK_ZONE2 replacement key via BOD`
  | SHA: 30af733

  **Note:** also fixed the identical fabrication in V2's `_execute_partial_roll` (D3 partial
  roll new-leg keys) — same file, same defect class, feeds the same ROLL_WING path; found via
  `@code-reviewer`-substitute pass, not separately scoped, folded in rather than left half-fixed.
  A third occurrence in `IronCondorV2.enter()` (entry legs, not roll) was found and is
  **out of scope** — logged as BUG-023's sibling, `docs/bugs/bugs.md` BUG-024 (open, not fixed
  this session).

---

- [ ] **MC-3b** — IC-CLOSE-2: persist the close side of `ROLL_WING`/`PROFIT_LOCK_ZONE2` actions.
  Spawned from TODOS.md (deferred from the 2026-07-15 auto-close persistence fix). Same missing-
  persistence gap as the flatten actions (`CLOSE_FULL` etc., fixed 2026-07-15 via
  `close_ic_legs()`), but for roll actions: the old leg being replaced is filtered from the
  in-memory `positions` list without a DB write. Not yet symptomatic as of the last check (0
  occurrences of either action type in `logs/monitor_daemon.log`) but will silently no-op the
  same way once a roll signal fires. **Depends on MC-3a landing first** — strike selection
  itself already exists (`_select_wing_roll_target`/`_search_narrower_wing_candidate` in V1,
  `roll_utils.search_narrow_wing_replacement` in V2, both chain-derived); the only missing piece
  besides persistence was a valid key, which MC-3a provides.

  **Affects:** `src/strategy/ic_nifty_v1.py` (`ROLL_WING`), `src/strategy/ic_nifty_v2.py`
  (`ROLL_WING`, `PROFIT_LOCK_ZONE2`).

  **Before any code:**
  ```
  get_code_snippet("close_ic_legs")          # the existing flatten-action helper to mirror
  search_code("ROLL_WING")
  search_code("PROFIT_LOCK_ZONE2")
  git log --oneline -10 src/strategy/ic_close_executor.py
  ```

  **Tests:** roll-fires → old leg closed and persisted to `paper_trades`, new leg opened and
  persisted, atomic (single `record_trades` call, no partial-write window).

  **Commit:** `fix(strategy): persist ROLL_WING/PROFIT_LOCK_ZONE2 close side atomically`

---

- [ ] **MC-4** — Fix BOD resolution in CC / PP / Collar leg finders. Spawned from TODOS.md
  (remaining scope after the IC portion was fixed 2026-07-06, and after `_price_utils.py`/
  `overlay_closer.py`/`executor.py`/`nifty_track_comparison_v1.py` were fixed 2026-07-20).
  `src/strategy/cc_overlay_v1.py`, `src/strategy/pp_overlay_v1.py`,
  `src/strategy/collar_overlay_v1.py` each still carry their own separate, unfixed
  `_STRIKE_RE`-only leg-resolution copy — falls back to a random chain walk on numeric-key
  parse failure, which is worse than IC's blind-`None` since it silently computes signals
  against the wrong strike.

  **Fix:** identical pattern to the IC fix (BUG-012, 2026-07-06) and the shared-utility fix
  (2026-07-20) — route through `src/strategy/_price_utils.py::find_option_leg`'s existing
  `lookup: InstrumentLookup | None` BOD-fallback path instead of each file's own regex-only
  logic; remove the chain-walk fallback entirely.

  **Files:** `src/strategy/cc_overlay_v1.py`, `src/strategy/pp_overlay_v1.py`,
  `src/strategy/collar_overlay_v1.py`, their test files.

  **Before any code:**
  ```
  get_code_snippet("find_option_leg")     # the shared utility to delegate to
  search_code("_STRIKE_RE")               # confirm all three files' duplicate copies
  git log --oneline -10 src/strategy/_price_utils.py
  ```

  **Tests:** one per file — numeric key resolves via BOD fallback, chain-walk fallback is gone
  (asserted via a fixture where the chain-walk would have picked the wrong strike).

  **Commit:** `fix(strategy): route CC/PP/Collar leg finders through shared BOD-fallback utility`

---

- [x] **MC-6** — BUG-024: resolve `IronCondorV2.enter()`'s four entry legs' real `instrument_key`
  via BOD, instead of the fabricated symbol-style key. Same defect class as BUG-023/MC-3a, found
  during the MC-3a code-review pass (2026-08-06) and deliberately left out of that commit's scope
  — see `docs/bugs/bugs.md` BUG-024. Higher severity than BUG-023 was, since `enter()`'s legs
  persist to `paper_trades` immediately (not gated behind an unbuilt persistence step). Audited
  2026-08-06 via `scripts/dev/audit_bug024_fabricated_keys.py` against the live DB — **0 rows**
  found with a fabricated key under `paper_ic_nifty_v2*`, confirming the defect is dormant, not
  actively corrupting persisted data, before this fix lands.

  **Affects:** `src/strategy/ic_nifty_v2.py::IronCondorV2.enter`.

  **Fix:** reuse the `_resolve_roll_target_key(strike, option_type, expiry_str)` helper added in
  MC-3a (same signature already fits — `strike: Decimal`, `option_type: "CE"|"PE"`,
  `expiry_str: str`, `market.expiry.isoformat()` already computed in `enter()`) — renamed to
  `_resolve_instrument_key` since it's no longer roll-specific once `enter()` uses it too; all
  existing MC-3a call sites (`_roll_result_to_signal` Zone 2, `_execute_partial_roll`) updated to
  the new name, behavior unchanged. Any of the four legs failing to resolve aborts entry
  entirely (`return None`) — same skip-on-failure contract `_select_short_put`/`_select_short_call`/
  `_select_long_wing` already use earlier in `enter()`, not a partial 3-leg entry.

  **Tests:** all four legs resolve via BOD → `PositionUpdate` returned with real numeric keys;
  any single leg's strike absent from BOD for the resolved expiry → `enter()` returns `None`
  (treated as a failed entry, not a partial position or a crash); existing `enter()` tests
  updated to assert real key shape.

  **Commit:** `fix(strategy): resolve IC V2 entry leg instrument_key via BOD` | SHA: pending —
  same sandbox `.git/HEAD.lock` limitation as MC-3a; commit to be run on live host.

---

- [ ] **MC-5** — Docs close: `TODOS.md` session log entry per task landed (MC-1 through MC-4,
  whichever subset ships), `DECISIONS.md` entry only if MC-3/MC-4 change production behavior
  (MC-1/MC-2 are logging/audit-only, no DECISIONS.md entry needed for those unless MC-2's audit
  finds a real missed exit). No `CONTEXT.md` change expected unless MC-3 introduces a new
  strike-selection helper worth noting in the module tree. Run only after MC-1 through MC-4
  (or whichever subset the team lands) are complete.
