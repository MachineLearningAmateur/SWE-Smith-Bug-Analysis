# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (7):

  tests/test_article_only.py::TestArticleOnly::test_best_elem_is_root_and_passing
  tests/test_article_only.py::TestArticleOnly::test_correct_cleanup
  tests/test_article_only.py::TestArticleOnly::test_si_sample
  tests/test_article_only.py::TestArticleOnly::test_si_sample_html_partial
  tests/test_article_only.py::TestArticleOnly::test_too_many_images_sample_html_partial
  tests/test_article_only.py::TestArticleOnly::test_utf8_kanji
  tests/test_article_only.py::TestArticleOnly::test_wrong_link_issue_49

Tests passing in both states: 4
