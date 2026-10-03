# Python hygiene checklist — and how to automate it

> `design-principles.md` covers architecture-level discipline (SOLID, DIP, named patterns) — decisions made once, at the shape of a class or module. This doc covers the other layer: line-level Python
> defect patterns that recur in day-to-day diffs, and the automation that should be catching them mechanically instead of relying on a human (or an AI assistant) remembering a checklist. The two
> layers are deliberately separate docs: one is read occasionally while designing a module, the other is meant to be enforced on every commit and rarely read in full at all.

## Why this is a separate doc from `design-principles.md`

A design-principles reference doc is meant to be loaded on demand and applied by judgment — see that doc's own closing section on when a static doc stops being enough. The checklist below is exactly
the kind of content that doc was warning against folding in: a long, mechanically-checkable list bloats a judgment-based reference and, worse, duplicates something a tool should be doing instead. Put
it here, keep it short to read once, and push enforcement onto tooling (see "Automate it" below) rather than onto memory.

## Defect patterns worth a named check

Each of these is a concrete, recurring Python bug shape — not a style preference. A linter/type-checker catches some of these outright; the rest need either a custom lint rule or a reviewer (human or
AI) trained to look for the shape specifically.

- **Mutable default arguments** — `def f(x=[])` / `def f(x={})`. The default is created once at function-definition time and shared across every call that doesn't pass its own value.
- **Late-binding closures in a loop** — a lambda or nested function defined inside a loop that captures the loop variable by reference, not by value at definition time; every closure ends up seeing
  the loop's final value.
- **Bare or overly broad `except`** — `except:` or `except Exception: pass` with no logging or re-raise. See `design-principles.md`'s EAFP section and `code-deduplication-and-taxonomy.md`'s
  module-boundary exception wrapping for the shape this should take instead.
- **Generator exhaustion** — a generator handed to two consumers; the second iteration silently comes back empty because the first already consumed it.
- **Container mutation during iteration** — `del`, `.pop()`, `.update()`, `.append()` on the same dict/set/list currently being iterated.
- **`__eq__` without `__hash__`** — a class defining `__eq__` must also define `__hash__` explicitly, or the instance silently becomes unhashable.
- **`None` used as a sentinel when `None` is itself a valid domain value** — use a dedicated sentinel (`_MISSING = object()`) instead.
- **Set iteration-order assumptions** — `list(some_set)[0]` or any code relying on a `set`'s iteration order.
- **`zip` without `strict=True`** (Python 3.10+) — mismatched-length sequences silently truncate instead of raising.
- **`copy.copy()` on nested mutable structures** — should be `copy.deepcopy()` when the object contains nested mutables that must not be shared with the original.
- **SQL/shell injection** — an f-string or `%`/`.format()` string feeding `cursor.execute()`, `os.system()`, or `subprocess` with `shell=True`; require parameterized queries and argument lists
  instead.
- **Identity vs. equality (`is` vs. `==`)** — `is` is only valid for `None`, `True`, `False`, and sentinel objects; flag `is True`/`is False` against a non-bool-typed value, and flag `is` used on
  ints/strings expecting CPython's small-int/string interning to hold.
- **Float comparisons** — any `==`/`!=` between floats; require `math.isclose()`, or `decimal.Decimal` for financial values.
- **`asyncio` blocking the event loop** — `time.sleep`, a synchronous HTTP call, synchronous `open()`, or a CPU-intensive loop with no yield point inside an `async def`.
- **`dataclass` mutable-default traps** — a mutable default (`list`/`dict`/`set` literal) on a dataclass field instead of `field(default_factory=...)`.
- **Walrus operator (`:=`) scope leak** — a walrus assignment inside a comprehension/generator expression whose bound name could collide with an existing name in the enclosing scope (`:=`
  intentionally escapes comprehension scope).

## Design-quality signals (lower priority than the defects above)

These don't usually break anything today, but each is a predictor of a bug or a maintenance cost later. Skip anything your linter/formatter already flags — don't duplicate `ruff`/`black` output here.

