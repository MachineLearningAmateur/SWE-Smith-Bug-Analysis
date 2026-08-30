wide_to_long fails with pyarrow string columns

```python
>>> import pandas as pd
>>> import pyarrow as pa
>>> df = pd.DataFrame({
...     "id": [1, 2],
...     "foo_1": ["a", "b"],
...     "foo_2": ["c", "d"]
... })
>>> df = df.astype({"foo_1": "string[pyarrow]", "foo_2": "string[pyarrow]"})
>>> pd.wide_to_long(df, stubnames=["foo"], i="id", j="time")
```

This fails with:

```
TypeError: expected string or bytes-like object, got 're.Pattern'
```

The error happens when using pyarrow string columns with wide_to_long. It works fine with regular object or python string dtypes, but fails specifically with pyarrow string columns.

I've verified this happens with pandas 2.1.0 and above. The issue seems to be related to how string pattern matching is handled with pyarrow string columns.
