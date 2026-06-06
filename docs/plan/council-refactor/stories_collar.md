# council-refactor — Collar Automation Stories

> Shared context, signal tables, ReEntryMixin contract: `README.md`
> Prerequisite: CC-1 + CC-2 + CR1d committed.

---

## Design Decision: Collar as a Single Unit

Short call + long put are managed and exited as one position. Exit signals are
evaluated on the short call leg only (using `evaluate_cc()` — identical logic).
On any ACTION signal, `CLOSE_COLLAR` closes both legs atomically via
`OverlayCloser.close_collar` (call-first sequencing, already implemented).

The long put is dragged along silently. It has no independent exit signal in this
design — it exists only to define the floor for the underlying position. If a crash
monetization is needed, the user should be running a standalone PP position, not a collar.

Profit target: 70% of short call entry credit captured (LTP ≤ 30% of entry).
This matches CSP and CC — uses the shared `_PROFIT_TARGET_RETENTION = Decimal("0.30")`
constant introduced in CR1b.

---

## Signal Table (Collar, evaluated each EOD)

Evaluated on the **short call leg** only. Signal set mirrors CC exactly.

| Priority | Signal | Trigger | Action | Severity |
|---|---|---|---|---|
| 1 | `LOSS_STOP` | short call mark ≥ 2.5× entry | CLOSE_COLLAR | ACTION |
| 2 | `DELTA_STOP` | call delta ≥ 0.55 | CLOSE_COLLAR | ACTION |
| 3 | `PROFIT_TARGET` | short call LTP ≤ 30% of entry, entry ≥ ₹15 | CLOSE_COLLAR + re-entry check | ACTION |
| 4 | `TIME_STOP` | days_held ≥ 21 | CLOSE_COLLAR + re-entry check | ACTION |
| 5 | `DELTA_WARN` | call delta ≥ 0.45 | — | WARN |
| 6 | `DTE_REVIEW` | DTE ≤ 5 | — | WARN |

Re-entry is checked after PROFIT_TARGET and TIME_STOP only — same gate as CC.
LOSS_STOP and DELTA_STOP exits are adverse outcomes; re-entry requires a fresh assessment
by the user. Script hint sent via Telegram on ELIGIBLE: closes both call and put sides.

---

## COLLAR-1 `[Antigravity]` — `CollarOverlayV1` full automation

**Files:**
- `src/strategy/collar_overlay_v1.py` (major changes — auto_execute, ReEntryMixin, apply_action)
- `src/strategy/exit_signals.py` (remove `evaluate_collar`; CollarOverlayV1 calls `evaluate_cc` directly)
- `tests/unit/strategy/test_collar_overlay_v1.py` (extend / rewrite)

**Prerequisites:** CC-1 committed (`evaluate_cc` aligned, `_PROFIT_TARGET_RETENTION` introduced),
CC-2 committed (`ReEntryMixin`), CR1d committed (StrategyMonitor auto-execute dispatch,
`TelegramGateway.send_notification`).

**Before any code:**
- `get_code_snippet("CollarOverlayV1")` — current implementation; confirm only 75% signal, no __init__
- `get_code_snippet("evaluate_collar_call")` — **this is the real function name** (not `evaluate_collar`);
  note its current thresholds: profit target 25% decay (not 30%), DTE_FORCED branch present.
  Both will be removed — calling `evaluate_cc` directly is a **behavioral change**, not a no-op refactor.
- `get_code_snippet("evaluate_collar_put")` — also present; will also be removed.
- `get_code_snippet("evaluate_cc")` — confirm CC-1 committed; uses `_PROFIT_TARGET_RETENTION` (30%)
- `get_code_snippet("OverlayCloser.close_collar")` — confirm call-first sequencing exists
- `get_code_snippet("ReEntryMixin")` — confirm CC-2 committed; class attr names + `_check_reentry` signature
- `get_code_snippet("CCOverlayV1")` — reference implementation for CC-4 pattern
- `search_graph("_CC_SIGNAL_ACTION_MAP")` — reference constant name from CC-4

---

### Changes to `exit_signals.py`

Remove `evaluate_collar_call()` and `evaluate_collar_put()` entirely. The collar short call
exit logic is now handled by `evaluate_cc()` directly in `CollarOverlayV1.check_signals()`.

**This is a behavioral change — not a no-op refactor:**
- Old `evaluate_collar_call`: profit target at 25% decay (LTP ≤ 75% of entry); DTE_FORCED branch
  with ITM/delta/residual sub-conditions.
- New (via `evaluate_cc`): profit target at 30% decay (`_PROFIT_TARGET_RETENTION`); no DTE_FORCED;
  DTE_REVIEW flat WARN at DTE ≤ 5; DELTA_STOP at 0.55; TIME_STOP at 21 days.

Document this threshold change in `DECISIONS.md` when closing (CR4). Verify no other caller
references `evaluate_collar_call` or `evaluate_collar_put` — use `search_graph` before deleting.

---

### Changes to `collar_overlay_v1.py`

**1. Inherit `ReEntryMixin`:**

```python
class CollarOverlayV1(ReEntryMixin):
```

**2. Class attributes:**

```python
auto_execute: ClassVar[bool] = True
reentry_leg_role: ClassVar[str] = "overlay_collar_call"
reentry_script_hint: ClassVar[str] = "run find_overlay_strikes.py --overlay-type collar"
```

**3. Constructor** — accepts `store`, `notifier`, `vix_data_dir`
(currently `CollarOverlayV1` has no `__init__`):

