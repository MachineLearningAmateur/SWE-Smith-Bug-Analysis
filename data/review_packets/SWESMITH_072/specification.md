# Empty tuple assignment error message is incorrect

When trying to assign to an empty tuple in a bogus context, the error message is not what's expected.

For example, when running this code:

```python
() = 42
```

The error message is:
```
error: can't assign to ()
error: "int" object is not iterable
```

But the first error message should not appear. The only error should be `"int" object is not iterable`.

This happens because the code is checking for empty tuples and adding an additional error message, but this check is happening before the iterable check, which is the more appropriate error in this case.
