# src/nifty_calendar — Module Context

> Auto-loaded when working inside `src/nifty_calendar/`. Pure core of the Nifty positional calendar (`docs/plan/nifty-calendar/`, story `calendar-monthly/` CM-1..4, expiries added in CM-7).

---

## Purpose

Near-expiry ATM short straddle plus far-expiry OTM long wings (net long vega, near delta-neutral), paper only. This package holds the maths and the rules; it does not trade. The strategy shell is
`src/strategy/nifty_calendar_v1.py` (+ `nifty_calendar_state/_factory/_notify/_report/_payoff`); entry and EOD scripts are `scripts/strategies/nifty_calendar/`.

## Invariants

- **Leaf package, one-way dependencies.** Imports only `src.models` and `src.market_calendar` (plus stdlib/Decimal). Never import `src.strategy`, `src.paper`, `src.client`, `src.notifications` or any
  IC module. That is why `selector.py` carries its own `mid` / `spread_points` instead of `src.strategy._price_utils.resolve_price`.
- **No I/O, no clock, no network.** Every function takes its inputs (chains, dates, config) as arguments and returns frozen values. Time is passed in; holidays come through `src.market_calendar`.
- **`Decimal` for all money and Greeks.** Never `float`.
- **Executable-price valuation.** Entry, exit and P&L use the bid/ask-derived mid or the side that would actually fill, never a stale LTP (far-leg LTP lags the quote; see CM-0 finding 4).
- **No `if variant`.** Variants are frozen `CalendarVariantConfig` values (`MONTHLY`) plus implementers of three `Protocol` collaborators (`StructureSelector`, `ExitRule`, `CyclePolicy`) in a `dict`
  registry. Adding bi-weekly means a new config, policy and rule, not a branch.
- **Interim pricer.** `pricing.py` is a local Black-76 (price and IV solve, forward passed as an argument). It is temporary: CM-9 replaces it with `src/pricing` and deletes the file once
  `greeks-bs-fallback` GF-2/GF-3 ship. Do not add new importers.

## Files

`models.py` frozen `CalendarLeg` / `CalendarStructure` / `StructureMetrics` · `payoff.py` `payoff_at`, `compute_metrics` (breakevens, risk-reward, net Greeks; far legs repriced at each leg's own IV) ·
`config.py` `CalendarVariantConfig`, `MONTHLY` · `selector.py` `WingStructureSelector` (six entry filters plus absolute spread gate, inward search to `min_wing_points`, explicit `NoEntry`) ·
`cycle.py` `MonthlyCyclePolicy`, `active_variant`, `EntryPlan` · `expiries.py` `monthly_expiries` (settled months from the expiry rule, unsettled months from the instrument list) · `exit_rules.py`
`MonthlyExitRule` (priority: target, breach with time gate, hard day-10 close, DTE guard) · `errors.py` `CalendarError` hierarchy · `pricing.py` interim Black-76.

## Tunables worth knowing

`vega_cap` is an upper bound on signed net vega per unit (net long positive), monthly default 20, **uncalibrated** (see `DECISIONS.md` §"Nifty calendar monthly: close-out"). `spread_tolerance` is 3.0
points per leg. The monthly expiry is not "last Tuesday" in a holiday month (November 2026 is Monday 23rd), so expiries always come from `expiries.py`.
