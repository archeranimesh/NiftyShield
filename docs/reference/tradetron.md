# Tradetron MCP — Reference

> Status: backtest section filled from tool schemas on 2026-10-04; other sections still skeleton. Only two read-only calls have hit the live account (see Verified findings); no backtest has been
> submitted. Mark entries **verified** as they are tested. Not yet wired into `CLAUDE.md` / `AGENTS.md` / `REFERENCES.md`.

## Server

Tradetron MCP (`mcp__tradetron__tt_*`), authenticated via `/mcp`. About 70 tools. If a call returns unknown-tool / not-found, the connector's cached tool list may be stale — reconnect.

## Tool catalogue

**Authoring.** `tt_create_strategy`, `tt_create_strategy_chunked`, `tt_update_strategy`, `tt_apply_strategy_patch`, `tt_apply_strategy_patch_chunked`, `tt_preview_change`, `tt_list_editable_fields`,
`tt_normalize_strategy`, `tt_get_strategy`, `tt_export_strategy`, `tt_get_sample_strategy`, `tt_list_my_strategies`. Reference: `tt_get_tradetron_quickstart` (~13k tokens, load once, only for
create/edit), `tt_get_authoring_reference`, `tt_find_keyword`, `tt_lookup_keyword`, `tt_list_keywords_by_category`, `tt_report_template`. Validation: `tt_validate_markdown`, `tt_validate_python` —
always validate before create.

**Backtesting.** `tt_backtest_strategy`, `tt_backtest_idea`, `tt_backtest_sweep`, `tt_backtest_compare`, `tt_backtest_workbench`, `tt_backtest_status`, `tt_backtest_result`, `tt_backtest_trades`,
`tt_list_backtests`. Pre-checks and analysis: `tt_check_backtestability`, `tt_check_edge`, `tt_check_underlying_support`, `tt_pnl_drivers`, `tt_indicator_snapshot`.

**Deployment and monitoring.** `tt_deploy_strategy_paper`, `tt_promote_to_strategy`, `tt_get_my_deployed_strategies`, `tt_get_my_deployed_strategy_detail`, `tt_get_strategy_broker_log`,
`tt_get_strategy_notifications`, `tt_get_strategy_counters`, `tt_diagnose_strategy`, `tt_strategy_performance`, `tt_portfolio_report`, `tt_export_reports`.

**Market data / options analytics.** `tt_straddle_live`, `tt_straddle_chart`, `tt_straddle_decay`, `tt_scan_instruments`, `tt_list_underlyings`, `tt_market_calendar`.

**Integration.** `tt_create_signal_bridge`, `tt_update_signal_bridge`, `tt_link_strategy_api` (candidate path for NiftyShield signals into Tradetron). Brokers: `tt_list_brokers`, `tt_get_my_brokers`,
`tt_check_broker_support`, `tt_broker_integration_guide`.

**Account.** `tt_get_my_profile`, `tt_wallet_balance`, `tt_list_plans`, `tt_get_my_subscription`, `tt_get_my_strategy_subscriptions`.

**Lists.** `tt_get_list`, `tt_modify_list`, `tt_search_lists`.

**Support.** `tt_ask_tt`, `tt_open_crisp_conversation`, `tt_check_crisp_response`, `tt_reply_to_agent`, `tt_get_webinars`.

## Authoring rules (from server instructions)

Workflow: quickstart once → restate logic in plain English and flag ambiguities → author markdown → `tt_validate_markdown` → fix every error → `tt_create_strategy`. Never skip validation.

- Leg Qty is in **lots**. Confirm resolved lot count per leg; a share/contract count mis-sizes by orders of magnitude.
- A per-leg trailing/repair stop (Leg SL trail / Leg Exit / Traded Instrument) must anchor `cond_type='Entry'` — the condition that opened the leg, never the Repair Once it sits in. A self-reference
  silently never arms and the leg runs unprotected.
