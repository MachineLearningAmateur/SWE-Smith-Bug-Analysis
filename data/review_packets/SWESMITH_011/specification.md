# Host routes not included in schema generation

### Describe the bug

The schema generator doesn't include routes from `Host` instances when generating the OpenAPI schema. This means that any routes defined within a `Host` route are completely missing from the generated schema documentation.

### How to Reproduce

Create an application with routes defined within a `Host` instance:

```python
from starlette.applications import Starlette
from starlette.routing import Host, Route
from starlette.schemas import SchemaGenerator

async def endpoint(request):
    return {"message": "Hello World"}

routes = [
    Host("example.com", routes=[
        Route("/api/endpoint", endpoint, methods=["GET"])
    ])
]

app = Starlette(routes=routes)

# Generate schema
schema_generator = SchemaGenerator({"openapi": "3.0.0", "info": {"title": "API", "version": "1.0"}})
schema = schema_generator.get_schema(routes=app.routes)

# The schema will be missing the /api/endpoint route
print(schema)
```

### Expected behavior

Routes defined within a `Host` instance should be included in the generated schema, similar to how routes within a `Mount` instance are included.

### Your project

Starlette

### OS

Ubuntu 20.04

### Python version

3.9.7

### Additional context

The schema generator correctly handles routes within `Mount` instances, but it's ignoring routes within `Host` instances. This makes it impossible to document APIs that use domain-based routing.
