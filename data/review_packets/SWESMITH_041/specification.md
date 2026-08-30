# Bug: Fixed source string not correctly built when applying patches

## Description

I've found an issue with the `_build_up_fixed_source_string` method in `LintedFile`. The method is not correctly applying patches to the source file slices.

It's easier to explain with a simple example:

```python
# Example 1: Inserting content
source_slices = [slice(0, 1), slice(1, 1), slice(1, 2)]
source_patches = [FixPatch(slice(1, 1), 'b', '', slice(1, 1), '', '')]
raw_source_string = 'ac'
expected_result = 'abc'  # Should insert 'b' at position 1
actual_result = 'ac'     # The patch is not being applied

# Example 2: Replacing content
source_slices = [slice(0, 1), slice(1, 2), slice(2, 3)]
source_patches = [FixPatch(slice(1, 2), 'd', '', slice(1, 2), 'b', 'b')]
raw_source_string = 'abc'
expected_result = 'adc'  # Should replace 'b' with 'd'
actual_result = 'abc'    # The patch is not being applied
```

The issue appears to be in the lookup mechanism for patches. When iterating through the slices, the method is not correctly identifying which patches should be applied to which slices.

## Steps to reproduce

```python
from sqlfluff.core.linter.linted_file import LintedFile, FixPatch

# Test case 1: Simple replacement
source_slices = [slice(0, 1), slice(1, 2), slice(2, 3)]
source_patches = [FixPatch(slice(1, 2), 'd', '', slice(1, 2), 'b', 'b')]
raw_source_string = 'abc'
result = LintedFile._build_up_fixed_source_string(source_slices, source_patches, raw_source_string)
print(f"Expected: 'adc', Got: '{result}'")

# Test case 2: Insertion
source_slices = [slice(0, 1), slice(1, 1), slice(1, 2)]
source_patches = [FixPatch(slice(1, 1), 'b', '', slice(1, 1), '', '')]
raw_source_string = 'ac'
result = LintedFile._build_up_fixed_source_string(source_slices, source_patches, raw_source_string)
print(f"Expected: 'abc', Got: '{result}'")
```

This issue affects the auto-fix functionality, causing patches to not be applied correctly when fixing SQL files.
