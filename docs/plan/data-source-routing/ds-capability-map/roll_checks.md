# DSM-1 — Roll-critical checks (findings)

> Three checks that gate the Dec 2026 roll. Each is marked **verified** (by probe or file inspection, with the date) or **unverified** (with an owner). No checkboxes. Started 2026-10-11.

## 1. Does the Upstox BOD list Dec 2027 NIFTY contracts? — verified (file inspection), 2026-10-11

Source: `data/instruments/NSE.json.gz`, file mtime 2026-10-04 07:00. The BOD was **not** re-fetched on 2026-10-11, so this says "listed as of 2026-10-04", not "listed today".

| Expiry | CE strikes | PE strikes | Strike range | Step |
|---|---|---|---|---|
| 2026-12-29 | 114 | 116 | 15,000 to 34,500 (CE) / 12,000 to 33,000 (PE) | 50 near the money, 250 / 500 / 1,000 further out |
| 2027-12-28 | 15 | 20 | 15,000 to 33,000 | 500 / 1,000 / 1,500 only |

Dec 2027 is listed, on 2027-12-28, so the council's "Dec 2027 absent from the BOD" case has not occurred and Option A (side-table resolver) stands. Dec 2028 and later Decembers are listed too.

Coverage is thin, and this is a finding for the yearly book, not a failure of the check:

- 35 contracts against 230 for Dec 2026. Strikes between 24,000 and 27,000 are 24,000 / 25,000 / 25,500 / 26,000 / 27,000 (CE) and 24,000 / 25,000 / 25,500 / 26,000 / 27,000 (PE); nothing finer
  than 500.
- The Dec 2027 listing is the same shape as Dec 2026 before it widened: the archived POC (`docs/archive/plan/dhan-data-poc/findings.md`, DDP-5) shows Dec 2026 at 22 strikes in 500 / 1,000 / 1,500
  steps while all-zero, widening to 88 strikes on 2026-09-30 at about DTE 90. By analogy, finer strikes for Dec 2027 would appear around 2027-09-30. That is an inference from one contract, not a
  measured fact.
- Consequence: a Dec 2027 leg chosen at the 2026-12-29 roll can only be one of these coarse strikes. The `strike_selector` delta targeting runs against that sparse set, and the Dhan chain may list
  strikes the BOD does not (the resolver's partial-map case in `ds-chain-seam` DSC-2).

Still open on this check: refresh the BOD and diff against the 2026-10-04 copy (owner Animesh, optional; keep the old copy before it is overwritten).

## 2. Dhan response for a missing / expired token — verified (probe), 2026-10-11

Probe: two sequential POSTs 4 s apart to `https://api.dhan.co/v2/optionchain` (NIFTY, `UnderlyingScrip` 13, `IDX_I`, expiry 2026-12-29) and `/v2/optionchain/expirylist`. In the probe environment
`settings.dhan_access_token` was **empty**, so what was tested is a missing token; the client id was present.

```
HTTP 401, content-type application/json
{"Data":{"809":"Access token is invalid"},"status":"failed"}
```

Both endpoints returned the identical body. Findings:

- Dhan nests the error as `Data: {"<code>": "<message>"}` plus `status: "failed"`. There is **no** top-level `errorCode` / `error_code` key.
- `DhanMarketClient._fetch_with_backoff` (`src/client/dhan_market.py:159`) raises `AuthenticationError` on HTTP 401 / 403 before it parses the body, so this case is handled correctly today.
- Its 805 / 806 branch (`dhan_market.py:166-171`) reads `errorCode`. Its unit test mocks `{"errorCode": "806"}`. If real 805 / 806 bodies use the nested `Data` shape seen here, those branches never
  match. This must be settled before `ds-chain-seam` DSC-3 builds the 805 / 806 / empty / transport taxonomy on it.
- Dhan's JSON key case is **not stable**: the missing-token reply used `Data`, the expired-token reply (below) uses lowercase `data`. Parse case-insensitively.

Second probe, same two calls, with an *expired* token (JWT `exp` 2026-10-10 11:03 IST, about 32 h old; `iat` 24 h earlier) saved in `.env`:

```
HTTP 401, content-type application/json
{"data":{"808":"Authentication Failed - Client ID or Token invalid"},"status":"failed"}
```

Both endpoints again identical. So missing token gives code 809 ("Access token is invalid") and an expired token gives 808 ("Authentication Failed - Client ID or Token invalid"). The 808 message also
covers a wrong client id, so an expired token cannot be told apart from a bad client id by the response alone; the token's own `exp` claim can. DSN-1's staleness alert should read `exp` from the JWT
rather than wait for a 401. Both cases return HTTP 401, which `DhanMarketClient` already maps to `AuthenticationError`. No probe call consumed data-API quota.

## 3. Dhan error 806 ("Data APIs not subscribed") — not verified, no longer needed (plan renewed)

Animesh decided on 2026-10-11 to renew the Dhan data plan for a year (DA-0), so 806 should not occur during the roll window. The only evidence is the POC's secondhand note (`findings.md` line 100,
status U). Handle it as one generic "capability unhealthy, fall back to Upstox" branch with no 806-specific work. If a real 806 is ever seen, record the body here. The parser should still read the
nested `data` / `Data` code key and tolerate a top-level `errorCode`.

## 4. Upstox zero-to-non-zero Greeks flip on a second expiry — deferred, not a roll gate

Evidence today is one contract: Dec 2026 flipped between 2026-09-29 15:55 (DTE 91, all zero, 22 strikes) and 2026-09-30 09:51 (DTE 90, 90 rows with 0 < |delta| < 1, 88 strikes). The chain widening and
the DTE crossing coincide, so the cause cannot be separated. The second expiry in the stored data (2026-09-29) starts only at DTE 85 and cannot test the cutoff from above.

The next testable contract is 2027-06-29: the flip, if the ~90 DTE rule holds, falls on about 2027-03-31. The far-expiry capture store would record it, but `far_expiry_chain_snapshots` does not exist
in the local `portfolio.sqlite` on 2026-10-11, so no capture rows are present on this machine to read.

Roll implication: this cannot be resolved before the Dec 2026 roll. The yearly design must treat Upstox zero Greeks on Dec 2027 as the expected state until about 2027-09-30 and must not depend on the
cutoff being exactly 90 DTE (`ds-chain-monitoring` DSN-5 already requires two consecutive trading days of non-zero delta before flipping back).

## Summary

| Check | Status | Owner of remainder |
|---|---|---|
| Dec 2027 in Upstox BOD | Verified (2026-10-04 file) — listed, thin | Animesh (optional refresh) |
| Missing-token response | Verified — 401, `Data.809` | — |
| Expired-token response | Verified — 401, `data.808`, key case differs | — |
| 806 response | Not verified, not needed (plan renewed 1 year) | — |
| Greeks flip, second expiry | Deferred; revisit about 2027-03-31 | Claude (read capture store then) |
