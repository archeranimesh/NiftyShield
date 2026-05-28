# paper-exit-signals — Design Prompt

## What This Story Builds

Exit signal detection and automated closure for all paper-traded overlay legs:
Covered Call (CC), Protective Put (PP), and Collar. Also fixes the CSP exit
thresholds in `CSPNiftyV1` to match the confirmed council spec.

When this story is complete, the system:
1. Detects exit conditions automatically (EOD + intraday daemon)
2. Fires a Telegram alert with one-tap approval
3. Executes the close sequence without further user action
4. Writes a full audit trail to `paper_exit_events`

---

## Relationship to paper-backbone

This story is a **dependent extension** of paper-backbone, not a replacement.

| paper-backbone provides | paper-exit-signals adds |
|---|---|
| `PaperStrategy` protocol | `ExitSignalEngine` rule engine |
| `StrategyMonitor` daemon (90s tick) | `CCOverlayV1`, `PPOverlayV1`, `CollarOverlayV1` strategy classes |
| `PaperExecutor.apply()` | `OverlayCloser` (atomic multi-leg close with rollback) |
| `TelegramGateway` approval flow | `paper_exit_events` table + dual-signal audit fields |
| `pending_approvals` table | EOD signal write path in `paper_3track_snapshot.py` |
| `CSPNiftyV1` (partial thresholds) | Corrected `CSPNiftyV1` thresholds per council ruling |

**Prerequisite:** paper-backbone tasks PB1.1–PB1.7 and PB4.1 must be committed
before this story begins. Confirm with `search_graph("StrategyMonitor")` and
`search_graph("PaperExecutor")` before opening any file.

---

## Council Authority

All exit thresholds in this story are derived from:

```
docs/council/2026-05-28_paper-trade-exit-philosophy.md — Stage 3 Chairman Synthesis
```

No threshold may be changed without a new council decision. The council file is
archived to `docs/council/archive/strategy/` at the close of this story (ES9).

---

## Exit Rules — Canonical Reference

### CSP (corrects PB2.1 thresholds)

| Signal | Severity | Trigger |
|---|---|---|
| `PROFIT_TARGET` | ACTION | put mark ≤ 50% of entry credit |
| `LOSS_STOP` | ACTION | put mark ≥ **1.75×** entry credit ← (PB2.1 had 2.0×, wrong) |
| `DELTA_STOP` | ACTION | short put \|delta\| ≥ **0.45** ← (PB2.1 had 0.35, wrong) |
| `DELTA_WARN` | WARN | short put \|delta\| ≥ 0.35 |
| `TIME_STOP` | ACTION | 21 calendar days elapsed since entry |
| `DTE_REVIEW` | WARN | DTE ≤ 5 |

### Standalone CC

| Signal | Severity | Trigger |
|---|---|---|
| `PROFIT_TARGET` | ACTION | call mark ≤ 50% of entry credit AND entry credit ≥ ₹15/unit |
| `BELOW_FLOOR` | INFO | entry credit < ₹12/unit — do not use % exit; hold to DTE |
| `LOSS_STOP` | ACTION | call mark ≥ **2.5×** entry credit |
| `DELTA_STOP` | ACTION | short call delta ≥ **+0.55** |
| `DELTA_WARN` | WARN | short call delta ≥ +0.45 |
| `DTE_FORCED` | ACTION | DTE ≤ 5 AND (call ITM OR delta ≥ +0.30 OR residual ≥ ₹5/unit) |

### PP (Protective Put)

| Signal | Severity | Trigger |
|---|---|---|
| `CRASH_MONETIZE` | ACTION | put delta ≤ −0.80 OR put value ≥ 5× entry debit AND bid/ask ≤ 10% of mid |
| `DTE_REVIEW` | INFO | DTE ≤ 5 (informational only — PP holds to expiry by default) |

### Collar

