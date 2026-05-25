# Prompt for Sonnet — CSP v1 Strategy + Backtest Plan Revision

> Copy everything below the line into a fresh Sonnet session in this repo. The prompt is self-contained.

---

## Context — repo protocol (mandatory before any edits)

You are working in the NiftyShield repo. Follow `CLAUDE.md` step-by-step:

1. Read `CONTEXT.md` first. State `CONTEXT.md ✓` in your first response.
2. Use `codebase-memory-mcp` (`search_graph`, `get_code_snippet`, `trace_path`) before `Read` on `src/` or `scripts/`. For this task you are editing markdown only — `Read` is permitted on `.md` files.
3. State the plan in one sentence + files touched + commits. Wait for go-ahead if more than 2 files change in a single phase.
4. No code changes are expected in this task. If you find that a code change is required as a side-effect, stop and surface — do not silently extend scope.
5. Phase boundary = one commit. Two separate phases here (strategy doc, then backtest plan) = two separate commits. Do not bundle.

## Your job

Update two existing documents to reflect a strategy-design review completed on 2026-04-25. The review changed the underlying instrument and revised several rules. Files to modify:

- `docs/strategies/csp_niftybees_v1.md` — rename to `docs/strategies/csp_nifty_v1.md` (use `git mv`), update content
- `BACKTEST_PLAN.md` — update Phase 0 and Phase 1 task descriptions to match

Do NOT touch any source files in `src/`. Do NOT change `CONTEXT.md` or `DECISIONS.md` content beyond a single one-line entry in `DECISIONS.md` recording the underlying-switch rationale (see "Decisions to record" below).

---

## Decision 1 — Switch underlying option from NiftyBees to Nifty 50 index

**Why:** NiftyBees options are thin (open interest typically <1000 on monthlies, wide bid/ask). NiftyBees ETF tracking error vs Nifty 50 is 0.02% annually — the index is a near-perfect proxy. Use Nifty index options for liquidity; keep NiftyBees as collateral (already pledged).

**Concrete changes throughout the strategy doc:**

- Title: "Cash-Secured Put — Nifty 50 v1" (replaces "Cash-Secured Put — NiftyBees ETF v1")
- Underlying instrument: `NSE_INDEX|Nifty 50` (Upstox key) / `13` segment `IDX_I` (Dhan)
- Collateral remains `NSE_EQ|INF204KB14I2` (NiftyBees) — already pledged. State this distinction explicitly: option leg is on Nifty index, collateral is NiftyBees ETF.
- Lot size: **65** (effective Jan 2026; was 75 in 2024, was 50 before that). Document the lot-size revision history briefly so the figure is not mistaken for a typo.
- Expiry day: **last Tuesday** of each calendar month (changed from last Thursday in 2025). This affects all calendar arithmetic in the spec — re-check entry-window text.
- Notional capital deployed: strike × 65. At 25-delta strike near 23,000 (current Nifty spot 23,897 as of 2026-04-25), notional ≈ ₹14,95,000 per lot.
- Update the "Expected P&L Distribution Prior" table — figures in the existing doc are sized for NiftyBees lot 35 at ₹225-strike. Re-derive against Nifty lot 65 at ~23,000-strike. Indicative ranges:
  - Average winning month: ₹6,000–9,000 per lot net (was ₹180–240)
  - Average losing month: ₹10,000–15,000 per lot net (was ₹280–380)
  - Worst single month at 2× loss-stop: −₹13,000 to −₹17,000 per lot net (was −₹400)
  - Win rate range and Sharpe range can stay (regime-dependent, not size-dependent)

**Margin / collateral note to add:** Operator's actual collateral pool is ~₹1.2 cr (₹75L MF + ₹30L bonds + ₹15.5L NiftyBees). Cash-component requirement is met from existing pledge mix. The "cash-secured" framing is accurate at the *portfolio* level even though the option is on Nifty (not NiftyBees). Document this so future reviewers do not re-flag the correlated-collateral concern that was already addressed.

---

## Decision 2 — Rule revisions agreed in 2026-04-25 review

