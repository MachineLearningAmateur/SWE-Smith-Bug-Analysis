# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (2):

  tests/test_distance.py::TestDeepDistance::test_get_numbers_distance[num11-num21-1-0.0049261083743842365]
  tests/test_distance.py::TestDeepDistance::test_get_numbers_distance[num12-num22-1-1]

Tests passing in both states: 917
