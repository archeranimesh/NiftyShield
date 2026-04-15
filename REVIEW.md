# Python Code Review Guidelines

A consolidated reference covering subtle bug detection, clean code principles, and Pythonic idioms. Organized in two parts: **Part I** focuses on catching bugs; **Part II** focuses on structural quality and idiomatic Python.

---

## Part I: Catching Subtle Bugs

### 1. Mutable Default Arguments — The Classic Silent Killer

```python
# Wrong — `items` is shared across ALL calls (evaluated once at definition time)
def process(data, items=[]):
    items.append(data)
    return items

# Right
def process(data, items=None):
    if items is None:
        items = []
    items.append(data)
    return items
```

**Rule:** Flag every mutable default (`[]`, `{}`, `set()`, custom objects). No exceptions. The default is evaluated *once* at function definition time, not per call.

---

### 2. Late Binding Closures

```python
# Bug — all lambdas return 4, not 0..4
funcs = [lambda: i for i in range(5)]
funcs[0]()  # Returns 4, not 0

# Fix — capture value at creation time
funcs = [lambda i=i: i for i in range(5)]
```

**Rule:** Any lambda or nested function inside a loop that references the loop variable is suspect. The closure captures the *variable*, not its *value at creation time*.

---

### 3. Exception Swallowing and Bare `except`

```python
# Wrong — catches SystemExit, KeyboardInterrupt, MemoryError, and your own bugs
try:
    result = risky_operation()
except:
    pass  # silently swallows everything

# Also wrong — still swallows AttributeError, TypeError, NameError (your bugs)
try:
    result = risky_operation()
except Exception:
    pass

# Right
try:
    result = risky_operation()
except (ValueError, IOError) as e:
    logger.error("Expected failure: %s", e)
    raise
```

**Rule:** Every `except` must name specific exception types. Every caught exception must be logged or re-raised. `pass` in an except block requires a comment that justifies it.

---

### 4. Identity vs Equality (`is` vs `==`)

```python
# Wrong — CPython only interns small integers (-5 to 256)
x = 1000
y = 1000
x is y  # False

# Dangerous — fails for truthy non-bool values
if some_value is True:    # misses 1, "yes", [1], etc.
if some_value == True:    # also wrong — 1 == True is True in Python
```

**Rule:** `is` is only valid for `None`, `True`, `False`, and sentinel objects. `==` for everything else. Flag `is True`/`is False` comparisons on non-bool-typed values.

---

### 5. Float Comparisons

```python
0.1 + 0.2 == 0.3  # False — IEEE 754 representation error

# Right
import math
math.isclose(0.1 + 0.2, 0.3)  # True

# For financial calculations
from decimal import Decimal
Decimal("0.1") + Decimal("0.2") == Decimal("0.3")  # True
```

**Rule:** No `==` comparisons between floats. Use `math.isclose()` or `decimal.Decimal` for financial work. Loop termination on float counters is always a red flag.

---

### 6. Generator Exhaustion

```python
gen = (x for x in range(10))
list(gen)   # [0..9]
list(gen)   # [] — silently empty, no error

# If you need to iterate multiple times, materialize it
items = list(x for x in range(10))
```

**Rule:** Generators passed as arguments should be documented as "consumed." If a function needs to iterate multiple times, accept a `Sequence` or materialize with `list()` at the entry point.

---

### 7. Dictionary Mutation During Iteration

```python
# Wrong — RuntimeError in Python 3
for k in d:
    if condition(k):
        del d[k]

# Right — iterate over a copy of keys
for k in list(d):
    if condition(k):
        del d[k]
```

**Rule:** Never mutate a dict/set/list while iterating it. Flag any loop body that calls `.update()`, `.pop()`, `del`, or `.append()` on the container being iterated.

---

### 8. `__eq__` Without `__hash__`

Defining `__eq__` on a class sets `__hash__` to `None` automatically — making instances unhashable. They silently fail when used as dict keys or set members.

```python
class Point:
    def __eq__(self, other):
        return self.x == other.x and self.y == other.y
    # Missing __hash__ — Point() can't be used in sets or as dict keys

# Fix
    def __hash__(self):
        return hash((self.x, self.y))
```

**Rule:** Any class with `__eq__` must explicitly define `__hash__`, or be documented as unhashable.

