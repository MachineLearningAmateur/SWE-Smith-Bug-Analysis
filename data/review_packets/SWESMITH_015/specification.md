[BUG] APISpec Initialization Fails with Plugin Handling

#### Description
It seems there's an issue with the initialization of the `APISpec` class when handling plugins. The recent changes in the constructor might have introduced a problem where the plugins are not being initialized correctly, leading to failures in various components that rely on them.

#### Steps to Reproduce
1. Create an instance of `APISpec` with a valid title, version, and openapi_version.
2. Pass a list of plugin instances to the constructor.
3. Attempt to access components that depend on these plugins.

Example:
```python
from apispec import APISpec
from some_plugin_module import SomePlugin

spec = APISpec(
    title="Sample API",
    version="1.0.0",
    openapi_version="3.0.0",
    plugins=[SomePlugin()]
)

# Attempt to use a component that relies on the plugin
component = spec.components.get("some_component")
```

#### Expected Behavior
The `APISpec` instance should initialize correctly, and components should be accessible without errors.

#### Actual Behavior
An error occurs when trying to access components that depend on the plugins, indicating that the plugins might not be initialized properly.

#### Error Message
The error message suggests that the components cannot be accessed due to an issue with plugin initialization.

#### Additional Information
This issue seems to affect multiple tests related to component resolution and field validation, indicating a broader impact on the functionality that relies on plugins.
