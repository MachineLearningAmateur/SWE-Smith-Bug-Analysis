# time_difference() returns incorrect values when comparing track points

## Description

The `time_difference()` method in `GPXTrackPoint` is returning incorrect values when comparing two track points. The method is supposed to always return a positive time difference in seconds, but it's currently returning negative values in some cases.

## Steps to reproduce

```python
import gpxpy
from datetime import datetime, timedelta

# Create two track points with different times
point1 = gpxpy.gpx.GPXTrackPoint(latitude=45.0, longitude=45.0)
point1.time = datetime(2020, 1, 1, 12, 0, 0)

point2 = gpxpy.gpx.GPXTrackPoint(latitude=45.1, longitude=45.1)
point2.time = datetime(2020, 1, 1, 12, 0, 30)  # 30 seconds later

# Calculate time difference
diff1 = point1.time_difference(point2)  # Should be 30.0
diff2 = point2.time_difference(point1)  # Should also be 30.0, but returns -30.0

print(f"Time difference 1->2: {diff1}")
print(f"Time difference 2->1: {diff2}")
```

## Expected behavior

Both `diff1` and `diff2` should return `30.0` (the absolute time difference in seconds).

## Actual behavior

`diff1` returns `30.0` but `diff2` returns `-30.0` (a negative value).

This causes issues when calculating speeds or when using the time difference for other calculations that expect positive values.
