<!-- This file is guidance for whoever drafts a new council question. It is not copied. -->

# `docs/council/_TEMPLATE/` — how to draft a new council question

Only start here after the Step 2b council checkpoint (`CLAUDE.md` §Step 2b) confirms the
three trigger conditions hold. See `docs/council/README.md` §"When to Trigger the Council"
for the full test and the do-NOT-trigger list.

```
cp docs/council/_TEMPLATE/question.md tmp/q<N>_<topic-slug>.md
cp docs/council/_TEMPLATE/submit.sh    tmp/q<N>.sh
chmod +x tmp/q<N>.sh
```

`<N>` is the next unused question number in `tmp/` (check `tmp/README.md`'s Question Index).
`<topic-slug>` is kebab-case and matches the `--topic` value used in `submit.sh`.

Fill in `question.md` first — system context, the decision, the options, the numbered
sub-questions, and the required output format. Then fill in `submit.sh`'s `--topic`,
`--template`, and `--context` flags to match. Add the new question as a row in
`tmp/README.md`'s Question Index and Recommended Submission Order.

Run with the venv interpreter, from the project root:

```bash
bash tmp/q<N>.sh
```

Prerequisite: the council server must be running first — `cd tools/llm-council && ./start.sh`
in a separate terminal.

Output lands at `docs/council/YYYY-MM-DD_<topic>.md`. Read it — Stage 3 Chairman Synthesis
first — then update `DECISIONS.md` and the relevant plan/strategy doc per
`docs/council/README.md` §"Workflow". Once absorbed, the file moves to the matching
`docs/archive/council/<category>/` subfolder and gets a row in `docs/council/README.md`
§"Archived Decisions".

## Choosing a template

| Template | Use for |
|---|---|
| `strategy_parameters` | Entry/exit rules, delta targets, sizing, kill criteria |
| `backtest_methodology` | IV reconstruction, slippage, cost model, data pipeline |
| `data_architecture` | Storage choices, API integration, module design |

Full definitions: `scripts/council/council_templates/<template>.md`.
