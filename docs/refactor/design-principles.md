# Design principles

> Code-level discipline applied while re-implementing legacy logic. This is the restated, project-agnostic form of a "Python design reference" doc used during a real refactor — keep it as a
> trigger-based reference loaded on demand, not a resident essay re-read every session.

## Governing frame: simplicity first (PEP 20)

Treat the Zen of Python's core tenets as non-negotiable, not style preferences: explicit over implicit, simple over complex, flat over nested. A deeply nested conditional chain inside a decision
method is both a readability violation *and*, almost always, the concrete Open/Closed violation described below. If a change makes a function harder to read top-to-bottom, or adds another branch to
logic that already branches, stop before writing it — that feeling is the signal, not a thing to push through. Run `python -c "import this"` if the list ever needs re-reading in full.

## SOLID — as checkable triggers, not an essay

A generic "follow SOLID" reminder does not change behavior at the point of an edit. A named trigger — a concrete thing you're about to do, and what to do instead — does. Use this table while writing
or reviewing a class, not as background reading:

- **SRP — trigger:** you're adding a method to a class whose existing methods already cover a different concern (entry logic next to persistence next to notification). **Do instead:** a new class for
  the new concern; the original class keeps only its own job.
- **OCP — trigger:** you're adding a new `elif`/`case`/`switch` branch to an existing decision method to handle a new variant. **Do instead:** extract the decision into an interface, make the existing
  branches separate implementers, add the new variant as a new implementer — nothing existing is edited.
- **LSP — trigger:** a subclass overrides a method that narrows accepted inputs or returns something the base type's callers don't expect. **Do instead:** if the subclass can't honor the base
  contract, it isn't substitutable — split the interface instead of special-casing the subtype at call sites.
- **ISP — trigger:** an interface has grown methods that only some implementers use, so others implement stubs or raise "not implemented." **Do instead:** split into smaller interfaces; a class
  implements only the ones it actually needs.
- **DIP — trigger:** a class constructs its own collaborator directly (e.g. `self.store = ConcreteStore()`) instead of receiving it. **Do instead:** inject the collaborator via the constructor, typed
  as an interface, not a concrete class — this is what makes the class testable without a real DB/network/external call.

### `Protocol` over `abc.ABC` — the Pythonic default for the "interface" above

Every "interface" referenced above should default to `typing.Protocol` (PEP 544), not `abc.ABC`, unless you specifically need shared default-method bodies or `isinstance`-based runtime registration
that only nominal inheritance gives you. `Protocol` is structural: a class satisfies it by shape alone, with no explicit `class Foo(MyProtocol):` inheritance required. This is duck typing made
checkable rather than duck typing abandoned for a Java-style nominal interface — it's the more Pythonic choice precisely because it doesn't force every implementer into an inheritance relationship it
doesn't otherwise need. Mark it `@runtime_checkable` only where an actual `isinstance(x, MyProtocol)` check is needed at runtime (most call sites don't need one — static type-checking already covers
the common case).

### Why DIP is usually the first one to land

In a legacy-duplication refactor, the single highest-leverage design decision is almost always constructor injection of external-system collaborators (database clients, HTTP clients, cloud SDK
clients). Every duplicated "do the same external call three different ways in three different projects" problem traces back to each original constructing its own client internally. Fixing DIP first is
what makes every other principle's fix (testability in particular) possible without real network/DB access in tests.

## Concrete example: the seam that prevents an unbounded strategy file

A domain-orchestration class should hold sequencing only. Each decision it makes is a separate injected collaborator:

```
Orchestrator                  # sequencing only — e.g. check entry condition, size, monitor, check exit condition
├── EntryRule (interface)     # decides when/whether to start
├── ExitRule (interface)      # decides when/whether to stop
├── ReschedulePolicy (iface)  # decides retry/rollover timing and parameters
├── Sizer                     # pure function over inputs, no I/O
└── Store (interface)         # persistence
```

The orchestrator structurally cannot grow past a few hundred lines — it has nowhere to put variant-specific logic. A new variant is a new `EntryRule`/`ReschedulePolicy` implementation, not a fork of
an existing file, and not a new branch inside one.

## Named patterns worth knowing by name — and their Python-native shape

Classic design-pattern names are useful vocabulary, but applying them as if Python were Java produces more class hierarchy than the language needs. For each, know the GoF shape *and* the
usually-simpler Python-native shape, and default to the latter unless the GoF shape is genuinely earning its weight (e.g. several implementations really do share non-trivial state/behavior, not just
one method):

