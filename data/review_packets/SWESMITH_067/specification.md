[Bug]: StyleGuide.excluded() doesn't properly handle parent directory exclusions

### Bug summary

When using the StyleGuide API to check if a file is excluded, the current implementation doesn't properly handle parent directory exclusions. The `excluded()` method in the StyleGuide class doesn't correctly process the parent parameter when determining if a file should be excluded.

### Code for reproduction

```python
from flake8.api import legacy as api

# Create a style guide with exclusion patterns
style_guide = api.get_style_guide(exclude=['file*', '*/parent/*'])

# This works correctly
assert style_guide.excluded('file.py')

# This should exclude files in the 'parent' directory but doesn't work properly
assert style_guide.excluded('test.py', 'parent')
```

### Actual outcome

When checking if a file with a parent directory should be excluded, the current implementation doesn't correctly handle the parent parameter. This means that files that should be excluded based on parent directory patterns aren't being properly excluded.

### Expected outcome

Files should be properly excluded when they match exclusion patterns, including when those patterns match against the parent directory path combined with the filename.

### Additional information

The issue appears to be in the `excluded()` method in the `StyleGuide` class. The current implementation doesn't properly handle the parent parameter when determining if a file should be excluded based on patterns that would match the combined parent/filename path.

### Operating system

_No response_

### Python version

_No response_

### Installation

pip install flake8
