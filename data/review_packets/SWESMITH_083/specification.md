Download function does not respect SSL verification configuration

**Description**:

It seems that the `download` function is not respecting the SSL verification configuration set in the Conan configuration. This issue arises when attempting to download files with SSL verification toggled on or off.

**What happened**:

When using the `download` function with the `verify` parameter set to either `True` or `False`, the expected behavior is that the SSL verification should follow the specified configuration. However, the function does not adhere to this setting, leading to unexpected behavior during downloads.

**What you expected to happen**:

The `download` function should respect the SSL verification configuration as specified in the Conan settings. Specifically, when `verify=True`, SSL verification should be enforced, and when `verify=False`, it should be bypassed.

**Steps to Reproduce**:

1. Create a Conan package with a `source` method that uses the `download` function with different `verify` settings.
2. Run the package creation with the configuration `tools.files.download:verify=True`.
3. Observe that the SSL verification does not behave as expected.
4. Repeat the process with `tools.files.download:verify=False` and note the inconsistency.

**Minimal Complete Verifiable Example**:

```python
from conan import ConanFile
from conan.tools.files import download

class Pkg(ConanFile):
    name = "pkg"
    version = "1.0"

    def source(self):
        download(self, "http://verify.true", "", verify=True)
        download(self, "http://verify.false", "", verify=False)
```

**Environment**:

- Conan version: [Your Conan version]
- Python version: [Your Python version]
- Operating System: [Your OS]

**Anything else we need to know?**:

This issue might be related to the recent changes in the `download` function implementation. It would be helpful to review the handling of the `verify` parameter in the function.
