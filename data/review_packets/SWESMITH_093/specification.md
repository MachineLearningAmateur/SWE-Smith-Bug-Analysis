Parameter content schema references not being resolved in OpenAPI v3

I noticed an issue with the Components class in apispec when working with OpenAPI v3 specifications. When a parameter has content with a schema reference, the reference is not being resolved properly.

Here's a simple example that demonstrates the issue:

```python
from apispec import APISpec

# Create a spec
spec = APISpec(
    title="Pets API",
    version="1.0.0",
    openapi_version="3.0.0"
)

# Define a schema
spec.components.schema("PetSchema", {"type": "object", "properties": {"name": {"type": "string"}}})

# Define a parameter with content that references the schema
parameter = {'content': {'application/json': {'schema': 'PetSchema'}}}
spec.components.parameter('pet_param', 'path', parameter)

# The schema reference in the parameter's content is not being resolved
print(spec.to_dict()['components']['parameters']['pet_param'])
```

Expected behavior:
The schema reference in the parameter's content should be resolved to a proper reference object like:
```
{'content': {'application/json': {'schema': {'$ref': '#/components/schemas/PetSchema'}}}}
```

Actual behavior:
The schema reference remains as a string and is not converted to a proper reference object:
```
{'content': {'application/json': {'schema': 'PetSchema'}}}
```

This issue only affects OpenAPI v3 specifications since parameter content is specific to OpenAPI v3+.
