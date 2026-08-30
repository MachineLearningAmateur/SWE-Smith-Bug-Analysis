# attrs.define decorator doesn't work with bare annotations

## Description

I found a bug when using the `attrs.define` decorator with bare annotations. When using the newer `attrs.define` style decorators (as opposed to the older `attr.s` style), class attributes defined with only type annotations (without an explicit `attr.ib()` or similar) are not properly recognized.

## Steps to Reproduce

Here's a simple example that demonstrates the issue:

```python
import attrs

@attrs.define
class Foo:
    bar: int
    baz: str = "hello"

# Try to create an instance
foo = Foo(1)
```

When running this code, the attributes `bar` and `baz` are not properly recognized as attrs attributes, causing issues with initialization and attribute access.

## Expected Behavior

The code should work correctly, with `bar` and `baz` being recognized as proper attrs attributes. This is the documented behavior of the newer `attrs.define` decorator, which should support bare annotations without requiring explicit `attr.ib()` calls.

## Actual Behavior

The attributes defined with bare annotations are not properly recognized when using the newer `attrs.define` style decorators. This causes initialization to fail or attributes to be inaccessible.

## Additional Information

This issue only affects the newer `attrs.define`, `attrs.mutable`, and `attrs.frozen` decorators. The older `attr.s` style decorators don't have this issue when used with explicit `attr.ib()` calls.

A workaround is to use explicit `attr.ib()` calls instead of bare annotations:

```python
import attrs

@attrs.define
class Foo:
    bar = attrs.field(type=int)
    baz = attrs.field(type=str, default="hello")
```

But this defeats the purpose of the newer, more concise annotation syntax that attrs supports.
