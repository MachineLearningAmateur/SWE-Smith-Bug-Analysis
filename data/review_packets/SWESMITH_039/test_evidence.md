# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests (15):

  ../dev/tests/messages/test_decode.py::test_channel
  ../dev/tests/messages/test_decode.py::test_sysex
  ../dev/tests/messages/test_decode.py::test_sysex_end
  ../dev/tests/messages/test_decode.py::test_sysex_without_stop_byte
  ../dev/tests/messages/test_encode.py::test_encode_decode_all
  ../dev/tests/messages/test_messages.py::test_decode_pitchwheel
  ../dev/tests/messages/test_messages.py::test_decode_songpos
  ../dev/tests/midifiles/test_midifiles.py::test_invalid_data_byte_with_clipping_high
  ../dev/tests/midifiles/test_midifiles.py::test_single_message
  ../dev/tests/test_parser.py::test_encode_and_parse
  ../dev/tests/test_parser.py::test_encode_and_parse_all
  ../dev/tests/test_parser.py::test_parse
  ../dev/tests/test_parser.py::test_parse_channel
  ../dev/tests/test_syx.py::test_handle_any_whitespace
  ../dev/tests/test_syx.py::test_read

Tests passing in both states: 107
