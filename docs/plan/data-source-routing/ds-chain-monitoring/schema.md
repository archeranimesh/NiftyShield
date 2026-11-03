# DS Chain Monitoring — schema

Additive columns decided by the council ruling (`DECISIONS.md`, "Data source routing …, 2026-10-07"). Check `DB_REGISTRY.md` before DSN-2 and follow the migration pattern `PaperStore` already uses for
added columns; do not invent a new one.

| Table | Column | Type | Values |
|---|---|---|---|
| `paper_leg_snapshots` | `delta_source` | `TEXT NULL` | `upstox`, `dhan`, `last_known`, `unavailable` |
| `paper_leg_snapshots` | `delta_asof` | `TEXT NULL` | ISO timestamp of the delta observation actually used |
| `paper_overlay_pnl_snapshots` | `chain_source` | `TEXT NULL` | `upstox`, `dhan`, `last_known` |
| `paper_overlay_pnl_snapshots` | `chain_fetched_at` | `TEXT NULL` | ISO timestamp |

The source values in the table are the `SourceId` values from `ds-chain-seam/` DSC-1 (plus `last_known` and `unavailable`, which are not sources); a new source adds an enum member and no schema
change.

Rules:

- Provenance is recorded at leg level. If an aggregate delta is persisted at overlay level, the contributing leg observations are linked through `delta_asof`, never collapsed into one source string.
- Both books write the columns from DSN-2 onward (decided 2026-11-03): monthly rows record `upstox`, which is true because the monthly book only reads the Upstox chain; yearly rows record whichever
  source was used. Routing and behaviour of the monthly book are unchanged.
- Rows written before DSN-2 stay `NULL` and readers treat `NULL` as unknown provenance. Nothing is backfilled or inferred as "upstox".
- A pre-existing yearly position needs an explicit, recorded source assignment before the delta-dependent monitor may act on it.
- No new tables. The far-expiry capture store (`dhan-far-expiry-chain/far-expiry-capture/`) is the last-known-delta cache; leg snapshots record which observation was used.
- Decimal and monetary values stay `TEXT` per the settled convention. `paper_overlay_pnl_snapshots` stays keyed `(strategy_name, overlay_type, snapshot_date)`.
