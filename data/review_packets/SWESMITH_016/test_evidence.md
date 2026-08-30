# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (8):

  test/test_normalizer_issues_files.py::test_normalizer_issue[E10.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E101.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E12_first.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E12_not_first.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E12_not_second.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E12_second.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E12_third.py]
  test/test_normalizer_issues_files.py::test_normalizer_issue[E50.py]

Tests passing in both states: 792