---

### 9. `copy` vs `deepcopy` — Reference Aliasing

```python
a = [[1, 2], [3, 4]]
b = a.copy()          # shallow copy — inner lists are shared
b[0].append(99)
print(a[0])           # [1, 2, 99] — a was mutated!

# Fix
import copy
b = copy.deepcopy(a)
```

**Rule:** Wherever an object is "cloned" for safety, verify it's `deepcopy` if nested mutables are involved. `copy.copy()` is almost never the right answer for complex objects.

---

### 10. `isinstance` vs Type Checking — Subclass Blindness

```python
isinstance(True, int)    # True — bool is a subclass of int
type(True) is int        # False

# If you want to exclude bools from an int check:
def accepts_int(x):
    if isinstance(x, bool) or not isinstance(x, int):
        raise TypeError(f"Expected int, got {type(x).__name__}")
```

**Rule:** Prefer `isinstance` for polymorphism. Explicitly guard booleans when the API should reject them as integers.

---

### 11. `None` as a Sentinel When `None` Is a Valid Value

```python
# Bug — can't distinguish "not found" from "stored None"
def get(key, default=None):
    value = cache.get(key, None)
    if value is None:
        return default

# Fix — use a private sentinel object
_MISSING = object()

def get(key, default=_MISSING):
    value = cache.get(key, _MISSING)
    if value is _MISSING:
        return default if default is not _MISSING else None
    return value
```

**Rule:** If `None` is a valid domain value, use a private sentinel: `_MISSING = object()`. Its absence in any optional-value API is a latent bug.

---

### 12. String Formatting and Injection

```python
# SQL injection
query = f"SELECT * FROM users WHERE name = '{name}'"

# Shell injection
os.system(f"convert {filename}")

# Right
cursor.execute("SELECT * FROM users WHERE name = ?", (name,))
subprocess.run(["convert", filename], check=True)
```

**Rule:** Any f-string or `%`-format feeding into SQL, shell commands, file paths, or `eval`/`exec` is a critical defect. Use parameterized queries, `subprocess` with argument lists, `pathlib` for paths.

---

### 13. `asyncio` Pitfalls — Blocking the Event Loop

```python
# Wrong — blocks entire event loop; no error, just silent starvation
async def handler():
    time.sleep(5)           # blocks
    data = requests.get(url)  # blocks

# Right
async def handler():
    await asyncio.sleep(5)
    async with httpx.AsyncClient() as client:
        data = await client.get(url)
```

**Rule:** In any `async def`, flag every call to `time.sleep`, `requests`, synchronous `open()`, and CPU-intensive loops without `await asyncio.sleep(0)` yield points.

---

### 14. Ordering Assumptions in `dict` and `set`

Dicts are insertion-ordered since Python 3.7. Sets are **never** ordered — iteration order is non-deterministic across runs due to hash randomization.

```python
# Bug — set iteration order is not guaranteed
tags = {"beta", "alpha", "gamma"}
first_tag = list(tags)[0]  # non-deterministic

# Fix
first_tag = sorted(tags)[0]
```

**Rule:** Any code that relies on set iteration order for correctness is a bug. Sort before iterating if order matters.

---

### 15. `dataclass` Mutability Traps

```python
from dataclasses import dataclass, field

# Wrong — raises ValueError at class definition in Python 3.x
@dataclass
class Config:
    tags: list = []

# Right
@dataclass
class Config:
    tags: list = field(default_factory=list)
```

**Rule:** In dataclasses, every mutable field must use `field(default_factory=...)`. The factory must return a *new* object each time, not a cached shared one.

---

### 16. Walrus Operator Scope Leak

```python
data = [5, 15, 25]

if any((found := x) > 10 for x in data):
    print(found)  # Works, but `found` leaks into enclosing scope

# If outer scope already has `found`, it will be silently overwritten
```

**Rule:** Any walrus operator (`:=`) usage must be checked for scope collision with outer variables of the same name. The `:=` operator intentionally escapes comprehension scope by design.

---

### Meta-Rules for the Review Process

