IoT Data Publish fails with binary payloads

Description

When trying to publish binary data to an IoT topic, the operation fails with a UnicodeDecodeError. This happens when the payload contains non-UTF-8 bytes.

The following code reproduces the issue:

```python
import boto3

client = boto3.client('iot-data', region_name='ap-northeast-1')

# This works fine
client.publish(topic='test/topic1', qos=1, payload=b'normal text')

# This fails with UnicodeDecodeError
client.publish(topic='test/topic3', qos=1, payload=b'\xbf')
```

The error occurs because the binary payload is being processed incorrectly. The system is trying to decode binary data that isn't valid UTF-8.

This is a regression - binary payloads used to work correctly in previous versions.
