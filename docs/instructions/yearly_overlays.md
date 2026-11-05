# Yearly Overlay Book — Operator Runbook

> Ops wiring for the December-only (`--expiry-type yearly`) CC / PP / Collar book. Facts here are verified against `src/strategy/overlay_tenor.py`, `scripts/monitor_daemon.py` and
> `src/paper/constants.py` as of YW-2 (2026-11-05). Epic: `docs/plan/yearly-overlays/`.

## Monitor flag

`MONITOR_YEARLY_OVERLAYS` (settings field `monitor_yearly_overlays`, default off) registers three yearly instances, `CCOverlayV1`, `PPOverlayV1` and `CollarOverlayV1`, next to the monthly ones. It
only takes effect when `MONITOR_OVERLAYS=1` is also set; with the flag off the daemon registers the monthly instances only, exactly as before. If the BOD lookup failed to load, the daemon logs an
error and skips the yearly book instead of crashing. The yearly book reads its chain through the routed `ChainSource`, which stays Upstox-only by default. To let it fall back to Dhan Greeks (Upstox
returns zero Greeks past about 90 DTE) set `MARKET_DATA__CHAIN__SOURCES='["upstox","dhan"]'` together with `DHAN_ACCESS_TOKEN` and `DHAN_CLIENT_ID`.

The yearly instances run on a 3600 s monitor cadence (monthly stays on the daemon's 90 s poll). Policy values, from `OVERLAY_TENORS["yearly"]`: entry floor 20 DTE, review and exit at 15 DTE, re-entry
floor 20 DTE, PP roll at 15 DTE, profit target when 75% of sold premium has decayed, delta stop 0.55, premium backstop at 2.5x entry premium. The backstop is alert-only, and the profit target and
backstop apply to short-call legs only (CC and the Collar call); PP and the Collar put are hedges with neither.

## Ledger names and collateral

The yearly book has one `strategy_name` per overlay: `paper_nifty_overlay_yearly_cc`, `paper_nifty_overlay_yearly_pp`, `paper_nifty_overlay_yearly_collar`. The monthly book keeps the single
`paper_nifty_overlay` name split by `leg_role`. Its collateral gate is separate: yearly open lots are never added to the monthly NiftyBees pool and the reverse, and `YEARLY_NIFTYBEES_UNITS = 5400` in
`src/risk/collateral_gate.py`: the yearly book has its own separate holding of ~5,395.68 NiftyBees units, rounded to 5400 by Animesh on 2026-11-05. The monthly gate reads only `paper_nifty_spot`, so
the pools do not overlap. Edit the constant if the holding changes.

## Host cron lines (listed, not installed)

Animesh adds these on the host. They mirror the monthly lines (`--auto-cc` / `--auto-collar` Wednesdays, `--auto-pp` weekdays), staggered five minutes so the two books never run together.
`--expiry-type` is rejected without one of the `--auto-*` flags.

```
35 10 * * 3   cd $NS && $NSPY -m scripts.strategies.three_track.paper_3track_overlay_entry --auto-cc --expiry-type yearly >> logs/cc_yearly_entry.log 2>&1
35 10 * * 3   cd $NS && $NSPY -m scripts.strategies.three_track.paper_3track_overlay_entry --auto-collar --expiry-type yearly >> logs/collar_yearly_entry.log 2>&1
35 10 * * 1-5 cd $NS && $NSPY -m scripts.strategies.three_track.paper_3track_overlay_entry --auto-pp --expiry-type yearly >> logs/pp_yearly_entry.log 2>&1
```

The yearly entry depends on a fresh `data/instruments/NSE.json.gz` (`bod_instruments_path`). A stale file leaves the nearest live December missing or its strikes unresolved, so the yearly selection
comes back empty and no entry happens. The Sunday 07:00 host curl refresh keeps it current; check the file date before the first run and after any gap in that cron.

## Schema

No new table. The YF-1 audit (`docs/plan/yearly-overlays/yearly-foundation/audit.md` §C) found that the yearly namespace rides existing tables: `paper_trades`, `paper_nav_snapshots`,
`paper_leg_snapshots`, `paper_exit_events` and `paper_overlay_pnl_snapshots` (keyed `(strategy_name, overlay_type, snapshot_date)`) all key on `strategy_name`, so the three yearly names need no
migration. The Greeks provenance columns (`delta_source`, `delta_asof`, `chain_source`, `chain_fetched_at`) are separate DSN-2 work.
