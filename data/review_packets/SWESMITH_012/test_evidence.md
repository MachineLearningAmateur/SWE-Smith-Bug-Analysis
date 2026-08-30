# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (3):

  test/test_cache.py::test_cache_last_used_update[True-False]
  test/test_cache.py::test_cache_last_used_update[True-True]
  test/test_cache.py::test_modulepickling_change_cache_dir

Tests passing in both states: 797
