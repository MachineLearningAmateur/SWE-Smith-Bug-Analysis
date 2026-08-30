# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (382):

  tests/test_core.py::TestComponents::test_components_can_be_accessed_by_plugin_in_init_spec
  tests/test_ext_marshmallow.py::TestCircularReference::test_circular_referencing_schemas[2.0]
  tests/test_ext_marshmallow.py::TestCircularReference::test_circular_referencing_schemas[3.0.0]
  tests/test_ext_marshmallow.py::TestComponentHeaderHelper::test_can_use_schema_in_header[PetSchema-3.0.0]
  tests/test_ext_marshmallow.py::TestComponentHeaderHelper::test_can_use_schema_in_header[schema1-3.0.0]
  tests/test_ext_marshmallow.py::TestComponentParameterHelper::test_can_use_schema_in_parameter[2.0-PetSchema]
  tests/test_ext_marshmallow.py::TestComponentParameterHelper::test_can_use_schema_in_parameter[2.0-schema1]
  tests/test_ext_marshmallow.py::TestComponentParameterHelper::test_can_use_schema_in_parameter[3.0.0-PetSchema]
  tests/test_ext_marshmallow.py::TestComponentParameterHelper::test_can_use_schema_in_parameter[3.0.0-schema1]
  tests/test_ext_marshmallow.py::TestComponentParameterHelper::test_can_use_schema_in_parameter_with_content[PetSchema-3.0.0]
  tests/test_ext_marshmallow.py::TestComponentParameterHelper::test_can_use_schema_in_parameter_with_content[schema1-3.0.0]
  tests/test_ext_marshmallow.py::TestComponentResponseHelper::test_can_use_schema_in_response[2.0-PetSchema]
  tests/test_ext_marshmallow.py::TestComponentResponseHelper::test_can_use_schema_in_response[2.0-schema1]
  tests/test_ext_marshmallow.py::TestComponentResponseHelper::test_can_use_schema_in_response[3.0.0-PetSchema]
  tests/test_ext_marshmallow.py::TestComponentResponseHelper::test_can_use_schema_in_response[3.0.0-schema1]
  tests/test_ext_marshmallow.py::TestComponentResponseHelper::test_can_use_schema_in_response_header[2.0-PetSchema]
  tests/test_ext_marshmallow.py::TestComponentResponseHelper::test_can_use_schema_in_response_header[2.0-schema1]
  tests/test_ext_marshmallow.py::TestComponentResponseHelper::test_can_use_schema_in_response_header[3.0.0-PetSchema]
  tests/test_ext_marshmallow.py::TestComponentResponseHelper::test_can_use_schema_in_response_header[3.0.0-schema1]
  tests/test_ext_marshmallow.py::TestComponentResponseHelper::test_content_without_schema[3.0.0]
  ... and 362 more

Tests passing in both states: 177
