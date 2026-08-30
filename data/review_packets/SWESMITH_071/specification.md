# Optional() with default value not working correctly

I'm trying to use the Optional schema with a default value, but it's not working as expected. When I try to validate a dictionary with an optional key that has a default value, the default value is not being applied when the key is missing.

Consider the following example:

```python
from schema import Schema, Optional

schema = Schema({
    Optional('a', default=1): 11, 
    Optional('b', default=2): 22
})

result = schema.validate({'a': 11})
print(result)  # Expected: {'a': 11, 'b': 2}, but getting {'a': 11} instead
```

The default value for 'b' is not being applied when the key is missing from the input dictionary.

Similarly, when using Optional with a Literal that has a description:

```python
from schema import Schema, Optional, Literal

schema = Schema({
    Optional(Literal('test1', description='A description here'), default={}): dict
})

result = schema.validate({})
print(result)  # Expected: {'test1': {}} but not getting the default value
```

This used to work in previous versions. It seems like the default value handling in Optional is broken.
