# [Bug]: Path equality comparison with TType objects is broken

## Description

I found an issue with the `Path.__eq__` method when comparing a `Path` object with a `TType` object. The current implementation doesn't correctly handle equality comparisons between these two types.

## Steps to reproduce

```python
from glom import Path, T

# Create a Path object and a TType object
path_obj = Path(T.a.b)
t_obj = T.a.b

# Compare them - this should be True but fails
result = path_obj == t_obj
print(f"Path(T.a.b) == T.a.b: {result}")  # Returns False when it should be True
```

## Expected behavior

When comparing a `Path` object with a `TType` object that represents the same path, the comparison should return `True`.

## Actual behavior

The comparison returns `False` even when the `Path` object and the `TType` object represent the same path.

## Additional information

The issue appears to be in the `__eq__` method of the `Path` class, which now only compares against other `Path` objects but doesn't handle the case when comparing with a `TType` object.

This breaks backward compatibility with code that relies on equality comparisons between `Path` and `TType` objects.

## Environment

- glom version: latest
- Python version: 3.10
- Operating system: Linux
