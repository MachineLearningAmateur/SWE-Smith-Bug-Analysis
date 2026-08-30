# Missing `inspect` and `inspect_err` methods in Result class

## Description

The `inspect` and `inspect_err` methods are missing from both `Ok` and `Err` classes. These methods are supposed to allow calling a function with the contained value while returning the original result, but they're not available anymore.

When trying to use these methods, I get an AttributeError:
```
AttributeError: 'Ok' object has no attribute 'inspect'
```

## Reproductive example
```python
from result import Ok, Err

def test_inspect():
    values = []
    
    # This should call the function with the value 5 and append it to values
    # while returning the original Ok(5)
    result = Ok(5).inspect(lambda x: values.append(x))
    
    # But instead it raises:
    # AttributeError: 'Ok' object has no attribute 'inspect'
    
    # Similarly for inspect_err
    errors = []
    result = Err("error").inspect_err(lambda e: errors.append(e))
    # AttributeError: 'Err' object has no attribute 'inspect_err'
```

The expected behavior is that:
1. `inspect` should call the provided function with the contained value if it's an `Ok` and return the original result
2. `inspect_err` should call the provided function with the contained error if it's an `Err` and return the original result

These methods are useful for side effects like logging or debugging without breaking the result chain.

## Environment details
Python 3.10.15