```python
def __init__(
    self,
    store: Any = None,
    notifier: Any = None,
    vix_data_dir: Path | str | None = None,
) -> None:
    self._store = store
    self._notifier = notifier
    self._vix_data_dir = Path(vix_data_dir) if vix_data_dir is not None else None
```

**4. Signal → action mapping** (module-level constant):

```python
_COLLAR_SIGNAL_ACTION_MAP: dict[str, str] = {
    "PROFIT_TARGET": "CLOSE_COLLAR",
    "LOSS_STOP":     "CLOSE_COLLAR",
    "DELTA_STOP":    "CLOSE_COLLAR",
    "TIME_STOP":     "CLOSE_COLLAR",
}
```

**5. `check_signals()`** — evaluate using `evaluate_cc()` on the short call leg;
map to COLLAR action payloads:

For ACTION results:
```python
payload["auto_execute"] = True
payload["auto_action"] = "CLOSE_COLLAR"
payload["valid_actions"] = ["CLOSE_COLLAR"]
payload["triggering_signal"] = result.exit_signal
```

WARN and INFO results: payload unchanged — no `auto_execute` key.

`days_held` calculation (same pattern as `CCOverlayV1`):
```python
days_held = (today - pos.entry_date).days if pos.entry_date is not None else 0
```

`pos` here is the short call leg (`overlay_collar_call`).

**6. `apply_action()`** — handle `CLOSE_COLLAR`:

```python
async def apply_action(
    self,
    positions: list[PaperPosition],
    action: ApprovedAction,
) -> list[PaperPosition]:
    if action.action_type != "CLOSE_COLLAR":
        raise ValueError(f"CollarOverlayV1 only accepts CLOSE_COLLAR; got {action.action_type!r}")

    # Find both legs (used for notification data)
    call_pos = next(
        (p for p in positions if p.leg_role == "overlay_collar_call"),
        None,
    )
    put_pos = next(
        (p for p in positions if p.leg_role == "overlay_collar_put"),
        None,
    )

    # Close both legs atomically via OverlayCloser (call-first sequencing)
    # OverlayCloser.close_collar handles rollback if put close fails after call close
    updated = [
        p for p in positions
        if p.leg_role not in {"overlay_collar_call", "overlay_collar_put"}
    ]

    # Re-entry check for PROFIT_TARGET and TIME_STOP only
    triggering_signal = action.metadata.get("triggering_signal") if action.metadata else None
    if triggering_signal in ("PROFIT_TARGET", "TIME_STOP") and call_pos is not None:
        expiry = self._parse_expiry(call_pos.instrument_key)
        await self._check_reentry(
            expiry=expiry,
            today=date.today(),
            instrument_key=call_pos.instrument_key,
        )

    # Telegram notification (non-fatal)
    await self._send_close_notification(call_pos, put_pos, triggering_signal)

    return updated
```

**7. `_send_close_notification`** — HTML format via `self._notifier.send_notification`:

```
✅ <b>Collar: CLOSE ({signal})</b>
📤 Short Call: {call_key} @ ₹{call_exit:.2f}
   Entry ₹{call_entry:.2f} · Delta {call_delta:.3f} · DTE {call_dte}
📤 Long Put: {put_key} @ ₹{put_exit:.2f}
   Entry ₹{put_entry:.2f} · Delta {put_delta:.3f}
Net P&amp;L: <b>₹{net_pnl:+,.0f}</b>
```

Non-fatal: wrap in `try/except Exception`, log error, never raise to caller.
If either leg is `None` (partially closed collar — unexpected), log a warning and
send a degraded notification with available data rather than crashing.

---

### Tests (`tests/unit/strategy/test_collar_overlay_v1.py`)

**Signal routing — delegates to `evaluate_cc`; verify mapping and payload shape:**

- PROFIT_TARGET fires on short call → `auto_execute=True`, `auto_action="CLOSE_COLLAR"`,
  `triggering_signal="PROFIT_TARGET"`, `valid_actions=["CLOSE_COLLAR"]`
- TIME_STOP fires → `auto_execute=True`, `triggering_signal="TIME_STOP"`
- LOSS_STOP fires → `auto_execute=True`, `triggering_signal="LOSS_STOP"`
- DELTA_STOP fires → `auto_execute=True`, `triggering_signal="DELTA_STOP"`
- DELTA_WARN fires → no `auto_execute` key in payload (WARN only)
- DTE_REVIEW fires → no `auto_execute` key in payload (WARN only)
- No collar short call in positions → `check_signals` returns `[]` without crash
- `entry_date=None` on short call leg → `days_held` defaults to 0; no crash

**`apply_action`:**

- `CLOSE_COLLAR` triggered by PROFIT_TARGET → both legs removed from returned positions;
  `_check_reentry` called once
- `CLOSE_COLLAR` triggered by TIME_STOP → `_check_reentry` called once
- `CLOSE_COLLAR` triggered by LOSS_STOP → both legs removed; `_check_reentry` NOT called
- `CLOSE_COLLAR` triggered by DELTA_STOP → both legs removed; `_check_reentry` NOT called
- `action_type="CLOSE_FULL"` → raises `ValueError`
- `notifier=None` → close executes without crash; no notification error raised
- `store=None` → close executes; re-entry skip is graceful (no crash)
- `put_pos` missing from positions (partial collar) → close still executes;
  notification logs warning but does not raise

**Re-entry notification:**

- PROFIT_TARGET close with all gates passing → `send_notification` called with message
  containing `find_overlay_strikes.py --overlay-type collar`
- LOSS_STOP close → `send_notification` called with close notification only;
  NO re-entry notification

**Commit:** `feat(strategy): CollarOverlayV1 full automation — auto_execute, ReEntryMixin, CLOSE_COLLAR unit exit`
