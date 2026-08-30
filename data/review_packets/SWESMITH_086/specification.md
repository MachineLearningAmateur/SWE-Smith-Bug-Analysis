# Safety scan fails to find dependencies in certain file types

## Description

I noticed an issue when using the safety scan command on a project with various dependency files. The scan doesn't properly detect dependencies from certain file types that used to work in previous versions.

When running a scan on a project that contains requirements.txt, poetry.lock, pipenv.lock, or pyproject.toml files, the dependencies are not being detected correctly. This happens because the code is using different file type constants than what's expected.

For example, when I run:

```python
from safety.scan.ecosystems.python.dependencies import get_dependencies
from safety.scan.file import InspectableFile, FileType

# Create a test requirements file
f = InspectableFile("requirements.txt", FileType.REQUIREMENTS_TXT)
deps = get_dependencies(f)
print(deps)  # Returns empty list instead of the expected dependencies
```

The function is checking for `FileType.REQUIREMENTS` instead of `FileType.REQUIREMENTS_TXT`, and similarly for other file types. It's also checking for `FileType.VIRTUAL_ENV` instead of `FileType.VIRTUAL_ENVIRONMENT`.

This causes the scan to miss dependencies and report that everything is safe when it might not be, which is a serious security concern.

<END WRITING>
