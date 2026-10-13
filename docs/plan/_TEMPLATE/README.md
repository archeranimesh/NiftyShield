<!-- This file is guidance for whoever starts a new plan folder. It is not copied. -->

# `docs/plan/_TEMPLATE/` — how to start a plan folder

Size to scope (see `docs/plan/README.md` §Conventions "Folder shapes"):

## Single story — one coherent goal

```
cp -r docs/plan/_TEMPLATE/story docs/plan/<slug>
```

`<slug>` kebab-case, no date prefix. Fill in `prompt.md`, `tasks.md`, `stories.md`.
Keep `schema.md.example` → `schema.md` **only** if the story changes DB schema; otherwise
delete it.

## Epic — two or more related stories

```
cp -r docs/plan/_TEMPLATE/epic docs/plan/<epic-slug>
cp -r docs/plan/_TEMPLATE/story docs/plan/<epic-slug>/<story-slug>   # once per story
```

Fill in the epic root `prompt.md` (the router — list the stories in fixed order) and
`README.md` (the shared brief). The epic root has **no `tasks.md`** — every checkbox lives
in a sub-story's `tasks.md`.

## Both templates

`story/` and `epic/` are kept in sync by hand — a change to the story skeleton
(`story/prompt.md` etc.) is the same file an epic sub-story uses, so there is only one copy
of it. `_TEMPLATE/` is excluded from `check_story_structure.py` and
`check_checkbox_consistency.py`.
