# Maintainability Index (MI) calculation is incorrect

## Bug description

I noticed that the Maintainability Index calculation in radon is producing incorrect values. The formula seems to have been changed recently, and it's now giving different results than expected.

## Steps to reproduce

Here's a simple example that demonstrates the issue:

```python
from radon.metrics import mi_compute

# Test with some sample values
halstead_volume = 100
complexity = 10
sloc = 50
comments = 20

# Calculate MI
result = mi_compute(halstead_volume, complexity, sloc, comments)
print(f"Calculated MI: {result}")
# The result is different from what it should be
```

## Expected behavior

The MI calculation should follow the standard formula:
171 - 5.2 * ln(HV) - 0.23 * CC - 16.2 * ln(SLOC) + 50 * sin(sqrt(2.46 * comments))

And then normalize the result to a 0-100 scale.

## Actual behavior

The calculation seems to be using a different formula, particularly in how it handles the comments contribution. The current implementation is using `2.4 * comments / 100` inside the square root, which is not correct according to the standard formula.

## Radon version

```
radon 6.0.1
```

## Additional notes

I think the issue is in the `mi_compute` function in `radon/metrics.py`. The comments scaling factor should be `2.46 * comments` rather than `2.4 * comments / 100`, and the sine function should be applied to the radians of this value, not its square root.
