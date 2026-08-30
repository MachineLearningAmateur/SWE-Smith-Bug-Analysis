# WebsocketConsumer fails to handle messages with text=None

**Describe the bug**
When a WebSocket message is received with a "text" key that has a value of `None`, the consumer throws a KeyError. This happens because the code checks if "text" is in the message, but then tries to access message["text"] without checking if the value is None.

**To Reproduce**
Create a simple WebSocket consumer and send a message with text=None:

```python
from channels.generic.websocket import WebsocketConsumer

class MyConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()
        
    def receive(self, text_data=None, bytes_data=None):
        print(f"Received: text={text_data}, bytes={bytes_data}")

# Then in your application, if you send:
message = {"text": None}
consumer.websocket_receive(message)  # This will fail with KeyError
```

**Expected behavior**
The consumer should properly handle messages where "text" is present but has a value of None, treating it similar to how it would handle bytes data.

**Environment info**
- Django Channels version: 4.0.0
- Django version: 5.1.6
- Python version: 3.10

**Additional context**
This issue affects both the synchronous `WebsocketConsumer` and asynchronous `AsyncWebsocketConsumer` classes. The problem is that the code checks if "text" is in the message dictionary, but doesn't verify that the value isn't None before trying to use it.
