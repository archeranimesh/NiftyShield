# Audit Remediation — 2026-05-15

Source: docs/reviews/audit_2026-05-15.md
Resume rule: read CONTEXT.md → find first unchecked box → implement → test → commit → record SHA → tick box.

## Batch 0 — Style / Hygiene (single commit)
- [x] [1] bhavcopy_loader.py:72 — f-string in logger | SHA: 4d69050
- [x] [2] nuvama/store.py:138,150 — PRAGMA f-string | SHA: 290a1d8
- [x] [3] mock_client.py:36 — assert in prod | SHA: b54569e
- [x] [4] tracker.py:379 — bare except no comment | SHA: 240aa9e
- [x] [5] summary.py:7,8 — TODO without tracker ID | SHA: 1bfa20c
- [x] [6] daily_snapshot.py:47 — sys.path hack | SHA: 46a9bfe
- [x] [7] upstox_market.py:115,165 — inline imports | SHA: 67861d4

## Batch 1 — Coupling / KISS
- [x] [10] bhavcopy_loader.py:13 — hardcoded Path | SHA: e46e96d
- [x] [11] factory.py:67 — forwarding alias | SHA: 8639d44

## Batch 2 — Async Safety
- [x] [12] store.py:142 — blocking __init__ | SHA: 68504ae
- [x] [13] telegram.py:94 — blocking requests.post | SHA: b10aec9

## Batch 3 — Operational
- [x] [14] telegram.py:55 — no rate limit | SHA: 90f7acd
- [x] [15] paper_3track_overlay.py:666 — manual rollback | SHA: f54063c
- [x] [16] bhavcopy_ingest.py:334 — missing lineage metadata | SHA: 9874d84
- [x] [17] daily_snapshot.py — no cron heartbeat | SHA: 6f2ce32

## Batch 4 — Types / Domain
- [x] [18] protocol.py:42-52 — Any stubs (Interim fix: replaced with dict[str, Any] as cosmetic boundary constraint; schema validation pending TD-7) | SHA: 7cd5872
- [x] [19] models/portfolio.py — missing field validators | SHA: 20f0bb3
- [x] [20] store.py:605 — tuples instead of Position | SHA: 1520d3f
- [x] [21] paper_3track_overlay.py — business logic in script | SHA: 80046db

## Batch 5 — SOLID Refactors (each gets its own commit)
- [x] [8] tracker.py:169 — SRP violation | SHA: 3242fbd
- [x] [9] summary.py:236 — OCP strategy branching | SHA: bcde841

## Batch 6 — Financial Correctness (each gets its own commit)
- [ ] [22] ilts.py:49 — hardcoded lot_size=65 | SHA:
- [ ] [23] bhavcopy_ingest.py:143,189 — no VWAP distinction | SHA:
- [ ] [24] lookup.py:317 — DTE bands, no cadence awareness | SHA:
- [ ] [25] dhan/positions.py:167 — flat STT rate | SHA:
- [ ] [26] paper_3track_entry.py:487 — verify T1-C before fixing | SHA:
- [ ] [27] models/portfolio.py:110 — Leg.strike is float | SHA:
- [ ] [28] upstox_market.py:208 — float(price) cast | SHA:
- [ ] [29] tracker.py:208,327 — StrategyPnL float | SHA:
- [ ] [30] summary.py:35,99,171 — float() re-contamination | SHA:
- [ ] [31] protocol.py:68,125 — MarketDataProvider returns float ← START HERE | SHA: