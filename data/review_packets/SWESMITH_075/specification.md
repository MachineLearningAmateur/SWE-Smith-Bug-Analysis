# CSS classes for token types not properly generated in HtmlFormatter

I found an issue with the CSS class generation in the HtmlFormatter. When using custom token types with the `-F` option, the CSS classes are not properly generated.

## Reproduction

Here's a simple example that demonstrates the issue:

```python
from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import HtmlFormatter
from pygments.token import Name

# Create a custom token type
custom_token = Name.Blubb

# Create a formatter with a custom token type
formatter = HtmlFormatter()

# Check the CSS class for the custom token type
css_class = formatter._get_css_classes(custom_token)
print(f"CSS class for custom token: {css_class}")
```

Expected output should include both the parent token type class and the specific token type class, something like:
```
CSS class for custom token: n n-Blubb
```

But instead, it only returns the specific token type class without the parent class:
```
CSS class for custom token: Blubb
```

This also affects the command line usage with the `-F` option when trying to highlight specific token types.

For example, when running:
```
pygmentize -Fhighlight:tokentype=Name.Blubb,names=myfile.py -fhtml myfile.py
```

The generated HTML doesn't include the proper CSS class hierarchy for the token type.

This behavior breaks backward compatibility with existing stylesheets that rely on the hierarchical CSS class structure.
