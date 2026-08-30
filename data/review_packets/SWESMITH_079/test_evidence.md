# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (23):

  pandas/tests/window/test_ewm.py::test_ew_empty_series[std]
  pandas/tests/window/test_ewm.py::test_ew_empty_series[var]
  pandas/tests/window/test_ewm.py::test_ew_min_periods[std-0]
  pandas/tests/window/test_ewm.py::test_ew_min_periods[std-1]
  pandas/tests/window/test_ewm.py::test_ew_min_periods[var-0]
  pandas/tests/window/test_ewm.py::test_ew_min_periods[var-1]
  pandas/tests/window/test_ewm.py::test_ewma_frame[std]
  pandas/tests/window/test_ewm.py::test_ewma_frame[var]
  pandas/tests/window/test_ewm.py::test_ewma_series[std]
  pandas/tests/window/test_ewm.py::test_ewma_series[var]
  pandas/tests/window/test_ewm.py::test_numeric_only_frame[std-False]
  pandas/tests/window/test_ewm.py::test_numeric_only_frame[std-True]
  pandas/tests/window/test_ewm.py::test_numeric_only_frame[var-False]
  pandas/tests/window/test_ewm.py::test_numeric_only_frame[var-True]
  pandas/tests/window/test_ewm.py::test_numeric_only_series[std-False-int]
  pandas/tests/window/test_ewm.py::test_numeric_only_series[std-False-object]
  pandas/tests/window/test_ewm.py::test_numeric_only_series[std-True-int]
  pandas/tests/window/test_ewm.py::test_numeric_only_series[var-False-int]
  pandas/tests/window/test_ewm.py::test_numeric_only_series[var-False-object]
  pandas/tests/window/test_ewm.py::test_numeric_only_series[var-True-int]
  ... and 3 more

Tests passing in both states: 286
