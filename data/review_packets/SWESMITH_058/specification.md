# Import error with Literal in TypeAdapter

**Describe the bug**
When using TypeAdapter with Literal types, I'm getting an import error. The issue is that Literal is being imported from the wrong module.

**To Reproduce**
Create a simple script that uses TypeAdapter with a Literal type:

```python
from pydantic import TypeAdapter
from typing import Literal

# Define a type with Literal
MyType = Literal["option1", "option2"]

# Try to create a TypeAdapter for this type
adapter = TypeAdapter(MyType)

# This will fail with an import error
```

**Expected behavior**
The code should work without any import errors, allowing TypeAdapter to properly handle Literal types.

**Environment info**
- Python version: 3.10
- Pydantic version: latest

**Additional context**
This seems to be related to how Literal is imported in the type_adapter.py file. The error occurs because there's a conflict between the Literal import from typing and typing_extensions.
