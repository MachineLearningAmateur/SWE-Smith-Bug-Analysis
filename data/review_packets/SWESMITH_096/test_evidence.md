# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (42):

  tests/test_ec2/test_fleets.py::test_create_diversified_spot_fleet
  tests/test_ec2/test_fleets.py::test_create_fleet_api
  tests/test_ec2/test_fleets.py::test_create_fleet_api_response
  tests/test_ec2/test_fleets.py::test_create_fleet_request_with_tags
  tests/test_ec2/test_fleets.py::test_create_fleet_using_launch_template_config__overrides
  tests/test_ec2/test_fleets.py::test_create_fleet_using_launch_template_config__overrides_single[overrides0]
  tests/test_ec2/test_fleets.py::test_create_fleet_using_launch_template_config__overrides_single[overrides1]
  tests/test_ec2/test_fleets.py::test_create_on_demand_fleet
  tests/test_ec2/test_fleets.py::test_create_spot_fleet_with_lowest_price
  tests/test_ec2/test_fleets.py::test_delete_fleet
  tests/test_ec2/test_fleets.py::test_describe_fleet_instances_api
  tests/test_ec2/test_fleets.py::test_launch_template_is_created_properly
  tests/test_ec2/test_fleets.py::test_request_fleet_using_launch_template_config__name[lowestPrice-capacity-optimized-prioritized]
  tests/test_ec2/test_fleets.py::test_request_fleet_using_launch_template_config__name[lowestPrice-capacity-optimized]
  tests/test_ec2/test_fleets.py::test_request_fleet_using_launch_template_config__name[lowestPrice-diversified]
  tests/test_ec2/test_fleets.py::test_request_fleet_using_launch_template_config__name[lowestPrice-lowest-price]
  tests/test_ec2/test_fleets.py::test_request_fleet_using_launch_template_config__name[prioritized-capacity-optimized-prioritized]
  tests/test_ec2/test_fleets.py::test_request_fleet_using_launch_template_config__name[prioritized-capacity-optimized]
  tests/test_ec2/test_fleets.py::test_request_fleet_using_launch_template_config__name[prioritized-diversified]
  tests/test_ec2/test_fleets.py::test_request_fleet_using_launch_template_config__name[prioritized-lowest-price]
  ... and 22 more

Tests passing in both states: 60
