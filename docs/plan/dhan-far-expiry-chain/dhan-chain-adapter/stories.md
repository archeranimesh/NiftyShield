# Dhan Chain Adapter — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` + tick the box,
> update story status, add one line to `TODOS.md`.

---

## DA-0 — Renewal decision (Animesh)

**Files:** `docs/plan/dhan-far-expiry-chain/dhan-chain-adapter/findings.md` (reference file, no checkboxes). **Write:** renew or cancel, the date decided, and the reason. Recommendation: keep through
at least the Dec 2026 roll. **Tests:** none. **Commit:** `docs(plan): record Dhan data-plan renewal decision`

---

## DA-1 — Fixtures and the Upstox Dec 2026 check

**Files to change / create:**
- `tests/fixtures/dhan_chain/dec2026.json`, `dec2027.json` — recorded live responses, trimmed to a few dozen strikes around the target deltas, with ids or tokens removed.
- `docs/plan/dhan-far-expiry-chain/dhan-chain-adapter/findings.md` — Upstox Dec 2026 result.

**Before any code:** read both probes for the request shape; `src/auth/dhan_login.py` for how the token is obtained. Run the recording through `scratch/` per `SCRATCH.md`, read-only, honouring 4 s
spacing.

**What to implement:** record, sanitise (strip any client id or token field), commit; run the Upstox Dec 2026 chain once and note whether any delta is non-zero and the DTE.

**Tests:** `test_dhan_fixtures_contain_no_credentials` — scan fixtures for token-shaped fields.

**Commit:** `test(dhan): add sanitised far-expiry chain fixtures`

---

## DA-2 — Client and parser

**Files to change / create:** `src/client/dhan_market.py`, `tests/unit/client/test_dhan_market.py`. New directory? none expected; if one is added it needs `__init__.py` and a graph re-index.

**Before any code:** `get_code_snippet("OptionChain")`, `get_code_snippet("OptionLeg")`, `get_code_snippet("parse_upstox_option_chain")`; `search_graph("DhanAuthError")`-style existing exceptions in
`src/client/exceptions.py`.

**What to implement:**

1. `parse_dhan_option_chain(data) -> OptionChain`, pure, `Decimal` for every price and Greek.
2. `DhanMarketClient` async, constructor-injected HTTP session, rate limiter and clock; at least 4 s between unique requests; error 805 backs off and surfaces a typed error after bounded attempts;
   explicit timeout on every call.
3. Error 806 (not subscribed) and auth failure raise loudly.

**Tests:**
- `test_parse_dec2027_fixture_has_nonzero_deltas`, `test_parse_empty_chain_returns_empty_not_error`.
- `test_requests_spaced_by_rate_limiter` (fake clock), `test_805_backs_off_then_raises`, `test_806_raises_not_subscribed`, `test_timeout_raises`.

**Commit:** `feat(client): add Dhan option-chain client`

---

## DA-3 — Chain-source selection

**Files to change / create:** `src/client/chain_source.py` (Protocol + composite), `tests/unit/client/test_chain_source.py`; wire into the chain fetch used by the overlay bootstraps only after the
unit tests pass — name those files before editing.

**Before any code:** `trace_path` the chain fetch used by `auto_cc_bootstrap`; `get_code_snippet("UpstoxMarketClient")` chain method; `src/client/protocol.py`.

**What to implement:**

1. `ChainSource` Protocol with one method returning `OptionChain` for `(underlying, expiry)`.
2. Composite tries Upstox first; if every delta in the result is zero, asks Dhan; if Dhan also fails, raises (never returns a silent all-zero chain as if valid).
3. The decision and the source used are logged.

**Tests:** `test_upstox_greeks_present_dhan_not_called`, `test_upstox_all_zero_falls_back_to_dhan`, `test_both_fail_raises`, `test_partial_zero_is_not_fallback_trigger`.

**Commit:** `feat(client): add chain-source fallback to Dhan on zero Greeks`
