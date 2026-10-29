# Gamma Scan Phase B — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Blocked until** `../risk-gamma-phase-a/` is complete and ≥ 5 trading days of `gamma_chain_snapshots` exist.

**Open: GS-8.** GS-6 now runs last; see §Sequence.
- [x] **GS-1** — `gamma_signal_log` model, DDL (`DB_REGISTRY.md` entry) and `GammaStore` insert/update methods | Owner: Antigravity | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 7dfd971
- [x] **GS-2** — `src/gamma/signals.py`: Layers 0–4 as predicates returning reason codes in an ordered `SignalStack` | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: 594fedf
- [x] **GS-3** — `DepthSource` Protocol + Dhan L2 adapter + `NullDepth` (reduced mode) | Owner: Antigravity | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 1486e1c
- [x] **GS-4** — `ranking.py` (§6 formula) and `exits.py` (E1/E2/E3) as pure functions | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: b1e9316
- [x] **GS-5** — `scripts/gamma_scan.py` thin orchestration: lock, atomic no-open-position check, paper-entry adapter around `record_paper_trade` | Owner: Claude | Model: claude-sonnet-5 | Review:
  code-reviewer | SHA: 28cec55
- [x] **GS-7** — Correct the expiry-day text: cron is `*/5 9-15 * * 1,2` (Mon DTE 1, Tue DTE 0 since the April 2026 expiry move), not `3,4` / Wed–Thu, in this file, the epic `README.md` and
  `docs/strategies/near_expiry_buy_v1.md` | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: 406f640
- [ ] **GS-8** — Activate the Day-21 calibration: find why `strike_iv_pctile_20d` and `gamma_gearing_pctile_dte` are null on every `gamma_chain_snapshots` row, populate them, and replace the
  placeholder `gearing_threshold` of `5.0` with the per-DTE-bucket p75 (council Stage 3). Data-gated: starts on or after 2026-11-02 | Owner: Claude | Model: claude-sonnet-5-5 | Review: greeks-analyst
  | SHA: —
- [ ] **GS-9** — Council call (planning gate, no code): (a) L0 premium band for weeklies, given L0 survivors are deep OTM (|delta| 0.03–0.07), the opposite of the strategy doc §14 Q1 premise; (b) vol
  source for `theoretical_price` (own-strike IV makes condition A near-vacuous vs a fitted smile); (c) baseline for `volume_zscore_5m` (same-session history vs 20-day intraday history). Output to
  `docs/council/`; update `DECISIONS.md` and the strategy doc before any GS-10..12 code | Owner: Animesh | Model: n/a | Review: none | SHA: —
- [ ] **GS-10** — Apply the GS-9 premium band to `SignalConfig` (`min_premium` / `max_premium`) with boundary tests | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: —
- [ ] **GS-11** — Layer 4 volume input: persist cumulative day volume per scan in `gamma_signal_log` (DDL + `DB_REGISTRY.md`), derive `volume_5m` and `volume_zscore_5m` in `features.py`, remove the
  hardcoded `None` at `scripts/gamma_scan.py` | Owner: Claude | Model: claude-sonnet-5-5 | Review: greeks-analyst | SHA: —
- [ ] **GS-12** — Wire `theoretical_price` (and `model_edge`) into the scan: forward source, GS-9 vol source, Decimal-boundary adapter around the interim `src/nifty_calendar/pricing.py` so CM-9's
  `src/pricing` swap is a one-line repoint; remove the hardcoded `None` | Owner: Claude | Model: claude-sonnet-5-5 | Review: greeks-analyst | SHA: —
- [ ] **GS-6** — Dry-run validation: cron `*/5 9-15 * * 1,2` is already installed (`--dry-run`); once GS-8, GS-10..12 land, review at least two full Mon/Tue expiry sessions in which L2–L4 can fire,
  and log the findings in `TODOS.md` | Owner: Animesh | Model: n/a | Review: none | SHA: —

## Sequence

Work in this order; the numbering of GS-6 is historical, not its position. GS-7 has no dependencies and goes first. GS-8 is blocked on data, not on other tasks, so it can start whenever the date
allows. GS-9 is a planning gate and blocks GS-10, GS-11 and GS-12 (band, volume baseline and vol source are its outputs). GS-10, GS-11 and GS-12 are independent of each other after GS-9. GS-6 needs
GS-8 and GS-10..12 all closed; before that, a dry-run cannot reach a trigger (L2 threshold is a placeholder, L3 has no available condition, L4 fails closed on missing volume), so reviewing it earlier
only re-confirms the plumbing.

## Story done when

- **GS-1** — `gamma_signal_log` created idempotently; insert, exit-field update and watchlist-hit query covered by tests; `DB_REGISTRY.md` updated.
- **GS-2** — every layer predicate has a pass and a fail test; the stack stops at the first failing layer and returns its reason code; Layer 3 Condition B is inert until 20 days of history exist.
- **GS-3** — `DepthSource` has a Dhan adapter and a `NullDepth`; missing key or API failure degrades to reduced mode without raising.
- **GS-4** — ranking formula and E1/E2/E3 exit rules are pure and unit-tested with boundary values.
- **GS-5** — end-to-end test with all collaborators mocked; a second concurrent run exits without trading; a duplicate-direction signal does not open a second position.
- **GS-6** — cron live; two full dry-run sessions reviewed with L2–L4 able to fire; findings logged in `TODOS.md`.
- **GS-7** — no `3,4` / Wednesday–Thursday expiry text remains in the three files.
- **GS-8** — both percentile columns populated on new snapshots; the gearing threshold is read from data, not the `5.0` placeholder; tests cover the null-history and populated paths.
- **GS-9** — council file exists; `DECISIONS.md` and the strategy doc reflect Stage 3 for all three questions.
- **GS-10** — `SignalConfig` premium defaults match the council band; boundary tests at both ends.
- **GS-11** — `volume_5m` and `volume_zscore_5m` are non-null on scans after the baseline warm-up; L4 no longer fails closed on a fresh session; offline tests for warm-up and normal paths.
- **GS-12** — `theoretical_price` and `model_edge` are populated where inputs exist, `None` where they don't; no import of `src.nifty_calendar` outside the adapter module.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list (and the epic row in `docs/plan/README.md`) and add one line to
`TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
