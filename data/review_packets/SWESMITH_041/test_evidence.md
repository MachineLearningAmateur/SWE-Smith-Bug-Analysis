# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (4):

  test/core/linter/linted_file_test.py::test__linted_file__build_up_fixed_source_string[source_slices0-source_patches0-a-a]
  test/core/linter/linted_file_test.py::test__linted_file__build_up_fixed_source_string[source_slices1-source_patches1-abc-adc]
  test/core/linter/linted_file_test.py::test__linted_file__build_up_fixed_source_string[source_slices2-source_patches2-ac-abc]
  test/core/linter/linted_file_test.py::test__linted_file__build_up_fixed_source_string[source_slices3-source_patches3-abc-ac]

Tests passing in both states: 6
