# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (47):

  tests/integration/test_archive_full.py::test_avoid_double_slash_in_rss
  tests/integration/test_archive_full.py::test_full_archive[day]
  tests/integration/test_archive_full.py::test_full_archive[month]
  tests/integration/test_archive_full.py::test_full_archive[overall]
  tests/integration/test_archive_full.py::test_full_archive[year]
  tests/integration/test_archive_full.py::test_index_in_sitemap
  tests/integration/test_archive_per_day.py::test_archive_exists
  tests/integration/test_archive_per_day.py::test_avoid_double_slash_in_rss
  tests/integration/test_archive_per_day.py::test_day_archive
  tests/integration/test_archive_per_day.py::test_index_in_sitemap
  tests/integration/test_archive_per_month.py::test_archive_exists
  tests/integration/test_archive_per_month.py::test_avoid_double_slash_in_rss
  tests/integration/test_archive_per_month.py::test_index_in_sitemap
  tests/integration/test_archive_per_month.py::test_monthly_archive
  tests/integration/test_building_in_subdir.py::test_archive_exists
  tests/integration/test_building_in_subdir.py::test_avoid_double_slash_in_rss
  tests/integration/test_building_in_subdir.py::test_index_in_sitemap
  tests/integration/test_check_absolute_subfolder.py::test_archive_exists
  tests/integration/test_check_absolute_subfolder.py::test_avoid_double_slash_in_rss
  tests/integration/test_check_absolute_subfolder.py::test_index_in_sitemap
  ... and 27 more

Tests passing in both states: 384
