# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (122):

  parso/__init__.py::parso
  test/test_file_python_errors.py::test_on_itself[3.10]
  test/test_file_python_errors.py::test_on_itself[3.6]
  test/test_file_python_errors.py::test_on_itself[3.7]
  test/test_file_python_errors.py::test_on_itself[3.8]
  test/test_file_python_errors.py::test_on_itself[3.9]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E10.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E101.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E11.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E12_first.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E12_not_first.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E12_not_second.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E12_second.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E12_third.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E20.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E21.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E22.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E23.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E25.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E26.py]
  ... and 102 more

Tests passing in both states: 678
