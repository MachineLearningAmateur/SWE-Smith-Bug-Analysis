Inconsistent String Representation for X509Extension

Description

I've encountered an issue with the string representation of `X509Extension` instances. When attempting to convert an `X509Extension` object to a string, the output does not match the expected format. This seems to occur specifically when dealing with certain types of extensions.

To reproduce the issue, consider the following example:

```python
from OpenSSL.crypto import X509Extension

# Create an X509Extension instance
extension = X509Extension(b'basicConstraints', True, b'CA:false')

# Attempt to get the string representation
print(str(extension))  # Expected: 'CA:FALSE', but the output is different
```

The expected output should be `'CA:FALSE'`, but the actual output deviates from this. This inconsistency can lead to confusion when handling X509 extensions, especially in scenarios where the string representation is crucial for logging or debugging purposes.

It would be great to have this behavior aligned with the expected output to ensure consistency across different types of extensions.
