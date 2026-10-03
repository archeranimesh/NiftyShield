# Logging and run correlation (FCID)

> A worked, concrete example of applying the design principles to one specific cross-cutting concern: making every log line from one run traceable end-to-end without grepping disjoint lines by
> timestamp and hoping they line up. This is the pattern actually used in a real refactor — kept here as a template, with the "why this shape and not another" reasoning intact, since that reasoning is
> the reusable part, not the exact names.

## The problem this solves

Once legacy logic is consolidated behind a shared library (see `code-deduplication-and-taxonomy.md`), every caller of that library logs independently, with no way to tell "which of these log lines,
across an external-API client call, a parsing step, and a report-writing step, belong to the same end-to-end run." Debugging a slow or stuck run becomes grepping disjoint log lines by timestamp. This
is cheap to design once, at the point the shared library's logging is first being wired up, and expensive to retrofit once a dozen consumer scripts already log without it.

Treat this as a **design-only** exercise first, separable from implementation: define the convention, diagram the propagation, and land reference pointers in every consumer's plan docs — *before*
building the actual propagation module. This matches the project's own YAGNI stance: design the convention when the need becomes concrete (the shared library's first consumer), implement the
propagation primitives only when a real implementation needs them (not speculatively ahead of any consumer).

## The convention

### Name and scope

One correlation id — call it an FCID (flow/run correlation id), or whatever name fits your domain — per **run**: one invocation of a scheduled job, one investigation script execution, one CLI
invocation, one ad hoc one-off script run. Not one per external API call, not one per log line — calls and log lines are children of a run, identified by the run's FCID plus their own sub-ids (e.g. a
query execution id, a request id).

### Format

A human-greppable, sortable format beats a bare UUID: `f"{entry_point_slug}-{utc_timestamp:%Y%m%dT%H%M%S}-{random_suffix}"` — e.g. `daily-adoption-report-20261001T220500-a1b2c3d4`. Rationale:

- A bare UUID is not greppable or chronologically scannable without parsing structured logs first.
- Prefixing the entry-point's own slug lets you `grep fcid=daily-adoption-report logs/*.log` directly, and the embedded timestamp makes log files sortable by run even without a structured log index.
- A trailing random suffix keeps the id unique under same-second re-invocation (e.g. a retried scheduled job).

### Generation point — exactly once, at the outermost entry point

Mint the FCID exactly once, at the outermost entry point of each consumer type — a scheduled job's main block, a CLI's `main()`, an investigation script's top-level call. Never regenerate it inside
any shared-library adapter or downstream function: if an FCID reaches a lower layer, that layer *uses* it, it never mints a new one. This is what keeps a single run's id stable end-to-end.

### Propagation mechanism — ambient, not threaded through every signature

The naive approach — add an `fcid: str` parameter to every function/method along the call path — works, but it corrupts every signature along the way with a cross-cutting concern, and it directly
violates a shared library's own "thin, constructor-injected, delegation-only" shape once that shape exists (see `design-principles.md`'s DIP section): every adapter method picks up a parameter that
has nothing to do with its actual job.

