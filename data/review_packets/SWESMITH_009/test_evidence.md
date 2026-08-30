# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (19):

  tests/test_inference.py::InferenceTest::test_aug_different_types_aug_not_implemented
  tests/test_inference.py::InferenceTest::test_aug_different_types_aug_not_implemented_rop_fallback
  tests/test_inference.py::InferenceTest::test_aug_different_types_augop_implemented
  tests/test_inference.py::InferenceTest::test_aug_different_types_no_method_implemented
  tests/test_inference.py::InferenceTest::test_aug_op_same_type_aug_implemented
  tests/test_inference.py::InferenceTest::test_aug_op_same_type_aug_not_implemented_normal_implemented
  tests/test_inference.py::InferenceTest::test_aug_op_subtype_aug_op_is_implemented
  tests/test_inference.py::InferenceTest::test_aug_op_subtype_both_not_implemented
  tests/test_inference.py::InferenceTest::test_aug_op_subtype_normal_op_is_implemented
  tests/test_inference.py::InferenceTest::test_augassign
  tests/test_inference.py::InferenceTest::test_augop_supertypes_augop_implemented
  tests/test_inference.py::InferenceTest::test_augop_supertypes_none_implemented
  tests/test_inference.py::InferenceTest::test_augop_supertypes_normal_binop_implemented
  tests/test_inference.py::InferenceTest::test_augop_supertypes_not_implemented_returned_for_all
  tests/test_inference.py::InferenceTest::test_augop_supertypes_reflected_binop_implemented
  tests/test_inference.py::InferenceTest::test_binary_op_type_errors
  tests/test_inference.py::test_infer_assign_attr
  tests/test_inference.py::test_limit_inference_result_amount
  tests/test_scoped_nodes.py::ClassNodeTest::test_slots_added_dynamically_still_inferred

Tests passing in both states: 1574
