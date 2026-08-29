# Paper P&L Golden Test Addition — Story

**Source:** `docs/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 row 13 (ERROR) — FR-5 PNL-1.

## T1

Add 1-2 exact-value assertions directly into `tests/unit/test_pnl_hypothesis.py` for `_compute_leg_unrealized_pnl` —
e.g. a known short-CE position with a specific entry price, LTP, and lot size, asserting the exact `Decimal` P&L result, plus one for a long leg.
Use `get_code_snippet('_compute_leg_unrealized_pnl')` first to confirm the exact signature
and sign convention before writing the fixture (per CLAUDE.md Step 4's mandatory pre-step for domain-model test helpers).

**Files touched:** `tests/unit/test_pnl_hypothesis.py`

**Tests:** happy-path + error/edge-case per CLAUDE.md Step 4, in the files listed above.