Each item below is `current rule → new rule → rationale`. Apply to the strategy doc; ensure the backtest plan reflects the change wherever the rule is referenced (notably 1.7 CSP code spec, 1.8 backtest run, 2.1 continuous re-validation).

**R1 (time stop — clarification, NOT a change):** The existing wording "close on or before 21 DTE" was ambiguous. Operator's intent is **"hold for 21 calendar days from entry, then exit if no other trigger has fired."** Re-write the time stop in those exact words. Add a worked example: entry at 27 DTE → exit at 6 DTE remaining; entry at 34 DTE → exit at 13 DTE remaining. Note that this means the position is held into peak-theta zone but also into elevated gamma — this is intentional given the review concluded that 21-day theta capture is the strategy's edge.

**R2 (loss stop — change):** `Close immediately if the current option mark-to-market value reaches 2× the entry credit` → `Close immediately if put delta crosses −0.45 OR mark reaches 1.75× entry credit, whichever first`. Rationale: 2× rule fires after delta is already ~−0.50 to −0.65 (peak gamma); delta gate fires earlier and at lower gamma, producing better fills.

**R3 (IVR filter — new rule, was missing):** Skip cycle if India VIX < 12 OR IVR < 25 (trailing 252-day percentile of India VIX). Rationale: short premium when premium is already at the floor has near-zero positive expectancy after costs and unbounded vol-expansion risk.

**R4 (event filter — new rule, was missing):** Skip cycle if any of the following falls inside the trade DTE window: Union Budget (Feb 1 ± 1 trading day), RBI MPC announcement day, election-result day. Reason for inclusion: Indian-market specific tail-event premium is not adequately priced into 25-delta. Operationalize via a YAML calendar at `src/market_calendar/events.yaml` (file does not yet exist; reference its planned creation in `BACKTEST_PLAN.md` task 3.3 — that task already covers it).

**R5 (re-entry — change):** `After any exit, the next entry is strictly the Wednesday after the next monthly expiry. No early re-entries within the same expiry cycle.` → `After early profit-target exit (50% target hit before time stop), if DTE to current expiry is ≥ 14 AND IVR ≥ 25, re-enter at the new 25-delta strike of the same expiry. Otherwise wait for the standard Wed-after-next-expiry entry.` Rationale: reduces idle-capital drag without abandoning v1 simplicity. The IVR floor is the same as R3 so the discipline is consistent.

**R6 (kill criteria — additive):** Add to existing kill criteria: `Any single cycle loss > 3× trailing-12-cycle average credit pauses the strategy automatically pending review.` This is a per-cycle early warning to complement the trailing-6-month criterion that fires too late.

**R7 (slippage model — refinement):** Current spec uses ₹0.25/unit flat. Update to: `slippage = max(₹0.25, 0.5 × bid-ask spread) at entry and profit-target exit; 1.5× this figure at loss-stop exits (stressed market exit conditions).` On Nifty index options the spread is tighter than NiftyBees options (typically ₹0.50–1.50 normal, ₹2–5 stressed) so the multiplier on stop-loss exits matters more than the base.

**Confirmed unchanged:**
- Entry day rule (Wed after expiry, 10:00–10:30 IST)
- 25-delta target strike
- 50% profit target
- 1 lot for paper phase and first 3 months of live
- 25% portfolio cap

---

## Decision 3 — Backtest plan changes

Apply to `BACKTEST_PLAN.md`:

**1.7 (CSP strategy code):** Reword task to reference `csp_nifty_v1.md` (not `csp_niftybees_v1.md`). Add a sub-task: implement R5 re-entry logic as an explicit branch in `on_day` so it can be toggled off via config for the variant comparison below.

**1.8 (CSP backtest run):** Replace the single backtest run with **three runs** producing comparable metrics:
- V1 — current spec (Wed-after-expiry only, no early re-entry)
- V2 — R5 re-entry (re-enter after early profit exit if DTE ≥ 14 and IVR ≥ 25)
- V3 — always-on roll (re-enter immediately after any exit if DTE ≥ 14, no IVR gate)

