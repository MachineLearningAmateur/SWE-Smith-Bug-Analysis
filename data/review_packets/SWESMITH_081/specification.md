# Empty chunk size in HTTP chunked encoding not properly validated

## Description

When processing HTTP chunked encoding, the current implementation fails to properly validate empty chunk sizes. The code is supposed to raise an `InvalidChunkSize` exception when a chunk size is empty, but this validation has been removed.

## How to Reproduce

This issue can be reproduced when handling HTTP requests with chunked encoding that contain empty chunk sizes. For example:

```python
from gunicorn.http.body import ChunkedReader
from io import BytesIO

# Create a request with an empty chunk size
data = BytesIO(b"\r\n0\r\n\r\n")  # Empty chunk size followed by terminating chunk
reader = ChunkedReader(data, 8192)

# This should raise an InvalidChunkSize exception but doesn't
try:
    content = reader.read()
    print("Error: Empty chunk size was accepted")
except Exception as e:
    print(f"Correctly raised: {e}")
```

The expected behavior is for the code to raise an `InvalidChunkSize` exception when it encounters an empty chunk size, but after the recent changes, it incorrectly accepts empty chunk sizes.

## Expected Behavior

The code should validate that chunk sizes are not empty and raise an `InvalidChunkSize` exception when an empty chunk size is encountered, as per the HTTP specification.

This issue affects the handling of malformed HTTP requests and could potentially lead to security vulnerabilities by allowing improperly formatted chunked requests to be processed.