- Index strikes (NIFTY/BANKNIFTY) use ATM SPOT; MCX uses ATM (no spot).
- Prefer a keyword lookup over a guessed keyword name or Python API.

The server's instruction text was truncated in the session; re-read it for the remaining rules before authoring.

## What can be authored

Source: `tt_get_sample_strategy()`, `tt_get_authoring_reference()`, `tt_list_keywords_by_category()` on 2026-10-04. Fetch a template with `tt_get_sample_strategy('<pattern>')`; never author for a
pattern the catalogue does not list.

**Top-level patterns (create-verified templates).** NIFTY: `short_straddle`, `short_strangle`, `iron_condor` (ATM±1 body, ±4 wings), `butterfly` (iron fly), `rolling_straddle` (Repair Continuous roll
at 150 pts drift), `calendar`, `pilot_calm` (flagship margin-safe IC create payload: wings at Entry, body via Repair Once), `canonical` (NIFTY+SENSEX all-features master). Mechanics:
`repair_once_best_practice` (per-leg premium stop via Repair → runtime var → Set Exit, no leg SL columns), `staged_reentry` (one Set per fill, structural cap), `wait_and_trade` (capture 9:20 ATM
premium, trade on ±X move). Exchanges: `nfo_samples` (index spot/future/options, stock straddle; candle source is `NFO,NIFTY 50`, not NSE_IDX), `sensex_orb` (BFO), `nse_sample` (cash equity MIS),
`mcx_sample_template` (crudeoil), `us_spx_condor` (XCBO, USD), and Delta India crypto: `delta_crypto`, `delta_btc_ema_cross_15m`, `delta_eth_mean_reversion_1h`, `delta_btc_breakout_15m`,
`delta_eth_trend_trailing`, `delta_btc_range_intraday` (daily-option condor). `rank_top_gainers_losers` is **not MCP-authorable** (manual template only).

**Library (140+ validated entries).** `option_patterns` (101 leg structures: spreads, butterflies, condors, ladders, ratios, box, jelly roll, PMCC, calendars/diagonals, covered/collar, synthetics),
`team_idioms` (13, incl. `delta_neutral_gamma_scalping`, `short_straddle_with_hedge`, `straddle_per_leg_sl_ratchet`, `strangle_dte_strike_weekday_branch`, `covered_call_ema_adx`,
`donchian_pyramid_cap`), `primitives` (single/multi set, repair once/continuous, runtime var, python block), `mechanics` (rollover, pyramiding, overnight protection), `gap_structures`, `gap_entries`
(12 adjustment recipes, validated but not built, e.g. `04_defend_tested_side`, `31_trailing_recenter`, `cp08_vix_tail_hedge`), `chart_types`, `delta_crypto`, `python_recipes`.

**Keyword categories (counts).** Technical 103, RuntimeVariables 33, StrategyInfo 23, DateTime 17, PriceData 17, OptionGreeks 16, Statistics 14, Candle Patterns 13, PythonRuntime 12, ExpiryFormula 10,
Math 8, Series_Ops 6, Options 5, StrikeFormula 5, Fx 4, InstrumentFormula 3, LegQtyForms 2, Rank 2, Sentiment 2. Browse one with `tt_list_keywords_by_category('<name>')`.

**Authoring reference topics** (`tt_get_authoring_reference('<topic>')`, pull one at a time): `common_patterns`, `wire_vs_display_forms` (read before any python block or %-of-credit exit),
`equity_vs_derivatives_legs`, `option_chain_recipes`, `repair_once_pattern`, `capability_map`, `exit_sl_target`, `markdown_grammar_extended`, `candle_timeframes` (candles anchor to midnight, not
09:15), `frozen_instrument`, `python_block`, `list_based`, `strategy_brief_template` (the user-facing brief format), `positional_mechanics`, `adjustments_taxonomy`, `adjustments_crosswalk`,
`webhook_linking`, `editing_existing_strategies`.

