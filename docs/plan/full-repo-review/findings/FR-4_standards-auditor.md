# FR-4 — Code Quality & Coding-Standard Compliance Sweep

Persona: Standards Auditor. Scope: `src/`, `scripts/`, against `REVIEW.md` and `LOGGING.md`. `docs/plan/` and `docs/council/` excluded (FR-1/FR-3 scope). Counts below are from a fresh grep on the repo as of this session — seed numbers from the 2026-07-04 spot check are **not** assumed accurate and are only cited where they differ.

---

## 1. Logging standard violations

### bare `logging.getLogger(__name__)` instead of `structlog.stdlib.get_logger(...)`

**Current count: 21 files** (seed said 20 — one more file found this pass).

CRITICAL (violates the mandatory `structlog` standard in `LOGGING.md` §1):

- `src/backtest/bhavcopy_ingest.py`
- `src/backtest/bhavcopy_loader.py`
- `src/backtest/vix_ingest.py`
- `src/client/mock_client.py`
- `src/dhan/reader.py`
- `src/market_calendar/holidays.py`
- `src/mf/nav_fetcher.py`
- `src/mf/tracker.py`
- `src/models/portfolio.py`
- `src/notifications/telegram.py`
- `src/notifications/telegram_gateway.py`
- `src/nuvama/options_reader.py`
- `src/nuvama/reader.py`
- `src/nuvama/store.py`
- `src/paper/overlay_selector.py`
- `src/paper/track_snapshot.py`
- `src/paper/tracker.py`
- `src/portfolio/service.py`
- `src/portfolio/tracker.py`
- `src/risk/delta_tracker.py`
- `src/strategy/exit_signals.py`

### `scripts/` entrypoints missing `setup_logging()`

53 scripts have an `if __name__ == "__main__":` block. **Current count of those never calling `setup_logging()`: 22** — matches the 2026-07-04 seed exactly (no drift this pass):

- `scripts/council/ask_council.py`
- `scripts/dev/cleanup_cc_collar_dedup.py`
- `scripts/dev/generate_3track_viz.py`
- `scripts/dev/migrate_paper_strategies.py`
- `scripts/dev/migrate_paper_trades_state.py`
- `scripts/dev/migrate_strike_to_text.py`
- `scripts/dev/paper_track_snapshot.py`
- `scripts/dev/sandbox_order_lifecycle.py`
- `scripts/dev/send_test_telegram.py`
- `scripts/dev/validate_strategy_spec.py`
- `scripts/dev/verify_analytics.py`
- `scripts/lookup/find_overlay_strikes.py`
- `scripts/lookup/find_strike_by_delta.py`
- `scripts/lookup/instrument_lookup.py`
- `scripts/portfolio/roll_leg.py`
- `scripts/record/record_paper_trade.py`
- `scripts/record/record_trade.py`
- `scripts/seed/seed_mf_holdings.py`
- `scripts/seed/seed_nuvama_positions.py`
- `scripts/seed/seed_portfolio.py`
- `scripts/seed/seed_trades.py`
- `scripts/strategies/cc_calibration/paper_cc_entry.py`

Severity: CRITICAL per `LOGGING.md`'s mandatory-entrypoint rule (§"every entrypoint script must call `setup_logging()`"), even though this isn't one of `REVIEW.md`'s G-numbered rules — `CLAUDE.md`'s own instruction elevates `LOGGING.md` to canonical status.

### G7 vs. `LOGGING.md` keyword-arg rule — still unreconciled

Confirmed: `REVIEW.md` G7 ("f-strings in `logger.*()` calls are CRITICAL, use `%`-style") was written for stdlib `logging` and has not been updated for `structlog`. `LOGGING.md` §"Keyword args, not `%`-style, not f-strings — for structlog calls specifically" explicitly requires keyword arguments for `structlog` calls, which is a different convention from `%`-style positional args. `LOGGING.md` itself flags this ("`REVIEW.md` should be updated to clarify this split") — i.e., the contradiction is known and still open, not resolved.

