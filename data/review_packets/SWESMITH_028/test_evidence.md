# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (322):

  tests/middleware/test_base.py::test_app_middleware_argument[asyncio]
  tests/middleware/test_base.py::test_app_middleware_argument[trio]
  tests/middleware/test_base.py::test_contextvars[asyncio-CustomMiddlewareWithoutBaseHTTPMiddleware]
  tests/middleware/test_base.py::test_contextvars[trio-CustomMiddlewareWithoutBaseHTTPMiddleware]
  tests/middleware/test_base.py::test_custom_middleware[asyncio]
  tests/middleware/test_base.py::test_custom_middleware[trio]
  tests/middleware/test_base.py::test_do_not_block_on_background_tasks[asyncio]
  tests/middleware/test_base.py::test_do_not_block_on_background_tasks[trio]
  tests/middleware/test_base.py::test_fully_evaluated_response[asyncio]
  tests/middleware/test_base.py::test_fully_evaluated_response[trio]
  tests/middleware/test_base.py::test_multiple_middlewares_stacked_client_disconnected[asyncio]
  tests/middleware/test_base.py::test_multiple_middlewares_stacked_client_disconnected[trio]
  tests/middleware/test_base.py::test_pr_1519_comment_1236166180_example
  tests/middleware/test_base.py::test_read_request_body_in_app_after_middleware_calls_body[asyncio]
  tests/middleware/test_base.py::test_read_request_body_in_app_after_middleware_calls_body[trio]
  tests/middleware/test_base.py::test_read_request_body_in_app_after_middleware_calls_stream[asyncio]
  tests/middleware/test_base.py::test_read_request_body_in_app_after_middleware_calls_stream[trio]
  tests/middleware/test_base.py::test_read_request_body_in_dispatch_after_app_calls_body_with_middleware_calling_body_before_call_next[asyncio]
  tests/middleware/test_base.py::test_read_request_body_in_dispatch_after_app_calls_body_with_middleware_calling_body_before_call_next[trio]
  tests/middleware/test_base.py::test_read_request_stream_in_app_after_middleware_calls_body[asyncio]
  ... and 302 more

Tests passing in both states: 519
