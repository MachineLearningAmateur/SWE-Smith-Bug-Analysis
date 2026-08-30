# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (5438):

  tests/benchmarks/test_attribute_access.py::test_getattr
  tests/benchmarks/test_attribute_access.py::test_setattr
  tests/benchmarks/test_discriminated_unions.py::test_efficiency_with_highly_nested_examples
  tests/benchmarks/test_discriminated_unions.py::test_schema_build
  tests/benchmarks/test_fastapi_startup_generics.py::test_fastapi_startup_perf
  tests/benchmarks/test_fastapi_startup_simple.py::test_fastapi_startup_perf
  tests/benchmarks/test_imports.py::test_import_basemodel
  tests/benchmarks/test_imports.py::test_import_field
  tests/benchmarks/test_isinstance.py::test_isinstance_basemodel
  tests/benchmarks/test_model_schema_generation.py::test_complex_model_schema_generation
  tests/benchmarks/test_model_schema_generation.py::test_construct_dataclass_schema
  tests/benchmarks/test_model_schema_generation.py::test_failed_rebuild
  tests/benchmarks/test_model_schema_generation.py::test_field_validators_serializers
  tests/benchmarks/test_model_schema_generation.py::test_lots_of_models_with_lots_of_fields
  tests/benchmarks/test_model_schema_generation.py::test_model_validators_serializers
  tests/benchmarks/test_model_schema_generation.py::test_nested_model_schema_generation
  tests/benchmarks/test_model_schema_generation.py::test_recursive_model_schema_generation
  tests/benchmarks/test_model_schema_generation.py::test_simple_model_schema_generation
  tests/benchmarks/test_model_schema_generation.py::test_simple_model_schema_lots_of_fields_generation
  tests/benchmarks/test_model_schema_generation.py::test_tagged_union_with_callable_discriminator_schema_generation
  ... and 5418 more

Tests passing in both states: 0
