# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (12):

  tests/test_cli.py::test_get_default_path
  tests/test_cli.py::test_get_existing_value
  tests/test_cli.py::test_get_not_a_file
  tests/test_cli.py::test_list[shell-x='a/nb/nc'-x='a/nb/nc'/n]
  tests/test_cli.py::test_list_not_a_file
  tests/test_cli.py::test_run
  tests/test_cli.py::test_run_with_existing_variable
  tests/test_cli.py::test_run_with_existing_variable_not_overridden
  tests/test_cli.py::test_run_with_none_value
  tests/test_cli.py::test_run_with_other_env
  tests/test_cli.py::test_unset_existing_value
  tests/test_cli.py::test_unset_non_existent_value

Tests passing in both states: 109
