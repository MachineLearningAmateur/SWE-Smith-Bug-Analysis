# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (129):

  test/test_error_recovery.py::test_invalid_token_in_fstr
  test/test_file_python_errors.py::test_on_itself[3.10]
  test/test_file_python_errors.py::test_on_itself[3.6]
  test/test_file_python_errors.py::test_on_itself[3.7]
  test/test_file_python_errors.py::test_on_itself[3.8]
  test/test_file_python_errors.py::test_on_itself[3.9]
  test/test_fstring.py::test_invalid[f"""//N{NO/nENTRY}"""]
  test/test_fstring.py::test_invalid[f"""{"""]
  test/test_fstring.py::test_invalid[f"""}"""]
  test/test_fstring.py::test_invalid[f"{!:}"]
  test/test_fstring.py::test_invalid[f"{!a}"]
  test/test_fstring.py::test_invalid[f"{!{a}}"]
  test/test_fstring.py::test_invalid[f"{!}"]
  test/test_fstring.py::test_invalid[f"{"]
  test/test_fstring.py::test_invalid[f"{1!{a}}"]
  test/test_fstring.py::test_invalid[f"{1:{:}}"]
  test/test_fstring.py::test_invalid[f"{1:{}}"]
  test/test_fstring.py::test_invalid[f"{1=!{a}}"]
  test/test_fstring.py::test_invalid[f"{:1}"]
  test/test_fstring.py::test_invalid[f"{:}"]
  ... and 109 more

Tests passing in both states: 671