Document both annualized return and Sharpe for each variant. The decision V1-vs-V2-vs-V3 is the operator's; the backtest provides the comparison data, not the verdict.

**1.11 (variance check):** No methodology change, but the bias-adjustment paragraph must reference the *active* variant (V1, V2, or V3) selected for paper trading. Whichever variant the operator picks after 1.8 is the one paper-traded in 0.6.

**Phase 0.6 (paper trading start):** Push the minimum paper-trade duration to **6 cycles minimum** (~6 months), with at least one cycle that triggers each of: profit target, time stop, delta-stop. The current "8 weeks / 2 cycles" is statistically too thin. Re-word the rationale paragraph accordingly.

**Phase 1.1 (Dhan data subscription):** No change required — Dhan expired-options endpoint is sufficient for the indicative backtest. Add a one-line caveat: *"Dhan expired-options data does not include bid/ask spread history; the backtest fills at OHLC midpoint and applies the R7 slippage model. Realistic spread calibration happens in paper phase."*

---

## Open questions you must surface (do not guess)

Do not commit changes that depend on unresolved answers below. Either propose a concrete resolution and ask for sign-off, or stop and surface.

1. **Filename and git history:** is `git mv csp_niftybees_v1.md csp_nifty_v1.md` acceptable, or does the operator want both files to exist (old marked DEPRECATED, new with full content)?
2. **R3 IVR computation source:** India VIX history is needed for the IVR filter. Is this data already in the repo (search `src/` for VIX references first), or does it need a separate ingestion task added to Phase 1?
3. **R4 event filter calendar:** the YAML at `src/market_calendar/events.yaml` does not exist yet. Is its creation in scope for this task, or strictly a Phase 3.3 dependency? If Phase 3.3 only, document R4 as "specified, not yet enforced" in the strategy doc until 3.3 lands.
4. **Existing "Expected P&L Distribution Prior" priors:** the new figures I gave are indicative based on rough vol assumptions. Operator should provide refined priors before commit, or accept the placeholder with a note that they will be re-derived from V1 backtest output.

## Decisions to record in DECISIONS.md

Add one entry under the appropriate heading (likely "Strategy Selection" or "Architecture Decisions"):

> **2026-04-25 — CSP v1 underlying switched from NiftyBees options to Nifty 50 index options.** Rationale: NiftyBees options have insufficient liquidity (OI <1000, spreads >5% of mid). NiftyBees ETF tracking error vs Nifty is 0.02% annually, making Nifty index options a near-perfect proxy. NiftyBees holding remains as pledged collateral; the option leg is on Nifty. Reviewed 2026-04-25 with strategy-stress-test pass; no margin concern given the ₹1.2cr+ collateral pool (MF + bonds + ETFs).

## Done when

- `docs/strategies/csp_nifty_v1.md` exists with all changes above; old filename renamed via `git mv`
- `BACKTEST_PLAN.md` reflects 1.7/1.8/1.11/0.6/1.1 changes
- `DECISIONS.md` has the one-line entry
- `TODOS.md` has a session log line for 2026-04-25 noting the rename and the rule revisions
- Strategy spec validator (`scripts/validate_strategy_spec.py` if it exists, else manual section check) confirms all required sections still present in the renamed doc
- Two commits, in order:
  1. `docs(strategies): switch CSP v1 to Nifty index + revise rules per 2026-04-25 review`
  2. `docs(plan): update Phase 0/1 to reflect CSP v1 underlying + variant backtests`
- Each commit follows the project format with `Why:` / `What:` / `Ref:` lines as per `CLAUDE.md` Step 5

## What NOT to do

- Do not write any new Python code in this task — strategy doc + plan doc edits only
- Do not modify the existing `csp_niftybees_v1.md` priors numerically based on your own estimation if the operator is online to provide them; surface a question first
- Do not bundle the two commits into one
- Do not edit `CONTEXT.md` beyond what is strictly required (this task does not change module structure)
- Do not delete the "Open Questions for v2" section in the strategy doc — preserve it; only update entries that are now stale (e.g., the question about NiftyBees liquidity is now answered by the underlying switch — mark resolved with date)
