# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (2):

  tests/test_hash.py::TestOtherHashFuncs::test_combine_hashes_lists[items0-pre-pre583852d84b3482edf53408b64724a37289d7af458c44bb989a8abbffe24d2d2b]
  tests/test_hash.py::TestOtherHashFuncs::test_combine_hashes_lists[items1-pre-pre583852d84b3482edf53408b64724a37289d7af458c44bb989a8abbffe24d2d2b]

Tests passing in both states: 917
