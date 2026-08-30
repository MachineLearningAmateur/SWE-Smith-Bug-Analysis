# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (2):

  test/core/linter/fix_test.py::test__fix__generate_source_patches[tree3-templated_file3-expected_result3]
  test/core/linter/fix_test.py::test__fix__generate_source_patches[tree4-templated_file4-expected_result4]

Tests passing in both states: 72
