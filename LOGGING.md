# Logging Standard

> Why this exists: a full audit of `logs/` (2026-07-03, see `docs/bugs/bugs.md` BUG-010) found
> six incompatible log line formats in circulation — raw `print()`, bare stdlib `logging`,
> unconfigured structlog, a bespoke bracket format, and human-report text all mixed into the
> same files. Debugging required eyeballing each file's shape instead of grepping one pattern.
> This doc is the single rule set going forward. New code that doesn't follow it should be
> flagged in code review.

---

## The one rule

**Every entrypoint script must call `setup_logging()` (from `src/utils/logging.py`) before
any logging happens, and every log line must go through a `structlog` logger obtained via
`structlog.stdlib.get_logger(...)` (or the project's `_SCRIPT_NAME` convention in `scripts/`,
per root `CLAUDE.md`). Nothing else is allowed to write to a log file.**

That one rule, enforced everywhere, eliminates every format found in the BUG-010 audit except
the documented third-party exception (below).

---

## What "nothing else is allowed" rules out

### 1. `print()` for anything that is logically a log line

```python
# Wrong
print(f"ERROR: post_expiry_gate: current month expiry {expiry} has not yet passed")

# Right
logger.error("post_expiry_gate.blocked", expiry=str(expiry), today=str(today))
```

`print()` has no level, no timestamp, no module tag — it cannot be filtered, cannot be
correlated with a trace ID, and doesn't get routed anywhere structured logging does (JSON mode,
log aggregation, alerting). If it's worth writing to a log file, it's worth a level.

**Exception — human-readable report bodies** (Telegram messages, EOD audit tables, comparison
reports): these are legitimate to render as multi-line text, but the *rendering* is not the log
line. Log the fact that the report was produced/sent as one structured event, with the
rendered text as a value:

```python
report_text = build_ic_eod_report(...)   # the 📋/table/emoji block — fine as-is
logger.info("ic_snapshot.report_sent", strategy=config.strategy_name, channel="telegram", body=report_text)
await notifier.send(report_text)
```

This keeps the report human-readable in Telegram while the log file still has a filterable
`event=ic_snapshot.report_sent` line.

### 2. Bare stdlib `logging.getLogger(__name__)` in `src/` or `scripts/`

```python
# Wrong
import logging
logger = logging.getLogger(__name__)
logger.info("upstox.api_call endpoint=%s status_code=%s latency_ms=%s", url, status, latency_ms)

# Right
import structlog
logger = structlog.stdlib.get_logger(__name__)
logger.info("upstox.api_call", endpoint=url, status_code=status, latency_ms=latency_ms)
```

`setup_logging()` configures the stdlib root handler with `format="%(message)s"` specifically
so that third-party libraries routed through stdlib (requests, aiohttp) come out consistent —
but that means any first-party code using stdlib `logging` directly instead of `structlog`
loses the timestamp/level/module processors entirely and renders as a bare message. This is
exactly what happened in `src/client/upstox_market.py` (BUG-010, format 2).

Confirmed real exceptions: none in `src/`/`scripts/`. Third-party SDK internals (e.g. Nuvama's
`APIConnect` library) manage their own logger and are out of our control — see the exception
section below.

### 3. `structlog.get_logger(...)` without `setup_logging()` ever being called

Declaring a module-level `logger = structlog.get_logger(...)` is correct, but if the
*process entrypoint* never calls `setup_logging()`, structlog falls back to its own default
configuration — a different renderer, different timestamp format, lowercase padded level
(`[warning  ]`), and no `[module]` bracket. This was the root cause of format 4 in BUG-010:
every file in `scripts/strategies/ic/` declares a structlog logger correctly but none of them
call `setup_logging()`.

**Rule:** any script with `if __name__ == "__main__":` (or an `async def main()` entrypoint)
must call `setup_logging()` as the first action, before any other import-time or runtime
logging can fire.

```python
def main() -> None:
    from src.utils.logging import setup_logging
    setup_logging()
    ...
```

### 4. Bespoke hand-rolled formats

`scripts/portfolio/daily_snapshot.py` writes `[2026-06-15 15:45:01] Daily snapshot for ...`
followed by indented plain-text detail lines — a third format that is neither the structlog
pipeline nor a `print(f"LEVEL: ...")` line. There is no good reason for a script to invent its
own timestamp/formatting convention; route it through the same `logger.info(...)` calls as
everything else.

---

## Required shape of every log line

Once every script calls `setup_logging()` and uses `structlog.stdlib.get_logger(...)`
exclusively, every line has this shape (console/plain mode, the default):

