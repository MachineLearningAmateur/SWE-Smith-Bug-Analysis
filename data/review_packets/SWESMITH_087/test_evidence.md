# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (26):

  tests/test_formparsers.py::test_max_part_size_exceeds_limit[asyncio-app-expectation0]
  tests/test_formparsers.py::test_max_part_size_exceeds_limit[asyncio-app1-expectation1]
  tests/test_formparsers.py::test_max_part_size_exceeds_limit[trio-app-expectation0]
  tests/test_formparsers.py::test_max_part_size_exceeds_limit[trio-app1-expectation1]
  tests/test_formparsers.py::test_multi_items[asyncio]
  tests/test_formparsers.py::test_multi_items[trio]
  tests/test_formparsers.py::test_multipart_multi_field_app_reads_body[asyncio]
  tests/test_formparsers.py::test_multipart_multi_field_app_reads_body[trio]
  tests/test_formparsers.py::test_multipart_request_data[asyncio]
  tests/test_formparsers.py::test_multipart_request_data[trio]
  tests/test_formparsers.py::test_multipart_request_files[asyncio]
  tests/test_formparsers.py::test_multipart_request_files[trio]
  tests/test_formparsers.py::test_multipart_request_files_with_content_type[asyncio]
  tests/test_formparsers.py::test_multipart_request_files_with_content_type[trio]
  tests/test_formparsers.py::test_multipart_request_mixed_files_and_data[asyncio]
  tests/test_formparsers.py::test_multipart_request_mixed_files_and_data[trio]
  tests/test_formparsers.py::test_multipart_request_multiple_files[asyncio]
  tests/test_formparsers.py::test_multipart_request_multiple_files[trio]
  tests/test_formparsers.py::test_multipart_request_multiple_files_with_headers[asyncio]
  tests/test_formparsers.py::test_multipart_request_multiple_files_with_headers[trio]
  ... and 6 more

Tests passing in both states: 815