- **Read the tests before the code.** Tests reveal what the author *believed* the contract was. Divergence between tests and implementation is where the bugs hide.
- **Grep for `# type: ignore` and `# noqa`.** Each one should have a comment explaining *why*. Silent suppressions are deferred bugs.
- **Every `TODO` and `FIXME` is an open defect.** Treat them as such, not as comments.
- **Run `mypy --strict` on the diff, not just the file.** Type errors often surface in callers, not in the changed function itself.
- **Cyclomatic complexity > 10** in a single function is a strong predictor of uncaught edge cases. Branches that aren't tested don't get caught by code review either.

---

## Part II: Clean, Pythonic Code

### Naming: The First Line of Defense Against Confusion

Names should eliminate the need for comments, not supplement them. If you need a comment to explain what a variable holds, the variable is misnamed.

- Avoid abbreviations except universally understood ones (`i`, `j` for loop indices, `df` for DataFrames). `usr_cnt_lst` is three wrong decisions in one name.
- Boolean names should read as assertions: `is_valid`, `has_permission`, `should_retry`. Never `flag`, `check`, `status` — these are nouns, not predicates.
- Functions should be named for what they *return* or *do*, not how they do it. `get_active_users()` is better than `query_database_for_users_with_active_flag()`.

---

### Functions: One Job, One Level of Abstraction

The most common violation is mixing *abstraction levels* within one function.

```python
# Wrong — fetch + transform + validate + persist in one function
def process_orders(db_conn):
    rows = db_conn.execute("SELECT * FROM orders WHERE status='pending'")
    orders = [Order(r['id'], r['amount'], r['user_id']) for r in rows]
    for order in orders:
        if order.amount > 10000:
            order.flag_for_review()
        order.status = 'processed'
    db_conn.executemany(
        "UPDATE orders SET status=? WHERE id=?",
        [(o.status, o.id) for o in orders]
    )

# Right — each function operates at one abstraction level
def process_orders(db_conn):
    orders = fetch_pending_orders(db_conn)
    updated = [apply_business_rules(o) for o in orders]
    persist_orders(db_conn, updated)
```

**Test:** Can you describe what the function does in one sentence without using "and"? If not, split it.

**Argument count:** More than 3 arguments is a design smell. Use keyword-only enforcement to prevent argument order bugs:

```python
def create_order(*, user_id, amount, currency, notify=True):
    ...
```

---

### Classes: Don't Fight Python's Object Model

A class is justified when it has both state *and* behavior that are inseparable, or when you need to implement a protocol. If a class has only `__init__` and one other method, it's probably a function with a config object.

**Properties over getters/setters:**

```python
# Wrong — Java import
def get_rate(self): return self._rate
def set_rate(self, value): self._rate = value

# Right
@property
def rate(self):
    return self._rate

@rate.setter
def rate(self, value):
    if not 0 < value < 1:
        raise ValueError(f"Rate must be between 0 and 1, got {value}")
    self._rate = value
```

**`__repr__` is not optional.** Every class should have one. The default `<MyClass object at 0x7f...>` is useless in logs and tracebacks. With `dataclass`, you get this for free.

```python
def __repr__(self):
    return f"Order(id={self.id!r}, amount={self.amount!r}, status={self.status!r})"
```

---

### Pythonic Patterns That Signal Mastery

**`enumerate` over range-indexing:**

```python
# Wrong — latent off-by-one risk
for i in range(len(items)):
    print(i, items[i])

# Right
for i, item in enumerate(items):
    print(i, item)
```

**`zip` with `strict=True` (Python 3.10+):**

```python
# Silent truncation on mismatched lengths
for a, b in zip(list_a, list_b):
    ...

# Right — raises if lengths differ
for a, b in zip(list_a, list_b, strict=True):
    ...
```

**Context managers for every resource:**

```python
# Wrong — resource may not be released on exception
conn = db.connect()
result = conn.execute(query)
conn.close()

# Right
with db.connect() as conn:
    result = conn.execute(query)

# Custom context manager
from contextlib import contextmanager

@contextmanager
def timed_block(label):
    start = time.perf_counter()
    yield
    print(f"{label}: {time.perf_counter() - start:.3f}s")
```

**`collections` is underused:**

```python
from collections import defaultdict, Counter, deque

# Instead of: if key not in d: d[key] = []
groups = defaultdict(list)
for item in items:
    groups[item.category].append(item)

# Instead of manual frequency counting
freq = Counter(words)
top_5 = freq.most_common(5)

# Fixed-size sliding window — useful for rolling metrics
window = deque(maxlen=20)
window.append(new_value)  # auto-evicts oldest
```

