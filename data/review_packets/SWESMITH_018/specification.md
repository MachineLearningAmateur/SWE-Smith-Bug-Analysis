# Path matching fails with backslashes in Windows-style paths

## Description

I've discovered an issue with the `matches()` function in `build_helpers.py` that affects Windows-style paths. The function is failing to properly match patterns against strings that contain backslashes.

## What happened?

When trying to match patterns against Windows-style paths (with backslashes), the function returns `False` even when it should return `True`. This happens because the function no longer normalizes backslashes to forward slashes before performing the pattern matching.

## Reproduction

Here's a simple example that demonstrates the issue:

```python
from build_helpers.build_helpers import matches

# This works fine
assert matches(['^a/.*'], 'a/') == True

# This fails - should be True but returns False
assert matches(['^a/.*'], 'a\\') == False

# Another example that fails
assert matches(['^/foo/bar/.*'], '\\foo\\bar/blag') == False
```

## Expected behavior

The function should match patterns against strings regardless of whether the path separators are forward slashes or backslashes. This was working correctly before, as the function used to normalize backslashes to forward slashes with:

```python
string = string.replace("\\", "/")
```

Additionally, the change from `re.match()` to `re.search()` might be causing different behavior in how patterns are matched against the beginning of strings.

## Environment

- OS: Windows 10 (but affects any code that processes Windows-style paths)
- Python: 3.10

<END WRITING>