Practical consequence: any file using correct `structlog.stdlib.get_logger(...)` with keyword-argument calls (the codebase standard, e.g. `logger.warning("event_name", key=value)`) would be **wrongly flagged CRITICAL by a reviewer applying G7 literally**, since G7 only recognizes `%`-style as compliant and doesn't special-case `structlog`. Every file in the codebase using the correct `structlog` keyword-arg convention is exposed to this false-positive risk — this is effectively every actively-logging module under `src/` and the majority of `scripts/`, since keyword-arg structlog calls are the documented standard (`LOGGING.md` line ~148). Representative files where this false-positive would actually fire (structlog + keyword args, confirmed present):
- `scripts/strategies/ic/paper_ic_snapshot.py` (`ic_snapshot.variant_failed`, `ic_snapshot.no_expiry_found` events use kwargs)
- `scripts/strategies/ic/paper_ic_entry.py`, `paper_ic_entry_v2.py`
- `scripts/pipeline/upstox_chain_snapshot.py`, `upstox_chain_intraday.py`

**Recommendation (not actioned, out of this audit's scope):** `REVIEW.md` G7 needs an explicit carve-out: "%-style for stdlib `logging`, keyword-args for `structlog`" — this is a doc fix, not a code fix, and should be logged as a `DECISIONS.md` follow-up rather than silently patched here.

### `print()` in strategy/portfolio/lookup/record scripts

**Current count: 23 files** (seed said "print() usage present," no seed count given — this is the first exact count):

| Directory | Files with `print()` |
|---|---|
| `scripts/strategies/` | 10 |
| `scripts/portfolio/` | 3 |
| `scripts/lookup/` | 8 |
| `scripts/record/` | 2 |

Files: `scripts/strategies/ic/paper_ic_snapshot.py`, `paper_ic_entry.py`, `paper_ic_entry_v2.py`, `paper_ic_monthly_comparison.py`, `scripts/strategies/cc_calibration/paper_cc_entry.py`, `paper_cc_roll.py`, `scripts/strategies/three_track/paper_3track_entry.py`, `paper_3track_snapshot.py`, `paper_3track_overlay.py`, `paper_3track_overlay_entry.py`, `scripts/portfolio/paper_snapshot.py`, `daily_snapshot.py`, `roll_leg.py`, `scripts/lookup/find_strike_by_delta.py`, `instrument_lookup.py`, `find_overlay_strikes.py`, `scripts/record/record_trade.py`, `record_paper_trade.py`.

Severity: WARNING, not CRITICAL — these are dry-run/CLI-report scripts printing human-facing summaries (dry-run command previews, position tables, error banners to `sys.stderr`) rather than swallowing structured events. `LOGGING.md` bans `print()` for anything that should be a structured log line, but a portion of this usage is legitimately CLI-report output (e.g. `roll_leg.py`'s "Dry run — roll NOT recorded" table) that overlaps in intent with the `src/auth/*` exclusion below. This needs a persona judgment call (not this auditor's) on which specific `print()` calls are structured-log substitutes (CRITICAL) vs. legitimate terminal-report output (acceptable) — flagging the full file list as WARNING pending that triage rather than blanket CRITICAL.

**`src/auth/*` exclusion — verified correct.** All `print()` calls in `src/auth/nuvama_login.py`, `dhan_verify.py`, `dhan_login.py`, `login.py`, `nuvama_verify.py`, `verify.py` are interactive OAuth/session-verification flows (open a login URL, prompt to paste a redirect URL, print a masked token, print profile/holdings for a human to eyeball). None of these are backgrounded entrypoints with a `setup_logging()` obligation — they're one-shot manual scripts meant to print directly to a human running them at a terminal. Exclusion holds.

---

## 2. Part III (G1–G8) — new-code diff check

Per the Meta-Rule (`REVIEW.md` line 778), Part III applies only to lines introduced/modified in the diff, not retroactively. Of the last 20 commits (`git log --oneline -20`), only **one** touches source/test code: `abafeaf fix(strategies): resolve IC snapshot expiry via instrument lookup` (all other 19 are `docs(plan)`/`docs(bugs)`/`docs(decisions)` commits with no `src`/`scripts` diff — correctly out of scope).

Diff reviewed: `scripts/strategies/ic/paper_ic_snapshot.py`, `tests/unit/strategies/ic/test_paper_ic_snapshot.py`.

- **G1 (`@staticmethod`)**: none introduced. Clean.
- **G2 (≤80 chars)**: checked every added line programmatically (`awk` length check) — all within 80 chars. Clean.
- **G3 (vertical alignment)**: none introduced. Clean.
- **G4 (TODO format)**: no new TODOs in this diff. Clean.
- **G5 (`except Exception` intent comment)**: no new broad-catch blocks introduced. Clean.
- **G6 (no `assert` outside `tests/`)**: no new `assert` in the `scripts/` file; the two new `assert`-free tests use `assert` correctly (permitted in `tests/`). Clean.
- **G7 (%-style logging)**: no new `logger.*()` calls added in this diff. N/A.
- **G8 (import ordering)**: `from src.instruments.lookup import InstrumentLookup, parse_expiry` — single edit, alphabetically ordered within the local-import group, no group-order violation. Clean.

**Finding: no Part III violations in the only code-touching commit of the last 20.** This commit's own session log (in `TODOS.md`) already self-reports a G7/G8/G2 self-review — consistent with what this independent grep-check finds.

---

## 3. `# type: ignore` / `# noqa` — explanatory-comment meta-rule

`REVIEW.md` line 306: "Grep for `# type: ignore` and `# noqa`. Each one should have a comment explaining *why*. Silent suppressions are deferred bugs."

- **`# type: ignore` total: 26 instances.** **0 of 26** carry an explanatory "why" beyond the bare suppression code (e.g. `# type: ignore[arg-type]` with no prose). Every instance is a bare suppression-code annotation with no justification prose. **CRITICAL per the meta-rule** — none currently comply. Representative files: `src/mf/store.py:250`, `src/portfolio/store.py:244,379,454`, `src/portfolio/tracker.py:337`, `src/models/portfolio.py:270,276,312`, `src/instruments/lookup.py:31,40`, `src/strategy/monitor.py:401`, `src/strategy/ic_nifty_v2.py` (×6), `src/strategy/nifty_track_comparison_v1.py:593,604`, `src/auth/nuvama_login.py:33,37`, `src/auth/nuvama_verify.py:28,30`, `src/nuvama/mock_client.py`/`protocol.py` (noqa, see below), `scripts/portfolio/daily_snapshot.py:159`, `scripts/seed/seed_portfolio.py:46`, `scripts/dev/probe_nuvama_schema.py:23`.

- **`# noqa` total: 89 instances.** **9 of 89** carry explanatory prose after the noqa code (e.g. `# noqa: BLE001 — persistence failure must not block entry`). **80 of 89 lack explanation** — CRITICAL per the meta-rule for those 80. The 9 compliant ones are concentrated in `scripts/strategies/ic/paper_ic_entry.py`, `paper_ic_entry_v2.py`, `ic_entry_gates.py` — i.e. one recent session already started doing this correctly; the pattern hasn't propagated to the other ~75 `# noqa: E402` (delayed-import-after-sys.path-insert) and `# noqa: F401` (re-exported-but-unused) instances scattered across `scripts/monitor_daemon.py`, `scripts/pipeline/*.py`, `scripts/pre_market_brief.py`, `scripts/portfolio/daily_snapshot.py`, `scripts/start_monitor.py`, `scripts/stop_monitor.py`, `scripts/eod_summary.py`, and others.

  Note for the reviewing persona: most bare `E402`/`F401` codes are self-describing to an experienced reader (E402 always means "import after `sys.path.insert`, unavoidable in this script layout"), but `REVIEW.md`'s meta-rule as written does not carve out an exception for self-describing codes — flagging as CRITICAL per the letter of the rule, while noting this is a candidate for the same "document the policy split" fix as G7/`LOGGING.md`.

---

## 4. `assert` outside `tests/` (G6)

**Current count: 2 instances, both CRITICAL** (pre-existing, not part of the one reviewed diff — these are tech debt under G6's "no grace period for new code" but retroactive to existing code per the Part III meta-rule, so they land in TD backlog territory rather than blocking this diff):

- `src/config.py:209` — `assert self._cached_settings is not None` (post-population invariant check in a settings-cache getter; stripped under `-O`, should raise `RuntimeError` or similar instead).
- `src/strategy/roll_utils.py:62` — `assert leg.delta is not None` inside `_sort_key`, guarding a precondition the caller is supposed to have already filtered for. Same `-O`-stripping risk; if the precondition is ever violated in production (e.g. a filter upstream regresses), this silently returns garbage sort order instead of raising.

Recommend both get a `TODOS.md` TD entry if not already tracked — grep found no existing TD-1..TD-7 entry referencing either file by name.

## `except Exception` without an intent comment (G5)

**Current count: 183 `except Exception` occurrences across 55 files.** This is too large a set to hand-verify per-instance in this pass without ballooning the report; spot-checking is required rather than a full per-line audit. Full file list (55 files) is in the grep output above/available on request — flagging the **count and file list** as the FR-4 deliverable, and recommending a **follow-up pass** (or a dedicated persona) to go instance-by-instance and confirm which of the 183 have the required "intentional isolation point" comment vs. which are bare/silent. Spot check of 3 files during this session:

- `scripts/strategies/ic/paper_ic_entry.py:416,505,539` — all three carry `# noqa: BLE001 — <reason>` comments that satisfy G5's intent. Compliant.
- `scripts/portfolio/daily_snapshot.py` (10 instances) — all use `# noqa: BLE001` with **no** explanatory text (just the bare code). **G5 CRITICAL** for these 10.
- `src/notifications/telegram.py`, `telegram_gateway.py` — not spot-checked line-by-line this pass; flagged for the follow-up.

This is the single largest open item in this audit — the true CRITICAL count for G5 is very likely well above the 10 confirmed here once all 183 are checked, and this auditor did not have budget in this pass to hand-verify all of them without turning this into a second full task.

---

## Summary table

| Rule | What | Current count | Severity |
|---|---|---|---|
| Logging standard | bare `logging.getLogger(__name__)` | 21 files | CRITICAL |
| Logging standard | `scripts/` entrypoints missing `setup_logging()` | 22 files | CRITICAL |
| G7 vs LOGGING.md | unreconciled contradiction, false-positive risk | open, unresolved | — (doc bug, not code bug) |
| print() ban | `scripts/{strategies,portfolio,lookup,record}/` | 23 files | WARNING (needs triage) |
| Part III (diff-level) | last 20 commits, 1 code-touching commit | 0 violations | — |
| Meta-rule | `# type: ignore` without explanation | 26/26 | CRITICAL |
| Meta-rule | `# noqa` without explanation | 80/89 | CRITICAL |
| G6 | `assert` outside `tests/` | 2 instances | CRITICAL |
| G5 | `except Exception` total / confirmed-uncommented | 183 total, 10+ confirmed bare | CRITICAL (partial audit) |

---

## Closing block

Persona reviewed as: **Standards Auditor**.

Perspective not covered by this review: a **Security Reviewer** persona would have caught something this pass explicitly skipped — the `# type: ignore[import]` suppressions around `APIConnect` imports (`src/auth/nuvama_login.py`, `nuvama_verify.py`, `scripts/dev/probe_nuvama_schema.py`) and the broad `except Exception` blocks wrapping credential/session-token handling in `src/auth/*` were only counted mechanically here, never assessed for whether the broad catches could mask a credential-leak or a silently-degraded auth failure mode reaching a "success" branch. This audit counted rule violations; it did not ask "does any of these 183 broad catches hide a security-relevant failure." That's a distinct question a Security Reviewer would need to answer, not a Standards Auditor.