Fit with NiftyShield: the IC, straddle/strangle, calendar and delta-neutral gamma-scalping shapes all have templates. Per-leg SL is built through Repair Once, which also avoids the
unsupported-in-backtest `Leg SL trail`.

## Greeks and option chain

Source: `tt_list_keywords_by_category` (OptionGreeks, Options, StrikeFormula) and `tt_get_authoring_reference('option_chain_recipes')`, 2026-10-04. Keyword listings only; first exercised on a Live
Offline strategy 2026-10-05 (see "Greeks probe results" below).

**There is no chain-dump tool.** The chain is reached one instrument at a time through an instrument CSV string, `'EXCHANGE,SYMBOL,EXPIRY,OPT_TYPE,STRIKE_SPEC,,OFFSET'` (7 fields). Examples:
`'NFO,NIFTY 50,Current Week,CE,ATM,,'`; OTM by strike count `'NFO,NIFTY 50,Current Week,CE,ATM-SPOT,,2'`; index spot `'NFO,NIFTY 50,,,,,'`. Options live on NFO and the symbol is `NIFTY 50` (with the
space). Numeric strikes go in the OFFSET field, not STRIKE_SPEC. Expiry tokens are `Current Week` / `Current Month`; "next" is the same token with nth offset 1 (no `Next Week` token). The wire forms
are for raw JSON only; markdown uses display form.

**Per-instrument Greeks (Float).** `Delta(instrument)`, `Gamma`, `Theta`, `Vega`, `Rho`, `Iv(instrument)`, plus `Atmiv(Underlying)` (ATM chosen off the futures chart, not spot). Rho and IV are
present, so the chain carries the full set.

