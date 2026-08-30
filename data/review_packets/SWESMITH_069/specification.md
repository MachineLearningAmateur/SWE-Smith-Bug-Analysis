# UTF-8 header values not properly decoded in WSGIHeaderDict

I'm having an issue with header values containing UTF-8 characters not being properly handled in Bottle.

When I send a request with a UTF-8 header value, the value gets corrupted when accessed through `request.get_header()`.

## Reproduction

Here's a simple example that demonstrates the issue:

```python
from bottle import route, run, request, response

@route('/test')
def test():
    # Get the header value
    h = request.get_header('X-Test')
    print(f"Received header: {h}")
    
    # Echo it back in the response
    response.set_header('X-Test', h)
    return "Check the response headers"

run(host='localhost', port=8080)
```

When I send a request with a UTF-8 header like 'öäü', the value gets corrupted. Instead of getting the correct characters, I get something like 'Ã¶Ã¤Ã¼'.

## Expected behavior

The header value should be properly decoded from UTF-8 to Unicode when accessed through `request.get_header()`.

## Actual behavior

The header value is incorrectly decoded, resulting in corrupted characters.

This seems to be related to how the `WSGIHeaderDict.__getitem__` method handles encoding/decoding of header values.
