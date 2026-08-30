[Bug]: Decorator docstring not properly set in pass_meta_key function

### Description

I'm having an issue with the `pass_meta_key` decorator in Click. The docstring for the decorator is not being properly set or accessed. When I try to access the docstring of a decorator created with `pass_meta_key`, it doesn't contain the expected text.

### Reproduction

```python
from click.decorators import pass_meta_key

# Create a decorator with default doc_description
pass_value = pass_meta_key('value')
print(pass_value.__doc__)  # Should contain "the 'value' key from :attr:`click.Context.meta`"

# Create a decorator with custom doc_description
pass_custom = pass_meta_key('value', doc_description='the test value')
print(pass_custom.__doc__)  # Should contain "passes the test value"
```

### Actual outcome

The docstring of the decorator doesn't contain the expected text. When I try to access `pass_value.__doc__`, it doesn't include the expected reference to `:attr:`click.Context.meta``.

### Expected outcome

The docstring of the decorator should include the proper description:
- For default case: "Decorator that passes the 'value' key from :attr:`click.Context.meta` as the first argument to the decorated function."
- For custom description: "Decorator that passes the test value as the first argument to the decorated function."

This is important for documentation generation and IDE hints.

### Additional information

I noticed that the docstring is being set on the inner function (`new_func`) but not on the decorator function itself. This seems to be causing the issue.