**Position-level Greeks (Float).** `Net Delta(Underlying)`, `Net Gamma`, `Net Theta`, `Net Vega` over the strategy's open positions. `Delta Neutral` / `Gamma Neutral` / `Theta Neutral` / `Vega
Neutral(Underlying, instrument)` return the lots of an instrument that zero the net Greek, as a float multiple of lot size; they are meant for Qty Fx in the position builder (delta hedging).

**`Get Greeks(identifier)` is hard-blocked** (returns a dict of all six; on the KEYWORD_NOT_OPERATIONAL gate list, refused by the validator). Use the individual keywords above.

**OI keywords (Options category).** `Max OI Strike` / `Max OI Instrument` / `Max OI Value(Underlying, Expiry, option_type)`, `PCR(Underlying, Expiry)`, `Total OI(Underlying, Expiry, option_type)`. Not
backtestable (`PCR`, `Total OI` are absent from the BT engine); the Max OI trio's BT status is unchecked.

**Strike selection (StrikeFormula).** `ATM(Underlying, Offset)` anchors on the futures chart (use for monthlies); `ATM SPOT(Underlying, Offset)` on spot (weeklies/dailies); `Get Strike`; and `Find
Strike(Underlying, Expiry, Field, Value, option_type, results)`, which returns the strike whose chosen field is **closest to a target value, e.g. a target delta or premium**. `Find Strike Crypto` is
the Delta-India mirror. So delta-targeted strikes are native for NSE.

**Find Strike hazard (live incident 2026-09-15, 100-lot deployment).** If it returns None (empty chain at the call, or `lesser`/`greater` mode with no qualifying strike), the engine skips only that
leg and fills its siblings, so the deployment went live with 2 of 3 legs. The set's Entry latch is already set, so the leg is never retried, and any Exit reading that leg through Traded Instrument
errors every cycle and never fires. Chronic at the NSE open (~15k "Invalid Strike" lines per 10 minutes fleet-wide). Rules: never put a Find Strike leg in the same set as ATM legs in the window's
first minute; put a Find Strike hedge in its own set entered first and gate the short legs on its fill; never write an Exit that indexes a Find Strike leg through Traded Instrument without a fill
check; mode `any` is unbounded (no distance cap; validator `FIND_STRIKE_ANY_UNBOUNDED`), so a Rs 10 target can return a Rs 100 contract in high VIX.

**Per-leg stops on options.** Compare the premium of the traded option, never index spot: live premium is `LTP(Traded Instrument Name('Entry','instrument',<underlying>,set,cond,leg),'LTP')`, entry
fill is `Traded Instrument('Entry','price',...)`. Cond type must be `Entry`/`Repair Once`/`Repair Continuous`, never `Exit`. Put these in an Exit condition or a Repair Once, never in the leg
SL/target/Limit columns.

**ATM probe (2026-10-04, a Sunday, market closed).** What the MCP returns for the ATM option, versus what it does not.
- `tt_straddle_live('NIFTY 50')` failed with `COMMON_NOT_FOUND: missing_leg: no ticks yet` — no live ticks outside market hours. The error did leak the defaults: nearest expiry **2026-10-06
  (Tuesday)**, ATM strike 22450, instrument ids of the form `OPTIDX_NIFTY_06OCT2026_CE_22450`.
- `tt_straddle_chart('NIFTY 50', date='2026-10-01', band=false)` works for a completed session. Header: expiry 2026-10-06, DTE 5, strike 22600, spot 22551.95, synthetic future 22464.25 (= strike +
  CE - PE), CE 66.7, PE 202.45, straddle 269.15 at 15:30; open 258.4, high 429.95 (14:02), low 248.2. Series is `{t, ce, pe, straddle}` per minute (09:15–15:30, 376 points).
- **It carries premiums only: no delta, gamma, theta, vega, IV or OI.** So the MCP's market-data tools do not expose Greeks; the Greek keywords only evaluate inside a strategy (condition or Python
  block). Seeing real values needs a paper / Live Offline deployment that writes `Delta(...)` into a runtime var, or `tt_ask_tt`.
- **`bucket_minutes` is ignored by `tt_straddle_chart`** (asked for 60, got 376 one-minute rows, ~15k tokens). Rule 1: avoid this call, or pass the narrowest question possible; `tt_straddle_decay`
  returns aggregated percentiles instead.
- ATM here is forward-anchored and fixed at the session open. At the 15:30 close the synthetic future sat about 88 pts **below** spot, which is unexpected for a 5-day forward; unexplained (stale
  strike vs. data quirk vs. convention). Do not rely on `synthetic_future` until checked.
- Date arithmetic check: 2026-10-01 is Thursday and 2026-10-06 is Tuesday, consistent with the Tuesday weekly expiry noted in `REFERENCES.md`.

**Greeks probe results (2026-10-05, Live Offline, template 999078810).** The probe's Entry condition writes LTP, delta, gamma, theta, vega, rho and IV of the weekly CE and PE into runtime vars once at
09:30 (guard `snap` 1 → 2); read them with `tt_get_strategy_counters(<SID>, changed_only=true)`. The Greek keywords work inside a strategy and every variable populated.
- **`ATM` and `ATM-SPOT` in the instrument CSV are different selectors.** Run 1 (SID 999158894, 04:00 UTC, spot 22566.95) used `...,CE/PE,ATM,,`: CE 50 / PE 152, delta 0.334 / -0.666, IV 17.37 /
  17.40. That is not an ATM pair (deltas should be near ±0.5). Put-call parity (CE minus PE = -102) implies a strike roughly 100 pts above spot, while the leg, using `ATM SPOT`, traded 22550. The
  resolved strike of plain `ATM` was never recorded, so "about 22650-22700, futures-anchored" is an inference, not a reading.
- Run 2 (SID 999167718, 04:38 UTC, spot 22550.3) used `...,ATM-SPOT,,`: `strike_spot` 22550, CE 106.7 / PE 88.0, delta 0.535 / -0.468, IV 18.56 / 18.62, theta -39.3 / -39.4, gamma 0.00163, vega 5.21.
  A proper ATM pair on the same strike as the traded leg. The runs are 38 minutes apart, so spot differs slightly.
- **Rule:** for weekly NIFTY options use `ATM-SPOT` in instrument strings, matching the `ATM SPOT` leg strike. Never mix plain `ATM` with `ATM SPOT` legs in one strategy. Record the strike with `ATM
  SPOT('NIFTY 50','0')` in a runtime var (`strike_spot`) so any later reading can be tied to a strike.
- **`Atmiv('NIFTY 50')` is a separate measure.** It read 13.30 (run 1) and 13.62 (run 2) against leg IVs of 17.4 and 18.6, so it did not match the spot-ATM leg IV even after the strike was fixed. Its
  docs say the ATM comes from the futures chart; the expiry or strike it reads was not verified. Do not compare it with per-leg `Iv()`.
- Unexplained: run 2 parity (CE minus PE = 18.7 vs spot minus strike = 0.3) implies a forward about 18 pts above spot, wider than one day of carry. Possibly leg quotes from different ticks.
- Orders on a Live Offline deploy stay `Initiated`, quantity 65, `broker_order_id` null: normal, nothing reaches the broker.
- Editing a template that has a running deployment warns `EDIT_RESETS_RUNTIME_COUNTERS`, but `snap` and `spot` on the running SID were unchanged on a re-read after the edit. `tt_apply_strategy_patch`
  edits runtime vars at `/sets/N/conditions/M/extra/variables` (value, display and json together); `condition_action` is not a patchable key.

**Not yet established.** Greek units and conventions (per-share vs per-lot, vega per 1% IV, theta per day), source of IV/Greeks (exchange vs Tradetron-computed), refresh latency, and whether Greeks
are available in the backtest engine. `tt_check_backtestability` on a template using `Delta()` answers the last; the first three need a live read or support (`tt_ask_tt`).

## IC v1 vs Tradetron templates

Full saved markdown for `iron_condor` and `pilot_calm`: `docs/reference/tradetron_ic_templates.md`. Compared against `docs/strategies/ic_nifty_v1.md` on 2026-10-04. "Check" means the answer is not in
what was pulled; the named authoring topic should settle it, so pull that one topic and record the result here.

| IC v1 spec | Template | Gap |
|---|---|---|
| Lot size 65 | NIFTY 50 lot size 65 (`tt_check_underlying_support`) | Match |
| Strike by target delta (short put ~15Δ, call ~10Δ; 8–15Δ with CSP) | `ATM SPOT("NIFTY 50", ±1)` body, fixed offsets | **Resolved in principle** via `Find Strike(..., 'Delta', ...)`; see note 1 |
| Wings 500 pts (equal) | Wings ±4 steps, body ±1: width 3 steps = 150 pts at 50-pt steps | **Gap.** Offset ±10 from the body gives 500; confirm the step size and that offsets that large resolve |
| Monthly expiry, 30–45 DTE, last-Tuesday expiry | `Current Week` | **Gap.** Calendar template uses `Current Month`; check `ExpiryFormula` keywords for DTE and the Tuesday expiry; see note 2 |
| Enter Wednesday after monthly expiry, 10:00–10:30 | `Week Day(NSE) == 3` + time window (pilot_calm) | Close. Needs a DTE 30–45 gate on top |
| One open IC; no re-entry in the same cycle | `entered` one-shot var + `Open Positions == 0` flat guard | Covered. Re-entry block across the cycle needs the var reset only on a new expiry |
| Exit: cost-to-close ≤ 50% of credit | PNL target is absolute ₹ × Multiplier | **Gap.** Check `wire_vs_display_forms` (%-of-credit exit, entry-credit capture) |
| Exit: cost-to-close ≥ 2× credit | PNL stop is absolute ₹ × Multiplier | **Gap.** Same topic; also `exit_sl_target` |
| Exit: short-leg absolute delta ≥ 0.35 | none | **Buildable in principle:** `Delta()` of the traded instrument in an Exit condition; see note 3 |
| Exit: close at 14 DTE; never hold within 2 days of expiry | `Time >= 1515` only | **Gap.** Needs a DTE keyword (ExpiryFormula / StrategyInfo) |
| Limit order at combined mid, improve ₹0.25 after 5 min | `Price execution = Market Price` | **Gap.** Check METADATA price-execution options in `markdown_grammar_extended` |
| IVR ≥ 25, 200-DMA, event, liquidity, min-credit gates | none | Likely not buildable except 200-DMA (Technical SMA); IVR needs India VIX history, events need the calendar. Keep those in NiftyShield |
| Margin-safe leg order | Wings first, body in Repair Once | Adopt as is; this is a platform rule for mixed BUY+SELL |
| Exit shorts first | `Exit shorts first = Yes` | Match |
| 5 independent exit triggers, first wins | Universal Exit is OR-joined | Structure fits; conditions differ |

Table notes.

1. `Find Strike(..., 'Delta', target, ...)` picks the strike nearest a target delta. Mind the Find Strike leg-drop hazard (see Greeks section); check field/mode argument values.
2. The weekly expiry moved from Thursday to Tuesday in April 2026.
3. Use `Delta(Traded Instrument Name('Entry','instrument',...))` in an Exit condition; the short-leg handle must exist (fill check). Confirm the delta sign/units for puts.

Net: the template is the right skeleton (margin-safe legs, one-shot guard, OR-joined Universal Exit). Entry sizing by delta, the %-of-credit and delta stops, DTE gates and limit-mid execution are the
unresolved items, and each maps to a specific authoring topic above. Do not port IC v1 until those are settled, since a fixed-offset condor would be a different strategy from the one in the spec.

## Backtesting

Source: tool schemas and descriptions read 2026-10-04. Since 2026-08-25 every backtest, web or chat, runs on Tradetron's own backtest fleet (FastBT, job ids `ttbt-<bt_id>`). Sweeps and
non-default-knob runs may still return 16-hex `btengine` job ids, whose status payload carries a results block; fleet runs return only completion + `report_url`.

**Workflow.** `tt_backtest_workbench(template_id)` first: free, shows existing runs and the price of a new one. Then `tt_check_backtestability(template, start, end)` to pre-flight. Then
`tt_backtest_strategy`, poll `tt_backtest_status` (10–75s), read numbers with `tt_backtest_result` (free, re-sliceable). Compare finished runs with `tt_backtest_compare` (free).

| Tool | Cost | Purpose |
|---|---|---|
| `tt_backtest_workbench` | free | Open a template: existing runs, what is free to re-read, `next_run.quote` and `changes_that_need_one` |
| `tt_check_backtestability` | free | Pre-flight; branch on `verdict` (blocked / backtestable / unknown), not the `backtestable` boolean |
| `tt_check_edge` | free | Spot-only rule screen (no charges, slippage, sizing). Not a backtest; never annualise or call it profit |
| `tt_backtest_idea` | free preview, paid run | NSE stock/ETF, daily candles, long-only; exit mandatory; run needs `confirm_charge` + token |
| `tt_backtest_strategy` | wallet debit past daily free allowance | One run by `strategy_id` or inline `template`; auto-refund on failure |
| `tt_backtest_sweep` | N × per-run fee | Single-axis only (`search` + `values`); needs a saved template (`tt_get_strategy` first) |
| `tt_backtest_status` | free | Completion + `report_url` |
| `tt_backtest_result` | free | Analysis sections over a finished run |
| `tt_backtest_trades` | free | Fills, paged (default 25, max 200); summary computed over all fills |
| `tt_backtest_compare` | free | 2–3 runs, first is baseline; deltas + paired daily test, no winner field |
| `tt_list_backtests` | free | Account's runs; id resolver (`job_id`, `bt_id`, `readable`) |

**`tt_backtest_strategy` arguments that matter.** `start`/`end` (YYYY-MM-DD), `candle_freq` (minutes, default 1), `trade_price` (`Open` default | `Close` | `Avg of Open and Close`; `Close` gives every
price-triggered condition a minute of look-ahead), `type` (`auto` | `intraday` force-closes at 15:30 | `positional`; wrong type means wrong numbers). `capital`, `oos_pct`, `slippage_bps`, `tt_match`
are **ignored** since 2026-08-28 — brokerage and slippage are set in the cost lab on the report page and apply without a re-run. Walk-forward is available only on a sweep (`oos_pct`, default 30).

**What forces a new paid run** (everything else is a free re-read): strategy body, dates, type, expiry, fill price, candle frequency.

**`tt_backtest_result` sections.** Default (~2.4k tokens): `headline meta costs weekday drawdowns monthly exit_attribution concentration trade_stats setwise stats_table`. On request: `series
sub_windows grade timing distribution underwater regime rom benchmark walk_forward montecarlo quality trades positions sets underlyingwise`. `trades` is ~56k tokens in full — cap it. `sub_windows` is
summarised unless `caps={"sub_windows_full": true}`. Read `caveats[]` before quoting any figure; a metric the book cannot support is absent, not zero (`section_notes.headline_withheld`). Check
`section_notes.<name>.basis` for gross vs net. Per Rule 1, request named sections and small caps; never pull full trades into context.

**Coverage (from `tt_check_backtestability`).** NSE/NFO/BFO (SENSEX/BANKEX options from 2023-07), MCX futures and options, Delta-India BTC/ETH daily options, US index options (SPX/XSP/NDX/VIX) plus an
18-symbol stock/ETF option list. Non-Delta crypto exchanges are blocked. The BT engine implements a subset of live keywords: `Leg SL trail`, `PCR` and `Total OI` are not in it, and custom Python and
runtime-variable underlyings are flagged as error-prone. A blocker means the run will fail; a warning means it may error or silently skip data.

**Other.** The sweep's baseline is comparable with a single run only because both default `trade_price` to `Open`. `tt_backtest_compare` withholds metrics in `not_compared`; do not subtract them.
`tt_indicator_snapshot` (1m–1h, no daily) returns summary / moving-average / oscillator verdicts plus forward-move history from the same bar store the engine uses; quote sample size.

## Account state

Captured 2026-10-04 (read-only calls). Never record credentials or tokens here.

- **Plan: Free** (India NSE, **1-minute delayed data**). One deploy slot per segment (NFO, NSE, MCX, CDS, Delta, NASDAQ-EQ), none used. Live-auto execution allowance 1 on NFO/NSE/MCX. Private
  strategies: 37 of 9999 used. Website backtests: 25 allowed on NSE, 0 used (MCX/CDS/US: 0).
- **Brokers on NFO/NSE:** Nuvama Wealth, and MIRAE ASSET Sharekhan (Open API; also CDS, MCX). A Live Offline deploy attaches the primary broker for the exchange, else the first connected.
- **Wallet:** ₹0. Chat/MCP backtests cost ₹20 each from the wallet, so none are affordable now. The prepaid pack (33 purchased, all used) expired its cycle on 2023-07-24. The website's own Backtest
  button has a separate 25-run allowance, which is the free route.
- **Deployed strategies:** none. **Saved templates:** 38, all 2023-era (e.g. `Nifty Iron Condor - Positional` id 2757809, `Long Straddle 120`, `Calendar Spread`); `tt_get_strategy(id)` reads one for
  free.
- **`tt_create_strategy` refused (2026-10-04):** HTTP 422 `Template creation/update limit exceeded for current subscription`, request id `6c3d8dc1754347a6a8cdd8a399826e00`. `tt_get_my_subscription`
  showed `create_private_strategy` 37 used of 9999, so the plan-usage figures do not reflect the real cap; the account holds 38 templates. Nothing was created or deployed. Retrying will not help; the
  account must free a template (delete on the website; there is no delete tool) or upgrade. The same limit presumably blocks `tt_update_strategy`, so editing an existing template is not a workaround.
  The probe markdown validated clean and is reproducible from the Greeks section.
- **Update, same day:** after the user deleted all 38 templates, `tt_create_strategy` succeeded (template `NS Greeks Probe`, id 999078810, edit_url `https://tradetron.tech/strategies/999078810/edit`;
  the Greeks-probe markdown from this doc, guard seeded at 1 → 2). `tt_deploy_strategy_paper` then refused: `STRATEGY_DEPLOY_NO_PAPER_BROKER` ("Connect a broker for NFO"). `tt_get_my_brokers` now
  returns **no brokers at all**, where it listed Nuvama Wealth and Sharekhan earlier that day, so the connections were lost at some point in between (cause unknown; possibly removed with the
  deletions, or expired). A Live Offline deploy needs a connected broker on the exchange; reconnect at `https://tradetron.tech/user/broker-and-exchanges` with the user's own login (never via chat).
