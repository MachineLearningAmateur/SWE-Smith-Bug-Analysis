# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (6):

  tests/test_duration.py::test_format
  tests/test_duration.py::test_format_parse[-P1DT2H3M4S-expectation24-P%P-None]
  tests/test_duration.py::test_format_parse[-P2.2W-expectation12-P%P--P15DT9H36M]
  tests/test_duration.py::test_format_parse[-P2W-expectation11-P%p-None]
  tests/test_duration.py::test_format_parse[-P2Y-expectation22-P%P-None]
  tests/test_duration.py::test_format_parse[-P3Y6M4DT12H30M5S-expectation23-P%P-None]

Tests passing in both states: 272
