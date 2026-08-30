# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (105):

  tests/test_hydra.py::TestVariousRuns::test_command_line_interpolations_evaluated_lazily[cmd_base0]
  tests/test_hydra.py::TestVariousRuns::test_multirun_config_overrides_evaluated_lazily[cmd_base0]
  tests/test_hydra.py::TestVariousRuns::test_multirun_defaults_override[cmd_base0]
  tests/test_hydra.py::TestVariousRuns::test_run_pass_list[cmd_base0]
  tests/test_hydra.py::TestVariousRuns::test_run_with_missing_default[run-cmd_base0]
  tests/test_hydra.py::TestVariousRuns::test_run_with_missing_default[sweep-cmd_base0]
  tests/test_hydra.py::test_app_with_error_exception_sanitized
  tests/test_hydra.py::test_app_with_unicode_config
  tests/test_hydra.py::test_cfg[--cfg=all-expected_keys0-False]
  tests/test_hydra.py::test_cfg[--cfg=all-expected_keys0-True]
  tests/test_hydra.py::test_cfg[--cfg=hydra-expected_keys1-False]
  tests/test_hydra.py::test_cfg[--cfg=hydra-expected_keys1-True]
  tests/test_hydra.py::test_cfg[--cfg=job-expected_keys2-False]
  tests/test_hydra.py::test_cfg[--cfg=job-expected_keys2-True]
  tests/test_hydra.py::test_cfg_resolve_interpolation[cfg]
  tests/test_hydra.py::test_cfg_resolve_interpolation[resolve]
  tests/test_hydra.py::test_cfg_resolve_interpolation[resolve_hydra_config]
  tests/test_hydra.py::test_cfg_with_package[no-package-False]
  tests/test_hydra.py::test_cfg_with_package[no-package-True]
  tests/test_hydra.py::test_cfg_with_package[package=_global_-False]
  ... and 85 more

Tests passing in both states: 44