- **Strategy** — the DIP seam above, generalized: interchangeable algorithms selected at construction/config time. In Python this is often just a `Callable`-typed parameter or a plain function passed
  around — a class implementing a one-method `Protocol` is only better than a bare function when the strategy needs to carry its own state/config across calls. Don't default to a class if a function
  does the job; "there should be one obvious way to do it" argues for the plain function first.
- **Factory Method** — trigger: a constructor is branching on a `type`/config string to decide which concrete class to build. In Python, this is most often a module-level function or a registry `dict`
  (`{"csv": CsvWriter, "json": JsonWriter}[fmt]()`), not a `Factory` class — a `dict` lookup is flatter and more explicit than a class whose only job is to branch once. Reach for a full Factory class
  only once construction itself needs multiple steps or shared setup, not merely a type-to-class mapping.
- **Template Method** — a fixed sequence (e.g. entry → size → monitor → exit) is the template; each step delegates to an injected Strategy object (or function) rather than containing logic itself.
  This one does genuinely want a class in Python too, since the *sequence* itself is the thing being reused across variants, not a single swappable step.
- **Decorator (the pattern) vs. `@decorator` (the Python feature)** — same name, often conflated. The GoF pattern (trigger: adding a conditional guard, e.g. a validation or rate-limit check, by
  editing an existing class's method) is "wrap the base object in a new class implementing the same interface, which the base object never knows about." In Python, the *language's own* decorator
  syntax routinely solves the identical cross-cutting-guard problem more simply — a plain `@decorator`-wrapped function, or a context manager, rather than a parallel class hierarchy — because Python
  functions are first-class objects and don't need an interface to be substitutable. Default to a function decorator or context manager for a cross-cutting guard around a function; reach for the
  class-wrapping GoF shape only when the thing being decorated is itself a stateful object with multiple methods, not a single callable.
- **Observer** — only reach for this once something already needs to react to state changes (a tracker, a notifier) and a direct call/return value is getting awkward. In Python this is usually a plain
  `list[Callable]` of listener callbacks on the subject, not a formal `Observer` abstract base — a callback list is simpler and is exactly what "flat is better than nested" and "simple is better than
  complex" are arguing for; don't introduce a class hierarchy for something a list of functions already solves.

## EAFP over LBYL

Python's idiom is "easier to ask forgiveness than permission": prefer a `try`/`except` around an operation that might fail over a pre-flight check that duplicates the failure condition (e.g. prefer
`try: value = d[key]` / `except KeyError` over `if key in d: value = d[key]` when the dict access is the actual intent). This isn't just a style tic — a pre-flight check is itself a race condition in
anything concurrent, and it duplicates the failure logic the exception path has to handle anyway. This is also why the module-boundary exception wrapping above matters: EAFP only stays readable when
the exceptions being caught are specific and few — a module that lets a dozen different unwrapped third-party exception types leak through turns every caller's `except` block into a guessing game,
defeating the whole point of EAFP being simpler than LBYL.

## When these rules don't resolve the situation at hand

"Although practicality beats purity" is the Zen line that governs this section: have a short, named escalation path (a couple of reference links or a senior reviewer) for edge cases — don't let "SOLID
didn't obviously apply" become license to skip design thought, but don't force a pattern onto a case that genuinely doesn't fit it either. These rules should resolve the common cases on their own;
reserve escalation for genuine edge cases.

## When a static doc stops being enough: consider active enforcement instead

A written reference like this one is read, then applied by judgment. That is the right shape as long as following it stays a matter of a person (or an AI assistant) reading a rule and self-applying
it. It stops being the right shape the moment you want *active, programmatic enforcement* rather than reference — e.g., a lint rule or review-bot check that actually parses a class and flags "this
method has a 4th branch on decision logic, extract an interface implementer" or "this constructor builds its own collaborator instead of receiving it" as a structural/AST check, not a judgment call.

That is a materially different investment than a reference doc — closer to a linter/static-analysis rule than a style guide — and it's worth building only once there is *evidence* the doc-based
approach isn't enough: review keeps catching the same violation shape after the doc already states it, meaning the guidance isn't being self-applied reliably and needs to become an enforced check.
Don't build that enforcement preemptively; it's real infrastructure (a rule engine, a CI gate, ongoing maintenance) for a problem you don't have evidence of yet.

The architecture-level principles above are rarely where this threshold gets crossed first, though — they're judgment calls about class/module shape, not mechanically checkable facts. The line-level
Python defect patterns that recur in day-to-day diffs (mutable defaults, bare `except`, injection-shaped string formatting, and the rest) are exactly the content that *should* cross this threshold
immediately rather than live in a reference doc at all — see `python-hygiene-and-automation.md` for that checklist and the lint/typecheck/pre-commit/AI-reviewer layering that enforces it.