- **Deployed (2026-10-04):** the user deployed the probe themself on **Dhan**. Deployed id (SID) **999158894**, template 999078810, `LIVE OFFLINE`, status `Active`, no error, multiplier 1, capital
  100000, broker Dhan on NFO (broker_id 369). No events or orders yet (market closed). `tt_get_my_brokers` lists Dhan with exchange `unknown` and still reports NFO as missing, so its exchange mapping
  is unreliable for Dhan; trust the deployment detail's `brokers[].exchange` instead. The deployment occupies the Free plan's single NFO slot.
- **Update 2026-10-05:** SID 999158894 entered at 04:00 UTC (leg CE 22550, qty 65) and wrote its snapshot; its Greeks looked non-ATM (see "Greeks probe results"). The template was patched (14 vars
  `ATM` → `ATM-SPOT`, plus `strike_spot`) and the user redeployed as SID **999167718** (Live Offline, Dhan on NFO, `Live-Entered` at 04:38 UTC). The old SID no longer appears in
  `tt_get_my_deployed_strategies`. `tt_deploy_strategy_paper` still refused with `STRATEGY_DEPLOY_NO_PAPER_BROKER` until the user reconnected the broker; the user did the deploy themself.
- Free-plan data delay (1 min) matters for any Greeks or strike-selection comparison against NiftyShield's own snapshots.

