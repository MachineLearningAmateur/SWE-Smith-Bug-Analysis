# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (2329):

  tests/pixels/test_common.py::TestCoderBase::test_add_plugin
  tests/pixels/test_common.py::TestCoderBase::test_add_plugin_function_missing
  tests/pixels/test_common.py::TestCoderBase::test_add_plugin_module_import_failure
  tests/pixels/test_common.py::TestCoderBase::test_add_plugin_unavailable
  tests/pixels/test_common.py::TestCoderBase::test_init
  tests/pixels/test_common.py::TestCoderBase::test_missing_dependencies
  tests/pixels/test_common.py::TestCoderBase::test_remove_plugin
  tests/pixels/test_common.py::TestCoderBase::test_validate_plugins
  tests/pixels/test_common.py::TestRunnerBase::test_del_option
  tests/pixels/test_common.py::TestRunnerBase::test_frame_length[shape0-1-length0]
  tests/pixels/test_common.py::TestRunnerBase::test_frame_length[shape1-1-length1]
  tests/pixels/test_common.py::TestRunnerBase::test_frame_length[shape10-8-length10]
  tests/pixels/test_common.py::TestRunnerBase::test_frame_length[shape11-8-length11]
  tests/pixels/test_common.py::TestRunnerBase::test_frame_length[shape12-8-length12]
  tests/pixels/test_common.py::TestRunnerBase::test_frame_length[shape13-8-length13]
  tests/pixels/test_common.py::TestRunnerBase::test_frame_length[shape14-8-length14]
  tests/pixels/test_common.py::TestRunnerBase::test_frame_length[shape15-16-length15]
  tests/pixels/test_common.py::TestRunnerBase::test_frame_length[shape16-16-length16]
  tests/pixels/test_common.py::TestRunnerBase::test_frame_length[shape17-16-length17]
  tests/pixels/test_common.py::TestRunnerBase::test_frame_length[shape18-16-length18]
  ... and 2309 more

Tests passing in both states: 0
