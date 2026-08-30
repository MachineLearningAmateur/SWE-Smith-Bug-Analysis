# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (5060):

  tests/contrast/test_contrasts.py::test_contrasts
  tests/examplefiles/abnf/abnf_example1.abnf::
  tests/examplefiles/abnf/abnf_example2.abnf::
  tests/examplefiles/ada/test.adb::
  tests/examplefiles/ada/test_ada2022.adb::
  tests/examplefiles/ada/test_ada_aspects.ads::
  tests/examplefiles/adl/test.adls::
  tests/examplefiles/adl/test_basic.adls::
  tests/examplefiles/agda/test.agda::
  tests/examplefiles/aheui/durexmania.aheui::
  tests/examplefiles/aheui/fibonacci.tokigun.aheui::
  tests/examplefiles/aheui/hello-world.puzzlet.aheui::
  tests/examplefiles/ahk/demo.ahk::
  tests/examplefiles/alloy/example.als::
  tests/examplefiles/amdgpu/amdgpu.isa::
  tests/examplefiles/antlr/antlr_ANTLRv3.g::
  tests/examplefiles/antlr/antlr_throws::
  tests/examplefiles/apacheconf/apache2.conf::
  tests/examplefiles/apdl/example1apdl.ans::
  tests/examplefiles/apdl/example2apdl.ans::
  ... and 5040 more

Tests passing in both states: 0