- **Abstraction-mixing functions** — fetch, transform, validate, and persist all in one body; a good test is whether the function's purpose can be stated in one sentence without "and."
- **Argument count > 3** — prefer keyword-only arguments (`def f(*, a, b, c)`) to prevent argument-order bugs.
- **Getter/setter methods instead of `@property`** — the Java-style pattern Python doesn't need.
- **Missing `__repr__`** on a hand-written class with meaningful state (not needed on `@dataclass`, which generates one).
- **`range(len(x))` indexing** instead of `enumerate(x)`.
- **Manual resource open/close** instead of a context manager (`with`), including a custom `@contextmanager` where cleanup-on-exception matters.
- **Manual patterns `collections` already solves** — a `dict.setdefault`/`if key not in d` bucket instead of `defaultdict`, manual frequency counting instead of `Counter`, a manually-truncated list
  instead of `deque(maxlen=...)`.
- **Comprehensions doing more than one condition + one transform** — nested-loop comprehensions with multiple predicates should be a plain loop instead.
- **Broad return types** (`Union[str, int, None, list]`-shaped signatures, or `dict[str, Any]` passed through several functions) — a signal the function is doing too much, or should use a `TypedDict`
  / a narrower type.
- **`Any` used outside a true system boundary** (JSON/third-party deserialization) — it silences the type checker the same way `# type: ignore` does.
- **`None`-return for failure** instead of raising a purpose-built exception from a small per-module exception hierarchy.
- **Exceptions used for flow control** — e.g. `try: d[key] except KeyError:` where `d.get(key, default)` says the same thing directly. Note the tension with the EAFP guidance in
  `design-principles.md`: EAFP is for genuinely exceptional failure, not for a lookup that has an obvious default.
- **Comments that restate the code** ("increment i") instead of explaining *why* a non-obvious choice was made.
- **No explicit public API on a package** — prefer `__all__` in `__init__.py`; treat a circular import fixed with a function-local `import` as a structural problem to flag, not a resolved one.

## Automate it, don't just document it

A checklist like the one above is only as good as someone remembering to apply it. The point of a refactor that's building fresh infrastructure is to make as much of this mechanical as possible, so it
runs the same way on every commit regardless of who (or what) is writing the code. Layer the automation like this, roughly in order of effort-to-value:

1. **A `lint`/`typecheck`/`test` target in one place** — a `Makefile` (or equivalent task runner) with named targets (`make lint`, `make typecheck`, `make test`) is the single command a person or a CI
   job runs; it should wrap `ruff`/`flake8` (fast line-level lint + import order + many of the defect patterns above), `mypy`/`pyright` (catches a large fraction of the type-shaped defects — `Any`
   leakage, broad return types, some `None`-handling bugs — for free), and `pytest`. Keep a `make help`-style self-documenting target so the list of available checks doesn't silently drift out of sync
   with what's actually wired up.

### Pin an explicit rule selection — don't rely on a tool's shifting defaults

A linter's *default* rule set is itself an implicit dependency: it changes across tool versions without this doc changing, which is exactly the "explicit is better than implicit" problem the rest of
this playbook argues against elsewhere. Two projects pinning the same `ruff`/`mypy` *version* but relying on defaults can still end up enforcing different things a year apart, or a new project started
today can silently end up enforcing *more* or *less* than the project this playbook came from. Select rules explicitly in `pyproject.toml` instead, so the enforced set is a reviewable,
version-controlled fact, not a side effect of whichever version happens to be installed. The selection below is one concrete mapping from this doc's own defect/design-quality catalog onto `ruff` rule
codes — verify against your installed `ruff` version's own rule list before trusting it (`ruff check --show-settings <file>` prints the actually-resolved set), since codes do get renamed or
reorganized between major versions:

```toml
[tool.ruff.lint]
select = [
    "E", "F", "W",     # pycodestyle + pyflakes — baseline correctness/style
    "B",               # flake8-bugbear — mutable defaults (B006), late-binding closures (B023),
                       # function-call-in-default-argument (B008), and friends
    "B9",              # bugbear's opinionated extras — zip-without-explicit-strict (B905) lives here,
                       # NOT in the plain "B" set; must be selected explicitly
    "BLE",             # blind/bare `except Exception` (BLE001)
    "S",               # flake8-bandit — the FULL injection/secrets/security set (hardcoded SQL,
                       # subprocess shell=True, hardcoded passwords); only S102/S110/S112 ship by
                       # default, the rest of "S" must be selected explicitly
    "C4",              # flake8-comprehensions — unnecessary/overcomplicated comprehensions
    "SIM",             # flake8-simplify — manual patterns `collections`/stdlib already solves
    "ASYNC",           # flake8-async — blocking calls inside `async def`
    "RUF",             # ruff-native rules — mutable dataclass defaults (RUF008/009), and more
    "PLR0913",         # too-many-arguments — NOT included by plain "PLR"; add explicitly
    "C901",            # McCabe complexity — the `max-complexity` setting exists by default but the
                        # rule itself is NOT enabled unless selected explicitly
]

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.mypy]
disallow_untyped_defs = true   # every public function needs a type-hinted signature
warn_return_any = true         # catches `Any` leaking out of a function boundary
no_implicit_optional = true    # catches the "None used as a sentinel" shape at the type level
strict_equality = true         # flags `==`/`!=` between incompatible types
```

Treat this as a starting point to adapt, not a value to copy blindly — a project with no `async` code gets no value from the `ASYNC` category, and a project that genuinely needs `Any` at its
boundaries (e.g. heavy `dict`-shaped third-party JSON) should scope `warn_return_any` exceptions explicitly rather than fighting it everywhere. The discipline that matters is *explicit selection*, not
this exact list.
2. **A `pre-commit` hook running the same checks locally, before a commit lands** — this is what turns "the CI will catch it eventually" into "it never gets committed in the first place." Wire actual
   tool hooks (`ruff`, `mypy`, a secrets scanner, a basic security linter) here, not just formatting checks — a hook that only reformats whitespace is leaving most of the defect list above uncaught.
3. **A security/secrets layer** — a static-analysis security linter (flags the injection/`shell=True`/unsafe-deserialization shapes above) and a secrets scanner (blocks a credential literal from ever
   reaching a commit) are cheap to add once the hook framework exists, and catch exactly the class of defect that's most expensive to find after the fact.
4. **An AI-reviewer hook for the patterns a static tool can't express as a rule** — several items in both lists above (late-binding closures, abstraction-mixing, "does this comment explain *why*") are
   structurally hard to write as an AST-matching lint rule but are easy for a model to recognize given the diff. A pre-commit hook that sends the staged diff to a narrowly-scoped, read-only review
   agent — one with no file-write/execute/network tool access, so a prompt-injection attempt in the staged content has nothing to act on even if it fools the model — closes this gap without needing a
   human reviewer to hold the whole checklist in their head on every commit. Treat a failure to reach a verdict (tool unavailable, request timeout, diff too large) as a skip, not a block — this should
   be an advisory safety net layered on top of human review, never a hard gate that can wedge a routine commit shut.
5. **Phase the adoption, don't block on it being complete** — a project early in a refactor (no `src/` yet, no test suite yet) should not stand up the full stack above on day one; declare which hooks
   are deferred and why (a one-line comment in the hook config is enough), and add them back in as soon as the structure they depend on exists. An empty or trivially-passing hook that nobody remembers
   is active is worse than an honestly-deferred one, because it creates false confidence that a check is running when it isn't.

The shape above is deliberately generic — the specific tool names (`ruff`, `mypy`, a particular secrets scanner) are a point-in-time choice, not a requirement; what matters is the *layering*: fast
local lint, type-checking, tests, security/secrets, then an AI-assisted catch-all for the shapes that resist a mechanical rule, with an explicit deferred-list for anything not yet wired up.
