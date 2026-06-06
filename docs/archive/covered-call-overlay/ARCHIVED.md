# Archived — covered-call-overlay

**Archived:** 2026-06-06  
**Absorbed into:** `docs/plan/council-refactor/`

## What happened

CC1 (`compute_max_lots` + `STRATEGY_CC_OVERLAY`) and CC2 (`paper_cc_entry.py`) were implemented
and shipped (SHAs: 0e5ebeb, 972a13c).

The remaining stories (CC3 roll script, CC4 docs close) were superseded or absorbed:

- **CC3** (`paper_cc_roll.py`) → migrated to **CC-5** in `council-refactor/stories_cc.md` with
  corrected thresholds matching `evaluate_cc()` post-CC-1: delta_stop 0.55 (was 0.40), profit_target
  30% remaining (was 50%), loss_stop 2.5× added, time_stop 21d unchanged.
- **CC4** (docs close) → absorbed into **CR4** in `council-refactor/stories_close.md`. CC overlay
  scripts documented there under CONTEXT.md scripts section and DECISIONS.md.

Do not implement from this directory. Load `docs/plan/council-refactor/` instead.
