HTTP1Connection.finish() doesn't properly close connection when returning early

Description

When a handler returns early from a streaming request, the connection doesn't properly close, causing the client to hang indefinitely.

Consider the following scenario:

```python
class EarlyReturnHandler(RequestHandler):
    @stream_request_body
    def post(self):
        # Return early without consuming the entire request body
        self.finish()

# Client code
response = requests.post('http://localhost:8888/early_return', 
                        data='some data', 
                        stream=True)
# Client hangs here waiting for the server to close the connection
```

The client will hang indefinitely waiting for the server to close the connection, because the server doesn't properly handle the case when a handler returns early from a streaming request.

To reproduce:
1. Create a server with a handler that uses `@stream_request_body` and calls `finish()` early
2. Send a POST request to this handler
3. Observe that the client hangs waiting for the connection to close

This issue appears to be related to how the HTTP1Connection handles the case when a handler finishes before reading the entire request body.
