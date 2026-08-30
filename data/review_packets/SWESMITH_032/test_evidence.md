# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (2):

  ../dev/tests/test_sockets.py::TestParseAddress::test_port_zero_raises_value_error
  ../dev/tests/test_sockets.py::TestParseAddress::test_too_many_colons_raises_value_error

Tests passing in both states: 120
