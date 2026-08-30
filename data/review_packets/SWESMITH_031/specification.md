# Variable interpolation in dotenv fails when referencing variables defined later in the file

## Description

I've found an issue with variable interpolation in dotenv. When a variable references another variable that is defined later in the file, the interpolation doesn't work correctly.

For example, with this .env file:
```
a=b
c=${a}
d=e
c=${d}
```

When loading this file with interpolation enabled, the variable `c` should be updated to the value of `d` (which is "e"), but instead it's not being interpolated correctly.

## Steps to reproduce

1. Create a .env file with the following content:
```
a=b
c=${a}
d=e
c=${d}
```

2. Load the file with interpolation enabled:
```python
import dotenv
result = dotenv.dotenv_values(".env", interpolate=True)
print(result)
```

## Expected behavior
The result should be:
```
{'a': 'b', 'c': 'e', 'd': 'e'}
```

## Actual behavior
The variable `c` is not correctly updated to the value of `d`.

This seems to be an issue with how variables are resolved during interpolation when a variable is redefined and references another variable that appears later in the file.
