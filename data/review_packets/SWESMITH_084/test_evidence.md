# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (6):

  tests/oauth1/rfc5849/endpoints/test_access_token.py::AccessTokenEndpointTest::test_check_request_token
  tests/oauth1/rfc5849/endpoints/test_access_token.py::AccessTokenEndpointTest::test_valid_request
  tests/oauth1/rfc5849/endpoints/test_access_token.py::AccessTokenEndpointTest::test_validate_client_key
  tests/oauth1/rfc5849/endpoints/test_access_token.py::AccessTokenEndpointTest::test_validate_request_token
  tests/oauth1/rfc5849/endpoints/test_access_token.py::AccessTokenEndpointTest::test_validate_signature
  tests/oauth1/rfc5849/endpoints/test_access_token.py::AccessTokenEndpointTest::test_validate_verifier

Tests passing in both states: 667