**Comprehension complexity limit:**

```python
# Acceptable — one condition, one transformation
result = [transform(x) for x in items if predicate(x)]

# This should be a loop — too many operations in one expression
result = [transform(x) for sublist in matrix
          for x in sublist if predicate(x) and another(x)]
```

---

### Type Annotations: Use Them as Design Feedback

Type hints are a *design tool*, not just documentation. When you find yourself writing `Union[str, int, None, list]` as a return type, the type system is telling you the function is doing too much.

```python
from typing import Optional, TypedDict

# Optional signals the caller must handle None
def find_user(user_id: int) -> Optional[User]:
    ...

# TypedDict for structured dicts you don't control
class OrderResponse(TypedDict):
    order_id: str
    status: str
    amount: float

# Python 3.10+ union syntax
def process(value: str | int | None) -> str:
    ...
```

- Avoid `Any` except at true system boundaries (JSON deserialization, untyped third-party libraries).
- `Any` is a type-system escape hatch that silences the checker — same as `# type: ignore`, it defers bugs.
- `TypedDict` for structured dicts you don't control (API responses, config files). A raw `dict[str, Any]` passed through five functions is untyped code.

---

### Error Handling: Fail Loudly at the Right Level

Don't return `None` to signal failure — Python has exceptions. Build a custom exception hierarchy per module:

```python
# Base exception per subsystem
class NiftyShieldError(Exception): ...
class BrokerConnectionError(NiftyShieldError): ...
class OrderValidationError(NiftyShieldError): ...

# Usage — callers can catch at the right specificity level
try:
    broker.submit(order)
except BrokerConnectionError:
    retry_with_backoff()
except OrderValidationError as e:
    logger.error("Invalid order: %s", e)
    raise
```

**Don't use exceptions for flow control:**

```python
# Wrong — exception as conditional
try:
    value = d[key]
except KeyError:
    value = default

# Right — use the conditional directly
value = d.get(key, default)
```

---

### Comments: Explain *Why*, Never *What*

A comment that restates what the code does is noise that will drift out of sync with the code and become a lie.

```python
# Wrong — restates the code
i += 1  # increment i

# Right — explains why
# Using 1-indexed here to match NSE strike price convention
strike_index = position + 1

# Right — explains what was deliberately avoided
# Not using sorted() here: the list is almost always pre-sorted
# and timsort's O(n) best case matters at this call frequency
_apply_fast_path(items)
```

Docstrings describe the *contract* of a public function — what it expects, what it returns, what it raises:

```python
def fetch_option_chain(symbol: str, expiry: date) -> OptionChain:
    """Fetch the full option chain for a given symbol and expiry.

    Args:
        symbol: NSE symbol, e.g. "NIFTY".
        expiry: Option expiry date. Must be a valid NSE expiry Thursday.

    Returns:
        OptionChain with CE and PE legs populated.

    Raises:
        BrokerConnectionError: If the upstream API is unreachable.
        ValueError: If expiry is not a valid NSE expiry date.
    """
```

---

### Module and Package Structure: The Import Is the API

- Prefix internal symbols with `_` or control exports via `__all__` in `__init__.py`.
- Circular imports are a *structural* problem, not an import problem. Fixing them with `import` inside functions is a workaround, not a solution — it usually means two modules that should be one, or a shared dependency that should be a third module.

```python
# __init__.py — explicit public API
__all__ = ["BrokerClient", "OrderValidationError", "fetch_option_chain"]
```

---

## The Underlying Principle

Pythonic code and clean code converge on the same goal: **code that communicates intent so clearly that bugs have nowhere to hide.** A bug can only persist undetected in code that is ambiguous, overly complex, or poorly named. Every rule above is a different attack on the same problem — reducing the gap between what the code *says* and what it *does*.

The Zen connection is real but indirect: *"Explicit is better than implicit," "Errors should never pass silently," "In the face of ambiguity, refuse the temptation to guess"* — these are all anti-patterns that manifest as the bugs catalogued above. The Zen tells you *what* good code looks like; this document tells you *where* the gaps between intention and execution hide.
