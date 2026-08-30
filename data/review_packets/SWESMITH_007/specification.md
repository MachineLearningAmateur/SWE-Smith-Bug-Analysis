# Environment variable expansion not working correctly

## Description

Currently, the environment variable expansion functionality in the `environs` package is not working as expected. There are issues with the following scenarios:

1. Full variable expansion using the `{{VARIABLE}}` syntax doesn't properly substitute values
2. Default values in expansions (like `{{VARIABLE:-default}}`) are not being processed correctly
3. Escaped dollar signs (`\$`) in environment variables are not being handled properly

For example, if I have:

```python
import os
from environs import Env

os.environ["SOURCE_VAR"] = "source_value"
os.environ["TARGET_VAR"] = "{{SOURCE_VAR}}"

env = Env(expand_vars=True)
value = env("TARGET_VAR")
# Expected: "source_value"
# Actual: something else
```

Similarly, when using default values:

```python
import os
from environs import Env

os.environ["TARGET_VAR"] = "{{MISSING_VAR:-default_value}}"

env = Env(expand_vars=True)
value = env("TARGET_VAR")
# Expected: "default_value"
# Actual: not working correctly
```

And escaped dollar signs are not being processed:

```python
import os
from environs import Env

os.environ["ESCAPED_VAR"] = "Value with \\$dollar"

env = Env(expand_vars=True)
value = env("ESCAPED_VAR")
# Expected: "Value with $dollar"
# Actual: not working correctly
```

It looks like the variable expansion logic in `_get_from_environ` method has been simplified, which has broken these features.