**This is a deliberate exception to "explicit is better than implicit," not a silent violation of it.** Zen's default is explicit data flow — an ordinary domain value belongs in a function's own
signature, not smuggled in via ambient state, and most of this playbook's own guidance (constructor injection, no hidden collaborators) pushes the opposite direction from what's being chosen here. The
exception is narrow and specific: FCID is not a domain value any function's logic actually consumes, it's pure cross-cutting infrastructure (identical in spirit to a logger instance or a request id in
a web framework's middleware stack) — threading it explicitly would add a parameter to every function in the call graph that no function's own logic needs or uses. Don't generalize this exception to
anything that *is* a real input to the logic it's passed to; `contextvars` is for infrastructure plumbing, not for passing data your function actually operates on.

Python's ambient-context primitive for this is `contextvars`:

```python
from contextvars import ContextVar

_fcid_var: ContextVar[str | None] = ContextVar("fcid", default=None)

def bind_fcid(fcid: str) -> None:
    _fcid_var.set(fcid)

def current_fcid() -> str | None:
    return _fcid_var.get()
```

This is stdlib, thread-safe, and — with an explicit context-copy call — safe across thread-pool/async-task boundaries, which matters the moment any part of a run does concurrent work (e.g. batched API
calls) under one FCID. **This is the one real gotcha**: naively submitting work to a thread pool or async task from inside a context that has the FCID bound does *not* guarantee the worker sees it —
you must explicitly capture and carry the context across that boundary (`contextvars.copy_context()`, or `asyncio`'s own context propagation), or the FCID silently vanishes inside worker
threads/tasks. Treat this as a concrete test case (submit from a bound context, assert the worker-side log line still carries the FCID), not just a reasoning claim — a real implementation found and
fixed exactly this defect after an initial design review had already signed off on a previous version of the concurrency-handling code.

### Log-line shape — auto-injected, never a manual call-site kwarg

Wire the FCID into every log record automatically via a logging filter/middleware (not a manual kwarg passed at every call site): the filter reads the current ambient FCID and sets it on the record;
the project's shared log-setup wires that field into every handler's format string (plain-text or structured/JSON). Example structured line:

```json
{"ts": "2026-10-01T22:05:12Z", "level": "INFO", "fcid": "daily-adoption-report-20261001T220500-a1b2c3d4",
 "logger": "lib.external_client.adapter", "request_id": "q-9f8e...", "tenant": "example-tenant",
 "query_fingerprint": "7c3a1e2b", "event": "query_state_change", "state": "SUCCEEDED", "duration_ms": 4210}
```

Automatic injection is the point: a manual kwarg at each call site will eventually be forgotten at some call site; a filter/middleware applied once to the shared log setup cannot be forgotten
per-call.

### Redact before you log, not after

Raw request payloads and query parameters routinely carry identifiers, tenant/customer data, or (if a caller ever misuses a literal instead of a parameter) credentials — none of which belongs verbatim
in a log line that may ship to a shared aggregator. Build this in from the start, not as a later hardening pass:

- Log a short fingerprint/hash of normalized request text (e.g. first 8 hex chars of a SHA-256 of the normalized query/payload) instead of the raw text.
- Log only a named, allow-listed set of parameter keys, never an opaque dump of every parameter.
- Expose this as a single `redact_params(params, allow_keys)`-style helper, called from the *same* logging filter/middleware that injects the FCID — so redaction is automatic and structurally cannot
  be forgotten at an individual call site the way a manual masking convention could be.

### Who sets it, per consumer type

State this explicitly per consumer type so no implementing session has to guess:

- A scheduled job generates one FCID per process start (one per cron-triggered invocation).
- An investigation/orchestration script generates one FCID per manual invocation, shared across every step of a multi-step run.
- A CLI tool generates one FCID per invocation.
- An ad hoc one-off script follows the same rule, no exception — a one-off script run is still a "run."

## What to deliberately defer

State explicitly, in the design doc, what this convention does *not* yet solve, so a future session doesn't have to rediscover the boundary:

- **Cross-process propagation.** An ambient context variable is in-process only. If a run shells out to a subprocess or triggers a separate scheduled-job boundary, the FCID does not cross that
  boundary automatically under this design. Flag this as an open question for whichever future story first needs it (e.g. pass it via an environment variable to subprocess children) rather than
  solving it speculatively now.
- **The propagation module itself**, if the design phase precedes any real consumer. Build only the minimal slice an actual first consumer needs (e.g. just `bind_fcid`/`current_fcid` and the log
  filter) rather than the full redaction/formatter wiring, and leave the rest explicitly flagged as unimplemented in that module's own docstring/README until a second consumer needs it.

## Coordination without ownership

Once the convention is designed, every consumer epic/story that will eventually adopt it gets a one-line, dated coordination note in its own planning doc ("this convention exists at `<path>`; this
epic does not implement it itself; this is the coordination record for whoever next touches the adapter code"), rather than the design story reaching into and editing each consumer's own files. This
keeps the design decision visible to every future implementer without creating edit conflicts across unrelated stories' plan docs.
