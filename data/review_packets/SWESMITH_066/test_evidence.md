# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (290):

  tests/oauth2/rfc6749/endpoints/test_client_authentication.py::ClientAuthenticationTest::test_basicauth_backend
  tests/oauth2/rfc6749/endpoints/test_client_authentication.py::ClientAuthenticationTest::test_basicauth_legacy
  tests/oauth2/rfc6749/endpoints/test_client_authentication.py::ClientAuthenticationTest::test_basicauth_web
  tests/oauth2/rfc6749/endpoints/test_client_authentication.py::ClientAuthenticationTest::test_client_id_authentication
  tests/oauth2/rfc6749/endpoints/test_client_authentication.py::ClientAuthenticationTest::test_custom_authentication
  tests/oauth2/rfc6749/endpoints/test_credentials_preservation.py::PreservationTest::test_default_uri
  tests/oauth2/rfc6749/endpoints/test_credentials_preservation.py::PreservationTest::test_default_uri_in_token
  tests/oauth2/rfc6749/endpoints/test_credentials_preservation.py::PreservationTest::test_invalid_redirect_uri
  tests/oauth2/rfc6749/endpoints/test_credentials_preservation.py::PreservationTest::test_redirect_uri_preservation
  tests/oauth2/rfc6749/endpoints/test_credentials_preservation.py::PreservationTest::test_state_preservation
  tests/oauth2/rfc6749/endpoints/test_error_responses.py::ErrorResponseTest::test_access_denied
  tests/oauth2/rfc6749/endpoints/test_error_responses.py::ErrorResponseTest::test_access_denied_no_default_redirecturi
  tests/oauth2/rfc6749/endpoints/test_error_responses.py::ErrorResponseTest::test_empty_parameter
  tests/oauth2/rfc6749/endpoints/test_error_responses.py::ErrorResponseTest::test_invalid_client
  tests/oauth2/rfc6749/endpoints/test_error_responses.py::ErrorResponseTest::test_invalid_client_id
  tests/oauth2/rfc6749/endpoints/test_error_responses.py::ErrorResponseTest::test_invalid_default_redirect_uri
  tests/oauth2/rfc6749/endpoints/test_error_responses.py::ErrorResponseTest::test_invalid_grant
  tests/oauth2/rfc6749/endpoints/test_error_responses.py::ErrorResponseTest::test_invalid_redirect_uri
  tests/oauth2/rfc6749/endpoints/test_error_responses.py::ErrorResponseTest::test_invalid_request
  tests/oauth2/rfc6749/endpoints/test_error_responses.py::ErrorResponseTest::test_invalid_request_duplicate_params
  ... and 270 more

Tests passing in both states: 383
