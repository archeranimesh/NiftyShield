# Yearly Overlays (CC / PP / Collar on December) — epic index

> Adds a December-only (`yearly`) variant of each overlay strategy — Covered Call, Protective Put, Collar — selected with `--expiry-type yearly`, running as an independent book beside the existing
> monthly overlays. One epic because the three variants share one foundation (tenor policy, ledger namespace, injectable clock, test fixtures) and must land in a fixed order.

## Why this epic exists

Monthly overlays need a roll or adjustment every cycle. Animesh wants a book that holds one December contract per year (Dec 2026 now, Dec 2027 after it expires) so there are far fewer adjustments. It
must be completely independent of the monthly overlay: separate ledger, separate positions, separate reporting, so the two books can be compared and neither can block the other.

## Scope decisions

Decided with Animesh on 2026-10-06:

- **Vocabulary is the resolver's, for IC and overlays alike:** `leaps` = quarterly (last Mar/Jun/Sep/Dec, 46-200 DTE), `yearly` = nearest live December. Overlays take `--expiry-type {monthly,yearly}`.
  `monthly` stays the default so every existing cron and invocation is unchanged.
- **IC needs no config change.** `CONFIGS` already holds weekly / monthly / leaps / yearly. The only IC work is the coexistence check in `yearly-validation/`.
- **Yearly overlays are a separate book.** Own `strategy_name` namespace, own positions; the monthly overlay's open legs must never make a yearly entry a no-op, or the reverse.
- **Dec 2026 now, Dec 2027 after it expires.** Dec 2026 runs on the current Upstox chain. Dec 2027 needs Dhan Greeks — see the sibling epic `dhan-far-expiry-chain/`.
- **Liquidity is a coded gate, not a judgement call** (Animesh: "we may have to adjust based on liquidity"). The gate itself is built in `dhan-far-expiry-chain/far-expiry-liquidity-gate/`.

## Verified facts that shape the design (2026-10-06 recon)

- CC, PP and Collar do **not** have separate `strategy_name`s. All three share `STRATEGY_OVERLAY = "paper_nifty_overlay"` and are told apart by `leg_role`. A yearly book therefore needs a second
  shared namespace, not three new names.
- The strategy classes (`CCOverlayV1`, `PPOverlayV1`, `CollarOverlayV1`) already carry `strategy_name: str = STRATEGY_OVERLAY` as a field, so a yearly instance can be the same class with a different
  name and tenor policy — no new strategy classes.
- `auto_cc_bootstrap` hardcodes `preference=["monthly"]` and `date.today()`; PP and Collar bootstraps do the same. Tenor and clock must become parameters.
- Hardcoded monthly-tenor gates: DTE >= 14 at entry and re-entry, `DTE_REVIEW` / EC-5 exit at DTE <= 5, PP routine roll at DTE <= 5 (`_PP_ROLL_DTE_THRESHOLD`). These are tenor policy, not constants.
- Namespace consumers known so far: `reentry_mixin`, `collateral_gate` (`_COLLATERAL_DRAWING_STRATEGIES`), `auto_close`, `overlay_coverage`, `eod_pt_summary`, `track_snapshot`,
  `_has_open_overlay_leg`. `yearly-foundation/` YF-1 turns this into an exhaustive audit.
- `paper_overlay_pnl_snapshots` is keyed `(strategy_name, overlay_type, snapshot_date)`, so a distinct yearly name should need no schema change (to be confirmed in YF-1).

## Architecture and design review

SOLID triggers run against the plan (`docs/refactor/design-principles.md`):

- **OCP:** no new `elif expiry_type == "yearly"` branch inside any bootstrap or strategy. Tenor differences live in one frozen `OverlayTenorPolicy` registry (a `dict`, not a Factory class) that is
  passed in. Adding a third tenor later is a new registry entry.