```
2026-07-03 15:45:05 [WARNING] [scripts] [strategies] [ic] [paper_ic_snapshot] ic_snapshot.no_expiry_found strategy=paper_ic_nifty_v1_monthly
```

| Part | Meaning |
|---|---|
| `2026-07-03 15:45:05` | Local timestamp (`TimeStamper`, `utc=False`) |
| `[WARNING]` | Level, uppercased, unpadded |
| `[scripts] [strategies] [ic] [paper_ic_snapshot]` | Dotted logger name split into brackets — tells you exactly which module emitted the line |
| `ic_snapshot.no_expiry_found` | The **event** — a short, dot-namespaced, machine-greppable identifier, not a full sentence |
| `strategy=paper_ic_nifty_v1_monthly` | Structured context as `key=value` pairs — add as many as are useful for debugging, they all render the same way |

### Event naming

Use `<module>.<condition>` style event names (`gate.ivr_violation_logged`,
`ic_snapshot.no_expiry_found`, `dte.outside_range`) — not prose. This is what makes the
difference between "grep for `ERROR`" reliably finding every failure versus missing half of
them because one code path wrote `"ERROR: something"` as a string and another wrote a real
`level=error` field.

### Keyword args, not `%`-style, not f-strings — for structlog calls specifically

```python
# Wrong — f-string (evaluated eagerly even if level filtered)
logger.debug(f"Processing {len(orders)} orders for {symbol}")

# Wrong — %-style is a stdlib logging convention; structlog does not consume it the same way
logger.debug("Processing %d orders for %s", len(orders), symbol)

# Right — structlog keyword arguments
logger.debug("orders.processing", count=len(orders), symbol=symbol)
```

**Note on `REVIEW.md` §G7:** that rule ("logger calls must use `%`-style formatting") was
written for stdlib logging and is still correct for any residual stdlib logger call — but after
this migration there should be none. For `structlog` calls (the standard, everywhere), use
keyword arguments as shown above. `REVIEW.md` should be updated to clarify this split the next
time it's touched, so the review checklist doesn't silently allow format-2-style regressions.

---

## What debugging needs that must always be present

At minimum, every log line needs enough to answer "what happened, where, and can I correlate it
with everything else that happened in the same request/run":

- **Timestamp** — always, via the shared `TimeStamper` processor. Never hand-format one.
- **Level** — real level, not a string prefix baked into the message.
- **Module path** — via `structlog.stdlib.add_logger_name`, automatic once you use
  `structlog.stdlib.get_logger(__name__)`.
- **`trace_id`** (where the call originates inside a request/run with a natural correlation
  scope — e.g. one cron invocation, one API round-trip) — bind with
  `bind_trace_id(generate_trace_id())` at the start of the run so every line in that run can be
  grepped together. Already used correctly in `paper_3track_snapshot.py`
  (`trace_id=2755c5a4`) — follow that pattern elsewhere.
- **The actual values involved in the decision**, not just "gate failed" — e.g.
  `gate.ivr_violation_logged gate=0.25 ivr=0.149` (good — has both sides of the comparison) vs.
  `ERROR: India VIX IVR = 0.24 below gate threshold of 0.25.` (same information, but unparseable
  as anything other than a string you have to read).

---

## Silent-failure / degraded-path logging (mandatory)

