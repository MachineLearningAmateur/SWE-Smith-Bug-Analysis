# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (9):

  tests/pixels/test_utils.py::TestGetExpectedLength::test_length_ybr_422[shape14-8-length14]
  tests/pixels/test_utils.py::TestGetExpectedLength::test_length_ybr_422[shape19-16-length19]
  tests/pixels/test_utils.py::TestGetExpectedLength::test_length_ybr_422[shape24-32-length24]
  tests/pixels/test_utils.py::TestGetExpectedLength::test_length_ybr_422[shape39-8-length39]
  tests/pixels/test_utils.py::TestGetExpectedLength::test_length_ybr_422[shape42-16-length42]
  tests/pixels/test_utils.py::TestGetExpectedLength::test_length_ybr_422[shape45-32-length45]
  tests/pixels/test_utils.py::TestGetExpectedLength::test_length_ybr_422[shape57-8-length57]
  tests/pixels/test_utils.py::TestGetExpectedLength::test_length_ybr_422[shape60-16-length60]
  tests/pixels/test_utils.py::TestGetExpectedLength::test_length_ybr_422[shape63-32-length63]

Tests passing in both states: 2320
