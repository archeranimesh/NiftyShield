# Full Repo Review — Story specs

> Shipped, superseded epic (2026-07-05 to 2026-07-06) — a multi-persona review of the whole repo across model/protocol/quant/architecture/standards/test/security dimensions, closed out by FR-9's
> synthesis into `full-repo-review-followups/`. Not actively worked; digests only, per `docs/plan/README.md` §Conventions and the DFM-3 tier-B rule. Full findings live in `findings/`, unchanged.

---

### FR-0 — Model validation pilot: Fable vs. Opus (SHA c7e8740)

Ran the same prompt on both Fable and Opus and diffed the outputs to decide whether Fable's cost premium is worth it for this epic's three Fable-assigned tasks; produced a per-task keep/downgrade
recommendation consumed by FR-1, FR-3, and FR-7.

### FR-1 — Prompting methodology & AI-collaboration protocol review (SHA 811ed02)

Protocol Reviewer pass (run on Opus per FR-0's downgrade recommendation) over `CLAUDE.md`, every module `CLAUDE.md`, and the AI-collaboration docs; findings fed FR-8's tooling guide and the epic's own
philosophy-promotion decision.

### FR-2 — Financial modeling & Greeks correctness review (SHA 9390330)

Quant Reviewer pass (Opus) over `src/risk/`, `src/paper/`, `src/strategy/`, `src/backtest/ivr.py`, and `src/models/options.py` against ground truth in `portfolio.sqlite`; surfaced the
`portfolio/tracker.py` reconciliation finding that became the epic's most significant result.

### FR-3 — Architecture & design-doc consistency review (SHA 8a67ffe)

Systems Architect pass (ran on Sonnet, a deviation from FR-0's low-confidence keep-Fable call — no Fable override was available inline) over root/module markdown, `docs/plan/`, and `docs/council/`,
checking cross-document provenance.

### FR-3.1 — Full folder structure & taxonomy review (SHA d205d16)

Folder Structure Auditor pass (Sonnet), depending on FR-3's output, covering the full repo directory tree, VCS-tracking status of `scratch/`/`tmp/`, and archive-folder consistency.

### FR-4 — Code quality & coding-standard compliance sweep (SHA 3242fa8)

Standards Auditor pass (Sonnet) over `src/` and `scripts/` against `REVIEW.md` and `LOGGING.md`; recounted violations fresh rather than trusting the prior spot-check (found 21 bare-logger files vs.
the seed count of 20).

### FR-5 — Test adequacy & ground-truth coverage review (SHA 5e09860)

Test Auditor pass (Sonnet) over `tests/` cross-referenced against `src/`; coverage tooling was only partially runnable in the sandbox, and two findings were tagged `NEEDS-OPUS-REVIEW` and left
unescalated.

### FR-6 — Security & operational-risk review (SHA ed3791b)

Red-Team pass (ran on Sonnet, a deviation from the Opus assignment — no Opus override was available inline) over `BrokerClient` implementations, auth/config, CI, and the Telegram gateway, probing
failure modes under leaked tokens and malformed responses.

### FR-7 — Missing-persona / blind-spot synthesis (SHA d57ee7f)

Chairman pass (Fable, kept per FR-0's explicit low-confidence caveat on this task) merging, deduplicating, and ranking severity across FR-1 through FR-6's findings.

### FR-8 — Tooling usage guide: Claude Code vs. Cowork vs. Antigravity handoff (SHA 308aa57)

Practitioner/DevEx pass (Sonnet) building a job-type routing table for the three surfaces, citing FR-1's protocol findings rather than re-deriving them.

### FR-9 — Implementation roadmap folder + DECISIONS.md update (SHA 149408f)

Mechanical synthesis (Sonnet): independently re-verified all 7 CRITICAL findings from FR-7's summary table against the live repo (none downgraded), then built the `full-repo-review-followups/` epic
with priority tiers P0–P3 and 9 story stubs to carry the findings forward.