## Verified findings

**2026-10-04, `tt_check_underlying_support("NIFTY")`:** resolves to `NIFTY 50`, exchange NFO, index futures + options (`FUTIDX`, `OPTIDX`), **lot size 65**, `emitter_buildable: true`. Compare with the
lot size the repo assumes before sizing any ported strategy.

**2026-10-04, `tt_list_backtests(limit=5)`:** the account has runs going back to 2022 (`has_more: true`). The five returned are all 2022–2023 (Nifty Mirage, New AJ straddles, Dynamic V4 TSL), each
`finished: false`, `readable: false`, `status: active` — `status` is not authoritative, and `readable: false` means `tt_backtest_result` cannot read them. These look like legacy runs, not usable
baselines. Rows carry no P&L and no `report_url`. Row order was oldest-first in this sample; page with `offset`/`next_offset` or filter by `template_id` to reach recent runs.

## Open questions

- Do any recent runs exist on the account? Page `tt_list_backtests` or call `tt_list_my_strategies` and then `tt_backtest_workbench`.
- Per-run backtest fee, daily free allowance and wallet balance: only `next_run.quote` from `tt_backtest_workbench` is authoritative; never estimate.
- Whether backtests cover Tuesday-expiry NIFTY weeklies (expiry moved Thursday→Tuesday, April 2026; see `REFERENCES.md`). `tt_check_backtestability` with a real template and window should answer it.
- Whether the IC strategies in `docs/strategies/` can be expressed without BT-unsupported keywords (`Leg SL trail`, `PCR`, `Total OI`).
- Brokers and underlyings supported on the current plan; signal-bridge payload shape and latency vs. NiftyShield's snapshot cadence.
