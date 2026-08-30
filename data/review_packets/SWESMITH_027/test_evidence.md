# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (30):

  test.py::GPXTests::test_add_missing_elevations
  test.py::GPXTests::test_add_missing_elevations_without_ele
  test.py::GPXTests::test_add_missing_speeds
  test.py::GPXTests::test_add_missing_times_2
  test.py::GPXTests::test_clone_and_smooth
  test.py::GPXTests::test_distance
  test.py::GPXTests::test_distance_between_points_near_0_longitude
  test.py::GPXTests::test_haversine_and_nonhaversine
  test.py::GPXTests::test_horizontal_and_vertical_smooth_remove_extremes
  test.py::GPXTests::test_horizontal_smooth_remove_extremes
  test.py::GPXTests::test_ignore_maximums_for_max_speed
  test.py::GPXTests::test_location_equator_delta_distance_50
  test.py::GPXTests::test_location_nonequator_delta_distance_50
  test.py::GPXTests::test_moving_stopped_times
  test.py::GPXTests::test_named_tuples_values_moving_data
  test.py::GPXTests::test_named_tuples_values_nearest_location_data
  test.py::GPXTests::test_named_tuples_values_point_data
  test.py::GPXTests::test_nearest_location_1
  test.py::GPXTests::test_positions_on_track
  test.py::GPXTests::test_positions_on_track_2
  ... and 10 more

Tests passing in both states: 113
