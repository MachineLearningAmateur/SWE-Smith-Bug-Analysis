# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (6):

  pandas/tests/io/excel/test_openpyxl.py::test_engine_kwargs_append_data_only[False-=1+1]
  pandas/tests/io/excel/test_openpyxl.py::test_engine_kwargs_append_data_only[True-0]
  pandas/tests/io/excel/test_openpyxl.py::test_engine_kwargs_append_reader[False-data_only]
  pandas/tests/io/excel/test_openpyxl.py::test_engine_kwargs_append_reader[False-read_only]
  pandas/tests/io/excel/test_openpyxl.py::test_engine_kwargs_append_reader[True-data_only]
  pandas/tests/io/excel/test_openpyxl.py::test_engine_kwargs_append_reader[True-read_only]

Tests passing in both states: 45
