# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (39):

  tests/oxml/shapes/test_groupshape.py::DescribeCT_GroupShape::it_calculates_its_child_extents_to_help[child_exts_fixture1]
  tests/oxml/shapes/test_groupshape.py::DescribeCT_GroupShape::it_calculates_its_child_extents_to_help[child_exts_fixture2]
  tests/oxml/shapes/test_groupshape.py::DescribeCT_GroupShape::it_calculates_its_child_extents_to_help[child_exts_fixture3]
  tests/shapes/test_base.py::DescribeBaseShape::it_has_a_position[p:cxnSp/p:spPr/a:xfrm-None-None]
  tests/shapes/test_base.py::DescribeBaseShape::it_has_a_position[p:cxnSp/p:spPr/a:xfrm/a:off{x=123,y=456}-123-456]
  tests/shapes/test_base.py::DescribeBaseShape::it_has_a_position[p:graphicFrame/p:xfrm-None-None]
  tests/shapes/test_base.py::DescribeBaseShape::it_has_a_position[p:graphicFrame/p:xfrm/a:off{x=123,y=456}-123-456]
  tests/shapes/test_base.py::DescribeBaseShape::it_has_a_position[p:grpSp/p:grpSpPr/a:xfrm/a:off{x=123,y=456}-123-456]
  tests/shapes/test_base.py::DescribeBaseShape::it_has_a_position[p:pic/p:spPr/a:xfrm-None-None]
  tests/shapes/test_base.py::DescribeBaseShape::it_has_a_position[p:pic/p:spPr/a:xfrm/a:off{x=123,y=456}-123-456]
  tests/shapes/test_base.py::DescribeBaseShape::it_has_a_position[p:sp/p:spPr/a:xfrm-None-None]
  tests/shapes/test_base.py::DescribeBaseShape::it_has_a_position[p:sp/p:spPr/a:xfrm/a:off{x=123,y=456}-123-456]
  tests/shapes/test_connector.py::DescribeConnector::it_can_change_its_begin_point_y_location[begin_y_set_fixture0]
  tests/shapes/test_connector.py::DescribeConnector::it_can_change_its_begin_point_y_location[begin_y_set_fixture1]
  tests/shapes/test_connector.py::DescribeConnector::it_can_change_its_begin_point_y_location[begin_y_set_fixture2]
  tests/shapes/test_connector.py::DescribeConnector::it_can_change_its_begin_point_y_location[begin_y_set_fixture3]
  tests/shapes/test_connector.py::DescribeConnector::it_can_change_its_begin_point_y_location[begin_y_set_fixture4]
  tests/shapes/test_connector.py::DescribeConnector::it_can_change_its_begin_point_y_location[begin_y_set_fixture5]
  tests/shapes/test_connector.py::DescribeConnector::it_can_change_its_end_point_y_location[end_y_set_fixture0]
  tests/shapes/test_connector.py::DescribeConnector::it_can_change_its_end_point_y_location[end_y_set_fixture1]
  ... and 19 more

Tests passing in both states: 2618