> Why this section exists: on 2026-07-20, `paper_ic_nifty_v1_monthly` sat at ~70-80% profit
> captured for a full morning with `PROFIT_TARGET` never firing, and the live
> `monitor_daemon.log` showed *nothing wrong* — no ERROR, no WARNING, no exception, just
> `leg_resolved_via_bod` lines that looked healthy. Root cause (`DECISIONS.md` 2026-07-20) was
> a chain of five silent fallback/guard branches, each individually reasonable ("degrade
> gracefully instead of crashing") but collectively invisible — diagnosing it required writing
> a standalone repro script and manually re-running the exact live code path outside the daemon.
> That should never be necessary again.

**Rule: every fallback, guard, or "skip this decision" branch that changes program behavior
must log at the moment it fires — not just the exception paths.** A function that silently
returns `None`/`[]`/a default instead of raising is doing exactly what it's designed to do, and
that is precisely why it needs a log line: nothing else will tell you it happened.

This is a different concern from the sections above (which are about *format* — is it
structlog, does it have a level). This section is about *coverage* — does every branch that
degrades behavior have a log line at all, regardless of format.

### How to recognize a branch that needs this

Ask: "if this line executes, does anything downstream behave differently than the caller
probably expects?" If yes, it needs a log line, even if:
- it's not technically an error (e.g. `expiry_fn()` fallback is a designed feature, not a bug)
- the function's docstring already documents the fallback (documentation is not observability)
- a similar-looking success path is already logged nearby (the *degraded* variant needs its own
  distinct event name — never reuse a healthy-path event for a fallback path, or `grep` for the
  healthy event will silently include failures)

### Event naming for this category

Suffix pattern: `<module>.<condition>_unresolved` / `<module>.<condition>_fallback_used` /
`<module>.<condition>_unavailable` / `<module>.<condition>_gate_skipped` — distinct enough from
plain `_failed`/`_error` events that a reviewer scanning `grep -E "unresolved|fallback|unavailable|gate_skipped"`
across `logs/` gets a complete picture of every degraded-path activation in the system, separate
from actual exceptions.

### Level

`WARNING` if the branch causes a real signal/decision to be silently dropped or computed against
wrong data (this is the BUG-2-follow-up case — `strategy_monitor.expiry_unresolved`,
`strategy_monitor.expiry_fallback_used`, `ic_nifty_v1.mark_unavailable`). `DEBUG` if the branch
is expected/benign and only useful for tracing why a signal *didn't* fire on a given tick (e.g.
`ic_nifty_v1.pnl_gate_skipped` — same underlying condition as the `WARNING` above, logged again
at the point where it changes the caller's outcome, so both "what broke" and "what didn't happen
as a result" are independently greppable).

### Worked example from the 2026-07-20 incident

```python
# Wrong (what existed before) — silent degrade, no trace of why
if self._lookup is not None:
    ...
return None

# Right — the degrade itself is now visible
if self._lookup is not None:
    ...
log.warning(
    "strategy_monitor.expiry_unresolved",
    instrument_key=pos.instrument_key,
    lookup_wired=self._lookup is not None,
)
return None
```

See `src/strategy/monitor.py` (`_get_position_expiry`, `_tick`, `_fetch_chains`) and
`src/strategy/ic_nifty_v1.py`/`ic_nifty_v2.py` (`_compute_combined_pnl`, `check_signals`) for
the full set of fixes this incident produced — use them as the reference pattern for auditing
other silent-fallback branches elsewhere in the codebase (`cc_overlay_v1.py`, `pp_overlay_v1.py`,
and `collar_overlay_v1.py`'s BOD-resolution fallbacks are flagged in `TODOS.md` as still needing
this treatment).

---

## Documented exception: third-party SDK logs

`logs/apiconnect.log` is written directly by the Nuvama `APIConnect` SDK's own internal
logger (`APIConnect.APIConnect`, `APIConnect.http`, comma-millisecond timestamps). This is
vendor code — we don't control its logger configuration and should not try to reformat it.
Leave it in its own dedicated log file (already the case) so it never mixes with first-party
structured logs, and treat its distinct format as expected, not a bug.

If any other third-party library's logger output ends up mixed into a first-party log file in
the future, either (a) route it to its own file the way `apiconnect.log` already is, or (b) if
it must share a file, at minimum don't let it interleave with structured lines mid-stream in a
way that breaks line-oriented parsing.

---

## Migration checklist (tracks BUG-010)

- [ ] `src/client/upstox_market.py` — replace `logging.getLogger(__name__)` with
      `structlog.stdlib.get_logger(__name__)`, convert 3 `%s`-style calls to keyword args.
- [ ] `scripts/strategies/ic/ic_entry_gates.py` — replace `print(f"ERROR/INFO: ...")` with
      `logger.error/info(...)`.
- [ ] `scripts/strategies/ic/paper_ic_entry.py` — same, plus add `setup_logging()` call at
      entrypoint.
- [ ] `scripts/strategies/ic/paper_ic_entry_v2.py` — same.
- [ ] `scripts/strategies/ic/paper_ic_monthly_comparison.py` — add `setup_logging()` call;
      keep the report string, but log a `report_sent` event alongside it.
- [ ] `scripts/strategies/ic/paper_ic_snapshot.py` — same as above.
- [ ] `scripts/portfolio/daily_snapshot.py` — replace the bespoke `[timestamp] message` format
      with `logger.info(...)` calls through the shared pipeline.
- [ ] Update `REVIEW.md` §G7 to distinguish stdlib `%`-style (legacy/third-party passthrough
      only) from structlog keyword-argument calls (the standard for all first-party code).
- [ ] Add "entrypoint calls `setup_logging()`" and "no bare `print()`/`logging.getLogger()` in
      `src/`or `scripts/`" as explicit `code-reviewer` checklist items.

Each item above should close as its own commit per the usual protocol (docs/config-only changes
skip `code-reviewer`; the actual code migrations do not).
