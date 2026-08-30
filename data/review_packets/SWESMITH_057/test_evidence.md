# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (60):

  tests/test_converter.py::TestColorSpace::test_do_rg
  tests/test_converter.py::TestPaintPath::test_paint_path_quadrilaterals
  tests/test_font_size.py::test_font_size
  tests/test_highlevel_extracttext.py::TestExtractPages::test_line_margin
  tests/test_highlevel_extracttext.py::TestExtractPages::test_no_boxes_flow
  tests/test_highlevel_extracttext.py::TestExtractText::test_issue_495_pdfobjref_iterable
  tests/test_highlevel_extracttext.py::TestExtractText::test_issue_566_cid_range
  tests/test_highlevel_extracttext.py::TestExtractText::test_issue_566_cmap_bytes
  tests/test_highlevel_extracttext.py::TestExtractText::test_issue_625_identity_cmap
  tests/test_highlevel_extracttext.py::TestExtractText::test_issue_791_non_unicode_cmap
  tests/test_highlevel_extracttext.py::TestExtractText::test_simple1_no_boxes_flow
  tests/test_highlevel_extracttext.py::TestExtractText::test_simple1_with_file
  tests/test_highlevel_extracttext.py::TestExtractText::test_simple1_with_string
  tests/test_highlevel_extracttext.py::TestExtractText::test_simple3_with_file
  tests/test_highlevel_extracttext.py::TestExtractText::test_simple3_with_string
  tests/test_highlevel_extracttext.py::TestExtractText::test_simple4_with_file
  tests/test_highlevel_extracttext.py::TestExtractText::test_simple4_with_string
  tests/test_highlevel_extracttext.py::TestExtractText::test_simple5_with_file
  tests/test_highlevel_extracttext.py::TestExtractText::test_simple5_with_string
  tests/test_highlevel_extracttext.py::TestExtractText::test_zlib_corrupted
  ... and 40 more

Tests passing in both states: 109
