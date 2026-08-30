# Nobara Linux not recognized as a distribution that uses DNF package manager

### What happened?

When using Conan on Nobara Linux, the system package manager tool is not correctly detected. Nobara Linux uses DNF as its package manager, but Conan doesn't recognize it as a supported distribution for DNF.

### What did you expect to happen?

Conan should recognize Nobara Linux as a distribution that uses DNF package manager, similar to how it recognizes Fedora, RHEL, CentOS, and Mageia.

### Minimal Complete Verifiable Example

```python
from conan.tools.system.package_manager import _SystemPackageManagerTool
from conan import ConanFile

class TestConanFile(ConanFile):
    pass

# Set up environment to simulate Nobara Linux
import platform
import distro

# Mock platform and distro
platform.system = lambda: 'Linux'
distro.id = lambda: 'nobara'

# Try to get the default package manager
conanfile = TestConanFile()
manager = _SystemPackageManagerTool(conanfile)
print(f"Default package manager for Nobara: {manager.get_default_tool()}")
# This will fail because Nobara is not in the list of distributions that use DNF
```

When running this code, it fails to identify DNF as the package manager for Nobara Linux.

### Anything else we need to know?

Nobara Linux is a Fedora-based distribution that uses DNF as its package manager. It should be included in the list of distributions that use DNF, alongside Fedora, RHEL, CentOS, and Mageia.

### Environment

- Conan version: latest
- OS: Nobara Linux (Fedora-based)