- **DIP:** the bootstraps take `today` and the tenor policy as parameters instead of calling `date.today()` and hardcoding `"monthly"`; this is also what makes the roll testable offline.
- **SRP:** expiry resolution is extracted once as a pure function; the three bootstraps currently each repeat it.
- **Prior-art audit:** `docs/refactor/code-deduplication-and-taxonomy.md` check is YF-1's first step — do not add a fourth copy of the resolution block.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `yearly-foundation/` | Audit, fixtures, `OverlayTenorPolicy`, resolver with injectable clock, namespace read-paths | ⬜ Not started | — | — |
| `yearly-cc/` | `--auto-cc --expiry-type yearly` + yearly CC behaviour | ⬜ Not started | `yearly-foundation` | — |
| `yearly-pp/` | `--auto-pp --expiry-type yearly` + yearly PP roll/re-entry | ⬜ Not started | `yearly-foundation` | — |
| `yearly-collar/` | `--auto-collar --expiry-type yearly` + same-expiry pair validation | ⬜ Not started | `yearly-cc`, `yearly-pp` | — |
| `yearly-ops-wiring/` | Daemon registration, labels, reports, crons for the yearly book | ⬜ Not started | `yearly-collar` | — |
| `yearly-validation/` | Independence tests, e2e dry-run, opt-in live smoke, IC coexistence check, paper-run runbook | ⬜ Not started | `yearly-ops-wiring` | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`.

## Open decisions for Animesh

1. **Yearly tenor policy values.** Entry min DTE, review DTE, roll DTE, profit target and delta stop for a ~12-month leg are not the monthly values. Default until decided: entry min DTE 14
   (unchanged), exit thresholds copied from monthly, `review_dte` / `roll_dte` set from the capture data in `far-expiry-liquidity-gate/` FG-3. Confirm or override before `yearly-cc/` starts.
2. **Collateral.** Default: the yearly namespace counts toward the same `collateral_gate` pool as the monthly overlay (conservative, avoids silently doubling exposure on the same NiftyBees holding).
   "Completely independent" could mean a separate budget instead — confirm before YF-5.

## Cross-cutting constraints

- `monthly` behaviour is frozen: a regression test pins every monthly policy value before any code changes, and the default `--expiry-type` stays `monthly`.
- No network, real token or real DB in the default `pytest` run. Live checks are opt-in behind a marker (`yearly-validation/`).
- The bootstraps keep their contract: structural failures abort, gate violations are log-only under `--log-only-gates`.
- Any change under `src/paper/` triggers `greeks-analyst`; any roll-logic change triggers `roll-validator` (`CLAUDE.md` AutoTrigger table).

## Supersession / coordination

- `dhan-far-expiry-chain/` supplies Greeks for Dec 2027 (Upstox returns zero past ~100 DTE). Nothing in this epic blocks on it until the Dec 2026 roll; `yearly-validation/` YV-5 gates the roll on it.
- `far-expiry-liquidity-gate/` FG-3 writes the yearly `roll_dte` into the policy registry created by YF-3 here.
- `data-source-routing/` (2026-10-07): the yearly book needs Dhan Greeks every day from the Dec 2026 roll until Upstox Greeks return (about Sep 2027), not only at the roll. `yearly-foundation` YF-6
  now depends on `data-source-routing/ds-chain-seam/` (contract resolver, `ChainSnapshot`). `yearly-validation` YV-5 additionally requires `ds-chain-monitoring/` (Dhan token freshness,
  chain-in-monitor path, stale-Greeks policy). `OverlayTenorPolicy` gains a monitor-cadence field (`ds-chain-monitoring` DSN-4).

## Epic done when

- **yearly-foundation** — monthly policy pinned by regression tests; yearly resolves Dec 2026 on 2026-10-06 and Dec 2027 on 2026-12-30 from fixtures; namespace consumers audited and updated.
- **yearly-cc / yearly-pp / yearly-collar** — each entrypoint accepts `--expiry-type yearly`, opens only the December contract under the yearly namespace, and leaves the monthly book untouched.
- **yearly-ops-wiring** — the daemon, reports and labels show the yearly book separately; off by default behind its own flag.
- **yearly-validation** — independence, dry-run and IC coexistence tests green offline; one opt-in live smoke recorded; paper-run runbook written.
