# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (2):

  test/core/linter/linted_file_test.py::test__linted_file__slice_source_file_using_patches[source_patches0-source_only_slices0-a-expected_result0]
  test/core/linter/linted_file_test.py::test__linted_file__slice_source_file_using_patches[source_patches1-source_only_slices1-abc-expected_result1]

Tests passing in both states: 8
