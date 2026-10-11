# Tradetron backtest studies — epic index

> Cheap Tradetron backtests (₹20 a run) used to settle protection and income questions on the NIFTY overlays before real money or paid data is committed. One epic because every study shares the same
> platform rules, spend gate and fill-level reading method; each study is its own story.

## Why this epic exists

`tradetron-delta-and-long-window/` showed that Tradetron can run a five-year CC, PP or Collar book for ₹20 and that the fills carry the NIFTY price at every entry and exit. Its numbers then raised
design questions that a screen can answer cheaply (how deep a protective put should be, what a covered call really earns net of its losses). Those questions need several runs of one template at
different settings, which is a study, not a verification task, so they get their own home instead of lengthening that story.

## Scope decisions

- Studies measure cost, deductible and realised income per cycle. They do not claim an edge; every figure carries its round-trip or cycle count and a flag under 30.
- The protected unit is one NIFTY lot (65 units, about ₹15 lakh at today's level), the stand-in for a NiftyBees holding of that size. Lot counts for a real portfolio come from Animesh's exposure and
  loss limit, which are inputs, not findings.
- Order of worth is protection first, then income. A study that recommends a short-option leg must show its gap-fill overshoot beside its credit.
- `tradetron-delta-and-long-window/` stays where it is and finishes TDL-9 and TDL-10 there. Whether it moves under this epic is Animesh's call; no pointer to it changes until he decides.

## Architecture and design review

No module, class or seam. If a story produces a reusable analysis CLI, run the SOLID triggers in `docs/refactor/design-principles.md` and the prior-art audit in
`docs/refactor/code-deduplication-and-taxonomy.md` first, and record the outcome in that story's `prompt.md`.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `tradetron-pp-protection-study/` | Cost, deductible and payoff of a hold-to-DTE-5 protective put at three depths, plus the CC rental net of losses | ⬜ Not started | — | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`.

## Cross-cutting constraints

- Spend: no funded run before its free pre-flight says `backtestable` and Animesh has confirmed the spend in that session. Quote `next_run.quote` from `tt_backtest_workbench` verbatim; read finished
  runs for free. Wallet was ₹100 on 2026-10-11.
- Platform rules live in `docs/reference/tradetron.md` (pass the leg instrument id to the pre-flight; trust `tt_wallet_balance` over the submit billing block; the per-trade index ages out in days, so
  save paired data to the story folder at once; large trade pages land in a file, process them with Python).
- No change to `src/` or `scripts/`. A reusable calculation becomes a tested CLI in `scripts/dev/`; one-offs stay in `scratch/` per `SCRATCH.md`.
- Never record credentials, broker tokens or the wallet top-up link.

## Supersession / coordination

Continues `tradetron-delta-and-long-window/` (inputs: its `findings.md`, the PP template 999135746, the CC v2 template 999082574, and the cycle numbers recorded in this epic's first story). Does not
edit that story's files or `greeks-bs-fallback/`.

## Epic done when

- **tradetron-pp-protection-study** — a per-depth table (annual cost, deductible actually realised, share of cycles beyond the deductible, worst cycle) with cycle counts, a stated selection rule, the
  CC rental net of losses, and a sizing note tied to Animesh's exposure and loss limit.
