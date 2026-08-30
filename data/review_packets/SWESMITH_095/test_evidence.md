# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (4):

  tests/opc/test_package.py::Describe_Relationships::and_it_raises_ValueError_when_there_is_more_than_one_part_with_reltype
  tests/opc/test_package.py::Describe_Relationships::but_it_raises_KeyError_when_there_is_no_such_part
  tests/opc/test_package.py::Describe_Relationships::it_can_find_a_part_with_reltype
  tests/test_package.py::DescribePackage::it_provides_access_to_its_core_properties_part

Tests passing in both states: 2653
