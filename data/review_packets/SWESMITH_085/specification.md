### Description

It seems there's an issue with formatting negative durations using the `duration_isoformat` function. When attempting to format negative durations, the output does not include the expected negative sign, which leads to incorrect duration strings.

### How to Reproduce

To reproduce the issue, try formatting a negative duration using the `duration_isoformat` function. For example:

```python
from isodate import duration_isoformat, Duration

# Example negative duration
negative_duration = Duration(years=-1, months=-1)

# Attempt to format the negative duration
formatted_duration = duration_isoformat(negative_duration)
print(formatted_duration)
```

### Expected Behavior

The formatted duration string should include a negative sign, indicating the duration is negative. For instance, a duration of `-1 year, -1 month` should be formatted as `-P1Y1M`.

### Additional Context

This issue affects any negative duration values, leading to potentially misleading outputs when negative durations are involved.
