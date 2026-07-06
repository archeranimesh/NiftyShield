# FR-6 — Security & Operational-Risk Review

**Persona:** Red-Team Reviewer
**Scope attached:** `src/client/` (all 4 `BrokerClient` implementations + `exceptions.py` +
`factory.py`), `src/auth/`, `src/config.py`, `.env.example`, `.pre-commit-config.yaml`,
`.github/workflows/ci.yml`, `src/notifications/telegram_gateway.py`, `src/db.py`, directory
listing of `data/portfolio/`, backup-referencing scripts.

Assumption throughout: leaked token, malformed API response, network partition mid-order,
config error in prod vs. sandbox. Where does the system fail unsafely instead of loudly?

---

## Seed issue verdicts

**1. `.env` not tracked, `detect-secrets` active.** CONFIRMED clean.
`git ls-files | grep -i '\.env'` returns nothing. `.gitignore` line 1 is `.env*` (broader
than just `.env`, also catches `.env.local` etc — good). `.secrets.baseline` exists
(3.4 KB) and `.git/hooks/pre-commit` exists and is executable (mode `-rwx------`,
installed May 29), so `detect-secrets` is wired into an actual git hook, not just declared
in `.pre-commit-config.yaml` with nobody having run `pre-commit install`. No finding.

**2. `factory.py` sole composition root.** CONFIRMED, with one nuance worth naming precisely.
Grep for `UpstoxLiveClient`/`MockBrokerClient` outside `factory.py`/tests turns up only
docstring/comment mentions (`protocol.py`, `paper/tracker.py`, `portfolio/tracker.py`) — no
second import site. Every `create_client(...)` call site in `scripts/` passes
`settings.upstox_env` or an explicitly threaded `env` var, never a hardcoded `"prod"`. Rule
holds. INFO, not a finding: `factory.py`'s `"sandbox"` branch still instantiates
`UpstoxLiveClient` (not `MockBrokerClient`) — sandbox is a real network path with a
different token, not an offline mode. That's correct per the docstring's own definition,
but it means "sandbox" gives false comfort if anyone reads the three-way enum and assumes
only `"test"` and `"prod"` touch the network.

