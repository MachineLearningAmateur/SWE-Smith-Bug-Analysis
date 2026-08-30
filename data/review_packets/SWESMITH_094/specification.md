# Engine kwargs not respected when reading Excel files with openpyxl engine

## Description

When using the openpyxl engine to read Excel files, engine_kwargs are not properly respected when they conflict with default parameters. The default parameters (read_only, data_only, keep_links) always override any user-provided values.

## Example

```python
import pandas as pd
import io

# Create a simple Excel file
buffer = io.BytesIO()
df = pd.DataFrame({'A': [1, 2, 3]})
df.to_excel(buffer)
buffer.seek(0)

# Try to read with custom engine_kwargs
# This should use data_only=False, but actually uses data_only=True
df_read = pd.read_excel(
    buffer, 
    engine='openpyxl',
    engine_kwargs={'data_only': False}
)

# The same issue happens with read_only and keep_links parameters
```

## Expected behavior

When a user provides engine_kwargs that include 'read_only', 'data_only', or 'keep_links', these values should override the defaults.

## Actual behavior

The default values (read_only=True, data_only=True, keep_links=False) are always used, regardless of what is specified in engine_kwargs.

This is particularly problematic when users need to read Excel files with formulas and want to get the formula text instead of the calculated values (which requires data_only=False).
