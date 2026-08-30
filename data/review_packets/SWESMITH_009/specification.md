### Description

It seems there's an issue with augmented assignment operations when dealing with different types. Specifically, when using the `+=` operator with objects of different types, the expected behavior is not being met. This is causing unexpected results or errors in certain scenarios.

### How to Reproduce

Here's a minimal example to illustrate the problem:

```python
class A:
    def __iadd__(self, other):
        return NotImplemented

class B:
    pass

a = A()
b = B()

# Attempting augmented assignment
a += b  # This should raise an error or handle the operation gracefully
```

### Expected Behavior

The operation should either be handled correctly by falling back to the appropriate method or raise a clear error indicating the operation is unsupported between the given types.

### Environment Details

- Python version: 3.10.16
- Operating System: Linux
- Additional context: The issue was observed after recent changes in the handling of augmented operations in the codebase.
