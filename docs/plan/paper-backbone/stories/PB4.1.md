# PB4.1 — `src/strategy/nifty_track_comparison_v1.py`: NiftyTrackComparisonV1 + tests
> **Assigned to: Claude** — live leg_role values must be verified mid-impl from existing paper_trades data.

**Files to change:**
- `src/strategy/nifty_track_comparison_v1.py` — `NiftyTrackComparisonV1` implements `PaperStrategy`
- `tests/unit/strategy/test_nifty_track_comparison_v1.py` — new test file

**Before implementing:** Read `docs/strategies/nifty_track_comparison_v1.md` — authoritative spec.

**Context:** 3-track already runs via `paper_3track_snapshot.py` (EOD cron) and
`paper_3track_overlay_roll.py` (manual roll). This phase adds WARN event routing so
the daemon delivers roll reminders via Telegram. No ACTION events — rolls remain manual.
`paper_3track_snapshot.py` is retained alongside the backbone during the migration period.

**What to implement:**

```python
class NiftyTrackComparisonV1:
    strategy_name = "paper_nifty_3track_v1"

    TRACK_STRATEGY_NAMES = [
        "paper_nifty_spot",
        "paper_nifty_futures",
        "paper_nifty_proxy",
    ]
```

`check_signals()` covers all three tracks as a single registered strategy:

| Event type | Severity | Trigger |
|---|---|---|
| `ROLL_DUE_DTE` | WARN | any open overlay leg with DTE ≤ 5 |
| `ROLL_DUE_DECAY` | WARN | any short overlay premium ≤ 25% of entry |
| `OVERLAY_EXPIRED` | WARN | overlay expiry date has passed with no roll recorded |

No ACTION events. `apply_action()` is a no-op (returns positions unchanged) — document
clearly that rolls are executed manually via `paper_3track_overlay_roll.py`.

`describe_context()` — returns: track name, leg role, DTE remaining, current premium vs
entry premium, % captured.

**Tests (`tests/unit/strategy/test_nifty_track_comparison_v1.py`):**

- No open overlay legs → `[]`.
- Overlay leg with DTE = 4 → `ROLL_DUE_DTE` WARN event; `payload` contains track name.
- Short overlay with premium = 22% of entry → `ROLL_DUE_DECAY` WARN.
- Overlay leg with expiry yesterday, no roll recorded → `OVERLAY_EXPIRED` WARN.
- Healthy overlays (DTE 15, premium 60%) → `[]`.
- All three tracks trigger simultaneously → three separate WARN events.
- `apply_action` called with any action → returns positions unchanged, no error.

**Commit:** `feat(strategy): add NiftyTrackComparisonV1 backbone integration`

---

## Pre-baked Context

> Graph queries pre-run 2026-05-31. Skip "Before any code" graph calls — use these directly.

**`PaperStrategy`** — `src/strategy/protocol.py` (PB1.1). Protocol with `strategy_name` class attr.

**`PaperPosition`** — `src/paper/models.py:95`. Dataclass.
Fields: `strategy_name: str`, `leg_role: str`, `net_qty: int`, `avg_cost: Decimal`,
`avg_sell_price: Decimal`, `instrument_key: str`.

**3-track strategy names in live DB** — confirmed from `scripts/strategies/three_track/paper_3track_snapshot.py`:
`"paper_nifty_spot"`, `"paper_nifty_futures"`, `"paper_nifty_proxy"`.
Overlay leg_role values: `"overlay_cc"`, `"overlay_pp"`, `"overlay_collar_call"`, `"overlay_collar_put"`.
Base leg_role values: `"base_etf"`, `"base_futures"`, `"base_ditm_call"`.
Only overlay legs trigger WARN events — filter by `leg_role.startswith("overlay_")`.

**`SignalEvent`** — `src/strategy/protocol.py`. Only `"WARN"` severity used here.
`payload` dict should include at minimum `{"track": strategy_name, "leg_role": leg_role, "dte": dte}`.
