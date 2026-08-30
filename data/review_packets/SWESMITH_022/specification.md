### Bug Report: `parse_time` Function Fails with Certain Timestamps

Hello,

I've encountered an issue with the `parse_time` function in the GPX module. It seems that the function is not handling certain timestamp formats correctly, resulting in an exception being raised.

### Steps to Reproduce

1. Use the `parse_time` function with the following timestamps:
   - `2001-10-26T21:32:52`
   - `2001-10-26T19:32:52Z`
   - `2001-10-26T21:32:52.12679`
   - `2001-10-26T21:32:52`
   - `2001-10-26T19:32:52Z`
   - `2001-10-26T21:32:52.12679`

2. Observe that the function raises an exception for these inputs.

### Expected Behavior

The `parse_time` function should successfully parse all valid ISO 8601 timestamps without raising exceptions.

### Actual Behavior

The function raises a `GPXException` indicating an invalid timestamp format for the inputs mentioned above.

### Environment

- Python version: 3.10.16
- GPX module version: [Please specify]
- Operating System: [Please specify]

It would be great if this could be looked into. Let me know if you need any more information.

Thanks!
