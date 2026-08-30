# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (2):

  tests/brain/test_enum.py::EnumBrainTest::test_enum_sunder_names
  tests/brain/test_enum.py::EnumBrainTest::test_enum_with_ignore

Tests passing in both states: 1591
