### Bug: Address Parsing Error with Port Zero

#### Bug Summary

The `parse_address` function in the `mido.sockets` module is not handling port zero correctly. According to the expected behavior, port zero should raise a `ValueError`, but it seems to be accepted without any error.

#### Steps to Reproduce

1. Use the `parse_address` function with an address string that includes port zero, such as `"localhost:0"`.
2. Observe that no error is raised, and the function returns the tuple `("localhost", 0)`.

#### Expected Outcome

A `ValueError` should be raised indicating that port zero is not allowed.

#### Actual Outcome

The function returns the tuple `("localhost", 0)` without raising any error.

#### Environment

- **Operating System**: Linux
- **Python Version**: 3.10.16
- **Installation Method**: Not specified

This issue affects the validation of port numbers, potentially leading to unexpected behavior when port zero is used.
