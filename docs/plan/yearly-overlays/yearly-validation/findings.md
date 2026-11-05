# Yearly Validation — findings

## YV-3 live smoke, 2026-11-05

Ran `python -m pytest -m live tests/live/test_yearly_overlay_live_smoke.py` once (3 passed, 4.5 s): `--expiry-type yearly --dry-run` for each entrypoint against the real Upstox chain, a temp DB,
Telegram neutralised. Instrument file `data/instruments/NSE.json.gz` mtime 2026-11-04 21:53 (unchanged by the run). Every run resolved the December 2026 expiry 2026-12-29 (DTE 54, lot 65, 137 chain
rows) and wrote zero rows.

| Entrypoint | Strategy ledger | Selection |
|---|---|---|
| `--auto-cc` | `paper_nifty_overlay_yearly_cc` | `overlay_cc` SELL 103.25 |
| `--auto-pp` | `paper_nifty_overlay_yearly_pp` | `overlay_pp` BUY 163.98 |
| `--auto-collar` | `paper_nifty_overlay_yearly_collar` | `overlay_collar_put` BUY 108.18 and `overlay_collar_call` SELL 103.25 |

These match Animesh's manual check of 2026-11-04 (prices unchanged at that sampling). The default run (no `-m live`) collects and skips the test.
