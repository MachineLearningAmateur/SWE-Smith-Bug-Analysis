# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (122):

  tests/test_command.py::TestCommands::test_command_extract
  tests/test_command.py::TestCommands::test_deeppatch_command[t1.csv-t2.csv-args4-0]
  tests/test_command.py::TestCommands::test_deeppatch_command[t1.json-t2.json-args0-0]
  tests/test_command.py::TestCommands::test_deeppatch_command[t1.json-t2_json.csv-args2-0]
  tests/test_command.py::TestCommands::test_deeppatch_command[t1.pickle-t2.pickle-args6-0]
  tests/test_command.py::TestCommands::test_deeppatch_command[t1.toml-t2.toml-args5-0]
  tests/test_command.py::TestCommands::test_deeppatch_command[t1.yaml-t2.yaml-args7-0]
  tests/test_command.py::TestCommands::test_deeppatch_command[t2_json.csv-t1.json-args3-0]
  tests/test_delta.py::TestBasicsOfDelta::test_delta_constr_flat_dict_list_param_preserve
  tests/test_delta.py::TestBasicsOfDelta::test_delta_dict_items_added_retain_order
  tests/test_delta.py::TestBasicsOfDelta::test_delta_dump_and_read1
  tests/test_delta.py::TestBasicsOfDelta::test_delta_dump_and_read2
  tests/test_delta.py::TestBasicsOfDelta::test_delta_dump_and_read3
  tests/test_delta.py::TestBasicsOfDelta::test_delta_mutate
  tests/test_delta.py::TestBasicsOfDelta::test_from_null_delta_json
  tests/test_delta.py::TestBasicsOfDelta::test_list_difference3_delta
  tests/test_delta.py::TestBasicsOfDelta::test_list_difference_add_delta
  tests/test_delta.py::TestBasicsOfDelta::test_list_difference_add_delta_when_index_not_valid
  tests/test_delta.py::TestBasicsOfDelta::test_list_difference_delta1
  tests/test_delta.py::TestBasicsOfDelta::test_list_difference_delta_does_not_raise_error_if_prev_value_changed
  ... and 102 more

Tests passing in both states: 797
