# Council — data-source-routing

Council question for the Step 2b checkpoint. It gates `ds-chain-seam/` and `ds-chain-monitoring/`; no code in those stories starts until it is absorbed (task DSM-3).

Drafted from `docs/council/_TEMPLATE/` on 2026-10-07. The template's `tmp/q<N>` layout was not used: `tmp/` is gitignored, so this question lives with the epic it gates.

| File | Role |
|---|---|
| `question.md` | The question, system context, options, Q1-Q5, required output format |
| `submit.sh` | Wrapper around `scripts.council.ask_council` (`--template data_architecture`) |

## Run (task DSM-2, owner Animesh)

```bash
# terminal 1
cd tools/llm-council && ./start.sh
# terminal 2, from anywhere in the repo
bash docs/plan/data-source-routing/council/submit.sh
```

Optional: add `--dry-run` to the `ask_council` call in `submit.sh` first to preview the assembled prompt.

## Absorb (task DSM-3)

1. Read `docs/archive/council/data_architecture/2026-10-07_data-source-routing.md` — Stage 3 Chairman Synthesis first, via `protocol-reference` §1.
2. Add a row per Summary Table decision to `DECISIONS.md`; log Dissenting Notes under "Noted, deferred".
3. Add a row to `docs/council/README.md` §"Topics Already Covered" (`data-source-routing`, status `archived` once absorbed).
4. Spec `ds-chain-seam/stories.md` and `ds-chain-monitoring/stories.md` from the Summary Table, then amend this epic's README open decisions.
5. Do not start any `DSC-*` or `DSN-*` task before steps 2-4 are done.

## Adjacent ruling

`docs/council/2026-07-02_paper-delta-source-architecture.md` (active, not yet absorbed into `DECISIONS.md`) already fixed the caller-resolves-delta-map boundary and the paper-phase fallback. This
question extends it for a far-dated book (Q4) and does not reopen it.
