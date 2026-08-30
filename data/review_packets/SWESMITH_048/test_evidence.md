# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (2):

  tests/sphinx/test_docstring.py::TestProviderMethodDocstring::test_stringify_results
  tests/test_proxy.py::TestFakerProxyClass::test_seed_locale

Tests passing in both states: 2101
