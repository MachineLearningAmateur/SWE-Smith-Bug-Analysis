# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (14):

  test/test_cache.py::test_permission_error
  test/test_diff_parser.py::test_backslash_with_imports
  test/test_diff_parser.py::test_paren_before_docstring
  test/test_file_python_errors.py::test_on_itself[3.10]
  test/test_file_python_errors.py::test_on_itself[3.6]
  test/test_file_python_errors.py::test_on_itself[3.7]
  test/test_file_python_errors.py::test_on_itself[3.8]
  test/test_file_python_errors.py::test_on_itself[3.9]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E27.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E30not.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E40.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[allowed_syntax.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[python.py]
  test/test_python_errors.py::test_future_import_first

Tests passing in both states: 786