| Signal | Severity | Trigger |
|---|---|---|
| `COLLAR_CALL_DECAY` | ACTION | short call mark ≤ **25%** of entry credit (75% decay) OR residual ≤ ₹3/unit AND DTE > 7 → close call only, keep put |
| `COLLAR_CALL_WARN` | WARN | short call delta ≥ +0.55 (informational — no independent stop) |
| `COLLAR_CLOSE_ALL` | ACTION | operator-initiated full exit; recorded as `MANUAL_OVERRIDE` |
| `COLLAR_PUT_CRASH` | ACTION | put delta ≤ −0.80 OR value ≥ 5× entry debit AND spread ≤ 10% of mid |
| `DTE_FORCED` | ACTION | DTE ≤ 5 AND (short call ITM OR call delta ≥ +0.50) |

---

## Closure Execution Sequences

### CC profit target / DTE_FORCED
```
1. BUY back short call at simulated fill (PaperFillSimulator)
2. Write paper_exit_events row: exit_signal=PROFIT_TARGET, status=ACTED
```

### CC loss stop / delta stop
```
1. BUY back short call at loss-stop slippage (1.5× base model)
2. Write paper_exit_events row: exit_signal=LOSS_STOP or DELTA_STOP, status=ACTED
3. Log delta_stop_would_fire and premium_stop_would_fire for Q2 validation
```

### PP crash monetisation
```
1. SELL long put at mid (bid/ask spread gated)
2. Evaluate replacement: if DTE ≥ 14 and liquidity, BUY fresh lower-strike put
3. Write paper_exit_events row: exit_signal=CRASH_MONETIZE
4. If replacement bought: write new paper_trade entry for replacement leg
```

### Collar call decay (close call, keep put)
```
1. BUY back short call
2. Keep long put and base long — do NOT touch them
3. Write paper_exit_events row: exit_signal=COLLAR_CALL_DECAY
```

### Collar full exit (MANUAL_OVERRIDE)
```
Atomic sequence (rollback on any failure):
1. BUY back short call       → if fails: abort, log, alert
2. SELL long put              → if fails: re-SELL short call to restore, log, alert
3. Both succeed: record both closes in paper_trades
4. Write paper_exit_events row: exit_signal=COLLAR_CLOSE_ALL, notes=MANUAL_OVERRIDE
```

### Collar put crash monetisation
```
1. BUY back short call first (likely near-worthless in crash)
2. SELL long put to monetise
3. Evaluate replacement protection if DTE ≥ 14
4. Write paper_exit_events row: exit_signal=COLLAR_PUT_CRASH
```

---

## Dual-Signal Audit (Q2 Council Mandate)

For every sell-leg exit event (CC and Collar short call), always record:
- `delta_stop_would_fire` — would the delta threshold have triggered?
- `premium_stop_would_fire` — would the premium multiple have triggered?
- `actual_rule_used` — which rule fired the event

After 6–12 cycles, compare these fields to determine which mechanism produces better
exit timing and lower adverse excursion. This resolves the council's Q2 minority dissent.

---

## Detection Tiers

**Tier 1 (EOD — mandatory for Phase 0):**
`paper_3track_snapshot.py` calls `ExitSignalEngine.evaluate()` for every open leg
at EOD. Writes to `paper_exit_events` with `detected_by=EOD`. Telegram alert fires
for any ACTION signal. User approves next morning via Telegram button.

**Tier 2 (Intraday — daemon, deferred):**
`StrategyMonitor._tick()` calls `CCOverlayV1.check_signals()` etc. every 90 seconds.
WARN events → plain Telegram message. ACTION events → `pending_approvals` row +
Telegram inline keyboard. `TelegramGateway` callback handler fires `OverlayCloser`.
Tier 2 is wired in this story but disabled in Phase 0 via `MONITOR_OVERLAYS=0` env var.

---

## Archive Gates (ES9)

After ES9 docs close, two files are archived:

1. `docs/council/2026-05-28_paper-trade-exit-philosophy.md`
   → `docs/council/archive/strategy/`
   Reason: all 10 Summary Table decisions are encoded in DECISIONS.md + this story.

2. `docs/strategies/csp_nifty_v1.md`
   → `docs/strategies/archive/`
   Reason: `CSPNiftyV1` class + `ExitSignalEngine` is now the authoritative
   implementation. The markdown spec is redundant — the code is the spec.
   A one-line deprecation notice is added at the top of the archived file
   pointing to `src/strategy/csp_nifty_v1.py` and this story.

Both archives are git moves (`git mv`), not deletes — full history preserved.
