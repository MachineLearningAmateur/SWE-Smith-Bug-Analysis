**Unexpected Hashing Behavior in `combine_hashes_lists` Function**

**Describe the bug**
The `combine_hashes_lists` function is not producing the expected hash values when provided with certain inputs. This seems to affect the consistency of the hash results, which is critical for applications relying on predictable hash outputs.

**To Reproduce**
Steps to reproduce the behavior:
1. Use the `combine_hashes_lists` function with the following inputs:
   ```python
   items = [<your_items_here>]
   prefix = "<your_prefix_here>"
   result = combine_hashes_lists(items, prefix)
   print(result)
   ```
2. Observe the output hash value.

**Expected behavior**
The function should return a consistent hash value for the same set of inputs, matching the expected hash output.

**Environment info**
- OS: Linux
- Python version: 3.10.16
- DeepDiff version: [version_number]

**Additional context**
This issue was observed after recent changes to the hashing logic. It is crucial to ensure that the hash function maintains its integrity across different versions.