**3. Retryable/terminal exception split.** PARTIALLY MOOT — see Finding S-1 below. There is
no retry *loop* anywhere in the codebase today (no `tenacity`, no `backoff`, no hand-rolled
`for attempt in range(...)` around a `RateLimitError`/`DataFetchError` catch). Every
catch site re-raises, logs, or returns an empty/None sentinel once. So the specific bug
class asked about ("a retry loop that retries a terminal exception, causing duplicate
order submission") cannot exist yet, because retry itself doesn't exist yet. That is
its own finding, not a clean bill of health — see S-1.

**4. Telegram chat-ID allowlist checked on every inbound path.** CONFIRMED single choke
point (`_handle_callback`, called only from `start_polling`'s update loop) — but the guard
logic itself has a real gap. See Finding S-2.

**5. CI can't accidentally hit live Upstox regardless of misconfiguration.** CONFIRMED,
and better than "the env var happens to be set" — there's genuine defense in depth. See
Finding S-3 for why this one actually clears the bar Animesh set in the prompt.

**6. `portfolio.sqlite` backup/durability.** CONFIRMED ABSENT. This is the highest-severity
finding in this review. See S-4.

---

## Findings

### S-1 (WARNING) — Retryable/terminal exception hierarchy is aspirational, not enforced

`src/client/exceptions.py`'s docstring hierarchy explicitly labels `RateLimitError` and
`DataFetchError` "(retryable)" and `OrderRejectedError`/`InstrumentNotFoundError`
"(terminal)". Grepping every raise/catch site of these four exceptions across `src/` and
`scripts/` shows the "retryable" label is not backed by any retry mechanism — every catch
site (`upstox_market.py`, `vix_ingest.py`, `strategy/monitor.py`, the `scripts/pipeline/*`
crons) does exactly one of: re-raise as a different exception type, log-and-continue to the
next item in a loop, or propagate up to the cron's top-level handler and exit. There is no
code path today where a `RateLimitError` triggers a second attempt at the same call.

This means the seed concern (a retry loop retrying a terminal exception → duplicate order
submission) is currently *impossible*, but only because retry logic doesn't exist, not
because the system correctly distinguishes retryable from terminal. The distinction is pure
documentation right now. `MISSION.md` Principle I doesn't care about retry today because
`place_order`/`modify_order`/`cancel_order` are all hard-blocked by
`_raise_order_blocked()` (static-IP constraint) — there is no live order path to duplicate
against. But the retryable/terminal docstring split will become load-bearing the moment
order execution is unblocked, and whoever adds retry logic then needs to know this
distinction was never exercised, let alone tested. **Recommendation:** either add one
`tests/unit/client/test_exception_retry_contract.py` asserting
`issubclass(RateLimitError, BrokerError)` and that no current catch site swallows
`OrderRejectedError` into a loop (a cheap "doesn't regress" test), or add a one-line
`DECISIONS.md`/`TODOS.md` note that retry semantics are unimplemented and must be
designed *before* the static-IP constraint is lifted — not discovered in production the
day order execution goes live. Grounding Test: this doesn't cost capital today, but it is
exactly the kind of gap that costs capital the day a constraint (static IP) is removed and
nobody remembers to revisit the exception contract that was written for that day.

### S-2 (ERROR) — Telegram callback auth guard uses OR instead of AND

`telegram_gateway.py::_handle_callback`:

```python
if sender_id != self._chat_id and chat_id_from_msg != self._chat_id:
    logger.warning(...)
    return
```

This only *drops* a callback when **both** the sender ID and the message's chat ID differ
from the configured `chat_id`. Equivalently, it **allows** the callback through if
*either* one matches — it should require both to match (or, more precisely, should check
the field that actually identifies who pressed the button: `sender_id`, exclusively).

In the current single-user private-DM deployment model (`.env.example`: "message the bot,
then hit getUpdates and read result[0].message.chat.id") `sender_id` and
`chat_id_from_msg` are always numerically identical for the legitimate user, so this bug is
currently unreachable — Animesh's own callbacks always satisfy both sides of the AND that
should be there. But the check as written is not defense-in-depth, it's a coincidence of
deployment topology. The moment this bot is ever added to a group chat (even
transiently, e.g. Animesh adds a second device or a shared "ops" group for visibility),
`chat_id_from_msg` becomes the *group's* ID, shared by every member, while `sender_id`
varies per member. Under the current OR logic, **any member of that group could press
"CLOSE_FULL" or "Reject All" on a real trading approval** and the guard would let it
through, because `chat_id_from_msg == self._chat_id` alone satisfies the condition.

Grounding Test: this directly threatens Principle I (capital protection) the moment the
topology assumption (strictly 1:1 DM) is violated, and nothing in the code or docs
enforces that assumption — it lives only in the deployer's head. **Fix:** change the guard
to check `sender_id != self._chat_id` alone (the identity of the button-presser is what
matters, not which chat the message lives in), or if group-chat use is intentionally
supported, require an explicit allowlist of sender IDs distinct from the notification
`chat_id`. Either way, the current line should read as an AND of "sender is authorized"
and "nothing else," not an OR that a topology change silently defeats.

### S-3 (INFO — noted as a positive, not a gap) — CI/prod boundary has real defense in depth

This is worth stating explicitly because the prompt asked for defense-in-depth, not just
"the env var is set correctly," and the codebase actually clears that bar:

- `Settings.upstox_env` (`src/config.py`) defaults to `"test"` with a `pattern` validator
  restricting it to `prod|sandbox|test` — so a missing/blank `UPSTOX_ENV` in any
  environment (CI misconfiguration, a forgotten `.env`, a new dev machine) fails safe into
  `MockBrokerClient`, not into `UpstoxLiveClient`.
- Every `create_client()` call site in `scripts/` reads `settings.upstox_env` (or an
  explicitly threaded value derived from it) rather than hardcoding `"prod"`.
- `MockBrokerClient` has zero network-capable imports (no `aiohttp`, `requests`, or `http`
  usage anywhere in `mock_client.py`) — it is structurally incapable of reaching a live
  endpoint regardless of what fixtures or config it's handed. A malformed
  `fixtures_dir` just produces a WARNING and an empty in-memory state, per the module's own
  documented design principle ("Fixture loading is graceful").
- Order execution (`place_order`/`modify_order`/`cancel_order`) on `UpstoxLiveClient` is
  centralized through a single `_raise_order_blocked()` helper that unconditionally raises
  `NotImplementedError`. There is exactly one place to check and one place that would need
  to change for this to become live — this is good architecture for the specific failure
  mode asked about in seed issue #4 (a future refactor accidentally turning a blocked
  method into a silent no-op): a no-op would require *removing* an explicit raise, which
  is a visible, reviewable diff, not a silently-introduced regression via exception
  handling changes elsewhere. This is meaningfully safer than, e.g., wrapping the blocked
  logic in a `try/except: pass`.

No action needed. Flagging so FR-9's synthesis doesn't miss that this area was checked
and is sound, not just unexamined.

### S-4 (CRITICAL) — No backup mechanism exists for `data/portfolio/portfolio.sqlite`

Grep across `scripts/` and `src/` for `backup`, `.backup(`, `shutil.copy` returns zero
matches. Directory listing of `data/portfolio/` shows exactly one live database file
(`portfolio.sqlite`, 6.4 MB, last modified today) and ~120 stale `.fuse_hidden*` temp files
(FUSE filesystem artifacts from a mounted drive, unrelated to backup — but their volume is
itself a small operational-hygiene smell worth a separate INFO cleanup ticket, not a
security finding).

This single SQLite file is, per `CONTEXT.md`, the store of record for `paper_trades`,
`paper_nav_snapshots`, `paper_leg_snapshots`, `pending_approvals`, `council_outputs`,
`daemon_heartbeat`, `paper_exit_events`, `gate_violations`, and (per the module tree)
live portfolio positions and MF holdings. `src/db.py::connect()` opens it in WAL mode with
no `PRAGMA busy_timeout` set — a secondary, lower-severity note: concurrent cron writers
(multiple `scripts/` crons run on overlapping schedules per `CONTEXT.md`'s cron list) can
hit `database is locked` under WAL without a busy timeout, though WAL's default reader
concurrency mitigates the common case.

The durability gap is the real finding. A single disk failure, a bad `git`/`rsync`
operation, an accidental `rm`, or filesystem corruption on the mount this file lives on
(notable given the FUSE-mount artifacts already visible in the same directory — FUSE
mounts are exactly the kind of layer where partial writes and unexpected disconnects
happen) destroys the entire trade history, every paper-trading P&L snapshot, every
pending approval audit trail, and the delta-tracking state the risk module depends on —
with no recovery path. Per `MISSION.md`'s Grounding Test, this is squarely a Principle I
(Protect Before You Earn) violation even though it's operational rather than
trading-logic: the mission's own text says "if a trade cannot define its maximum loss
before entry, it does not exist" — the symmetric operational version is "if the system
cannot reconstruct what it already did, its risk state is unknowable after a failure,"
which is just as capital-relevant as an undefined max loss, because a recovered process
with no memory of open positions can double-enter or fail to detect an already-breached
delta cap.

**Recommendation (concrete minimum):** a daily cron using SQLite's own `.backup` API
(`sqlite3 data/portfolio/portfolio.sqlite ".backup data/portfolio/backups/portfolio-$(date +%F).sqlite"`)
to a separate directory (ideally a separate physical/logical drive or, better, synced
off-machine), with a retention policy (e.g. keep 30 daily + 12 monthly). This is a
5-line addition to the existing cron surface (`scripts/daemon/` or `scripts/portfolio/`
already host comparable daily crons like `daily_snapshot.py`) and costs nothing to test
offline. `sqlite3 .backup` is safe to run against a live WAL-mode DB without locking out
writers, unlike a raw file copy. A raw `cp`/`shutil.copy` against a WAL-mode DB while a
writer holds the WAL file open risks copying a torn/inconsistent snapshot — worth calling
out explicitly since "backup" and "file copy" are not interchangeable here.

### S-5 (WARNING) — OAuth token persistence has no file-permission hardening, and the local OAuth callback has no CSRF `state` parameter

`src/auth/login.py::save_token` opens `.env` with `open(".env", "w")`, relying entirely on
the process umask for resulting file permissions — there is no explicit `os.chmod(path,
0o600)` anywhere in the three auth-flow modules (`login.py`, `nuvama_login.py` uses
`dotenv.set_key`, `dhan_login.py` uses `dotenv.set_key`). None of the three chmod the file
after writing. On a default `umask 022` this produces a world-readable `.env` containing
live Upstox/Nuvama/Dhan tokens on whatever machine runs the login flow. This doesn't
conflict with "never commit secrets" (git-tracking and filesystem permissions are
orthogonal controls) but it is a gap in the same principle — a secret that's safe from git
history but readable by any other local user account isn't actually protected.

Separately, `capture_auth_code()`'s `AUTH_URL` construction has no `state` parameter, so
the local callback server (`localhost:8000`) accepts and processes any `code` query
parameter presented to it with no correlation back to a request the script itself
initiated. In a single-operator, run-once-interactively CLI script this is low-severity
in practice (the attack requires getting a code delivered to the operator's own
`localhost:8000` in the ~seconds the listener is up), but it's a textbook OAuth
best-practice gap and costs one line (`secrets.token_urlsafe()` generated before opening
the browser, checked against the callback's `state` param) to close. Also note:
`main()` prints `token[:20]` and `auth_code[:10]` to stdout — low risk (truncated, local
terminal), but worth avoiding on principle since shell history/session recording tools
sometimes capture stdout.

**Recommendation:** add `os.chmod(path, 0o600)` immediately after each of the three
token-writing calls (`login.py::save_token`, and confirm `nuvama_login.py`/
`dhan_login.py`'s `set_key` calls receive the same treatment — `python-dotenv`'s
`set_key` does not chmod on its own), and add a `state` param round-trip to
`login.py`'s OAuth flow. Both are small, mechanical, non-load-bearing changes — good
candidates for a follow-up story rather than blocking anything in this review.

### S-6 (INFO) — Async/blocking-call architecture violation in `UpstoxMarketClient`

`CLAUDE.md`'s Async Model section is explicit: "`asyncio` + `aiohttp` for all I/O-bound
operations. Never mix asyncio with blocking calls in the hot path." `src/client/
upstox_market.py` uses the synchronous `requests` library for every HTTP call
(`_fetch_ltp_batch`, `get_ohlc_sync`, `get_option_chain_sync`), and the `async def
get_ltp`/`get_option_chain` wrapper methods that satisfy the `BrokerClient`/
`MarketDataProvider` protocol call these synchronous methods via
`asyncio.to_thread(...)`. This isn't a security hole — `to_thread` correctly keeps the
blocking call off the event loop thread, so nothing deadlocks — but it's a direct
contradiction of the documented standard (`aiohttp` required, not `requests`+
`to_thread`), and it means every market-data call consumes a thread from Python's default
`ThreadPoolExecutor` (default size `min(32, cpu_count+4)`), which is a soft capacity limit
worth knowing about before scaling concurrent chain-fetch fan-out (e.g. the four IC
variants' EOD snapshot crons calling this concurrently). Not urgent, but exactly the kind
of drift `LOGGING.md`'s own origin story (`BUG-010`) warns about — a documented standard
quietly diverging from what's actually implemented, discovered only when someone reads
the code instead of the doc. Recommend a `DECISIONS.md` entry either accepting `requests`+
`to_thread` as the actual standard for sync SDK wrappers, or a follow-up story to migrate
`upstox_market.py` to `aiohttp` for consistency.

---

## Severity summary

| ID | Severity | Area | One-line |
|----|----------|------|----------|
| S-4 | CRITICAL | Data durability | No backup mechanism for the single live SQLite DB |
| S-2 | ERROR | Telegram auth | Callback guard is OR, not AND — topology-dependent, currently masked |
| S-5 | WARNING | Auth/secrets | `.env`/token files not chmod'd 600; OAuth callback has no CSRF `state` |
| S-1 | WARNING | Exception contract | Retryable/terminal split is undocumented-as-untested, not yet exercised |
| S-6 | INFO | Architecture drift | `requests`+`to_thread` instead of `aiohttp`, contradicts `CLAUDE.md` |
| S-3 | INFO (positive) | CI/env boundary | Fail-safe default (`test`) + single order-block chokepoint — no gap found |

Items #1, #2, #5 from the seed list closed clean with no finding; #3 reframed as S-1
(the mechanism the seed question worried about doesn't exist yet, which is its own,
lower-urgency finding); #4 is S-2; #6 is S-4.

---

**Persona reviewed as:** Red-Team Reviewer.

**Perspective this review did not cover:** an Options-Strategist/Financial-Risk persona
would look at whether the *absence* of retry logic (S-1) itself creates capital risk in
the opposite direction — e.g., a transient `DataFetchError` during a delta-check causing a
cron to silently skip an entry/exit gate for a day, versus the duplicate-order risk this
review was scoped to look for. This review only checked "does retry create double-submit
risk" (no, because retry doesn't exist) — it did not check "does the *absence* of retry
create missed-risk-control risk" on the other side of that same design gap. That's a
distinct, financial-logic question this persona isn't equipped to weight against
`MISSION.md` Principle I as precisely as `greeks-analyst` or `options-strategist` would.
