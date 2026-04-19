# Code Style and Quality Rules

## Python Style (PEP 8 + Best Practices)

### Naming Conventions

- Functions and variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private attributes: `_leading_underscore`
- Avoid single-letter names except loop counters (`i`, `j`, `k`)

### Function Design

- Functions should do one thing (Single Responsibility Principle)
- Keep functions under 30 lines; if longer, refactor
- Maximum 4 positional parameters; use kwargs or dataclass for more
- Avoid boolean flag arguments — split into two functions instead
- Avoid returning `None` implicitly; be explicit

**Example:**
```python
# BAD: boolean flag argument
def process_data(data, is_async=False):
    ...

# GOOD: separate functions
def process_data(data): ...
def process_data_async(data): ...
```

### Error Handling

- Never use bare `except:` — always catch specific exceptions
- Don't silently swallow exceptions (`except Exception: pass`)
- Use context managers (`with`) for resource management
- Raise early, return late

**Example:**
```python
# BAD: bare except
try:
    result = risky_operation()
except:
    pass

# GOOD:
try:
    result = risky_operation()
except ValueError as e:
    logger.error(f"Invalid value: {e}")
    raise
```

### Imports

- Standard library imports first, then third-party, then local
- No wildcard imports (`from module import *`)
- Unused imports should be removed

### Type Hints

- All function signatures should have type hints (Python 3.9+)
- Use `Optional[X]` or `X | None` for nullable types
- Use `list[X]`, `dict[K, V]`, `tuple[X, Y]` (PEP 585)

**Example:**
```python
# BAD:
def process(data, callback=None):
    ...

# GOOD:
from typing import Callable, Optional
def process(data: list[dict], callback: Optional[Callable] = None) -> None:
    ...
```

## Code Smells

### Long Methods

Methods over 30 lines are candidates for extraction. Extract logical sub-sections into named helper functions.

### Deep Nesting

More than 3 levels of nesting reduces readability. Use early returns (guard clauses) to flatten logic.

**Example:**
```python
# BAD: deeply nested
def process(data):
    if data:
        if data.get("users"):
            for user in data["users"]:
                if user.get("active"):
                    send_email(user)

# GOOD: guard clauses
def process(data):
    if not data or not data.get("users"):
        return
    for user in data["users"]:
        if user.get("active"):
            send_email(user)
```

### Magic Numbers

Named constants should replace magic numbers in code.

```python
# BAD:
if score > 85:
    award_bonus()

# GOOD:
BONUS_THRESHOLD = 85
if score > BONUS_THRESHOLD:
    award_bonus()
```

### Mutable Default Arguments

Never use mutable default arguments in Python.

```python
# BAD: shared state bug
def append_to(element, to=[]):
    to.append(element)
    return to

# GOOD:
def append_to(element, to=None):
    if to is None:
        to = []
    to.append(element)
    return to
```

### God Classes

A class with too many responsibilities should be split. Signs: over 200 lines, more than 10 methods, methods that don't use `self`.

### Duplicate Code (DRY Violations)

Identical or near-identical code blocks in multiple places. Extract to a shared function or class.

## Performance Patterns

### N+1 Query Problem

Database queries inside loops cause N+1 queries.

```python
# BAD: N+1 queries
for user in users:
    profile = db.query(Profile).filter(Profile.user_id == user.id).first()

# GOOD: join or bulk fetch
profiles = {p.user_id: p for p in db.query(Profile).filter(Profile.user_id.in_([u.id for u in users])).all()}
```

### String Concatenation in Loops

Use `"".join(list)` instead of `+=` in loops.

```python
# BAD:
result = ""
for item in items:
    result += str(item)

# GOOD:
result = "".join(str(item) for item in items)
```

## JavaScript / TypeScript Style

### Use `const` by Default

Prefer `const` over `let`. Never use `var`.

### Avoid `any` Type in TypeScript

`any` defeats the purpose of TypeScript. Use proper types or `unknown`.

### Async/Await Over Callbacks

Prefer `async/await` over raw promise chains for readability.

### Null Safety

Use optional chaining (`?.`) and nullish coalescing (`??`) instead of verbose null checks.

```typescript
// BAD:
const name = user && user.profile && user.profile.name ? user.profile.name : "Unknown";

// GOOD:
const name = user?.profile?.name ?? "Unknown";
```
