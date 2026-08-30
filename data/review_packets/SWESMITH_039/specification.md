# MIDI message decoding issues with channel, pitchwheel, and songpos

I've found several issues with the MIDI message decoding in the `mido` library. The problems appear to be related to bit manipulation in the decoding process.

## Description

When working with MIDI messages, I noticed that several message types are not being decoded correctly. Specifically:

1. Channel values are incorrectly calculated in `_decode_data_bytes` function
2. Pitchwheel values are incorrectly decoded
3. Song position values are incorrectly decoded
4. Sysex messages are not being processed correctly

## Reproduction

Here's a simple script that demonstrates the issue with pitchwheel and songpos messages:

```python
import mido

# Create a pitchwheel message
pw_msg = mido.Message('pitchwheel', pitch=2000)
# Encode and decode it
encoded = mido.messages.encode.encode_message(pw_msg)
decoded = mido.messages.decode.decode_message(encoded)
print(f"Original pitch: {pw_msg.pitch}, Decoded pitch: {decoded['pitch']}")

# Create a songpos message
sp_msg = mido.Message('songpos', pos=100)
# Encode and decode it
encoded = mido.messages.encode.encode_message(sp_msg)
decoded = mido.messages.decode.decode_message(encoded)
print(f"Original pos: {sp_msg.pos}, Decoded pos: {decoded['pos']}")
```

The output shows that the decoded values don't match the original values.

For channel messages, the issue is in the bit manipulation. The channel is being calculated incorrectly with `args['channel'] = status_byte | 0xf0` instead of extracting the lower 4 bits.

There's also an issue with sysex messages where the condition for checking the end byte is inverted, and the data slicing is incorrect with `data = msg_bytes[:-1]` instead of `data = msg_bytes[1:]`.

## Environment

- Python 3.10
- mido version: latest from main branch

This issue affects all MIDI applications that rely on correctly decoded MIDI messages, especially those working with pitchwheel, songpos, and channel messages.

<END WRITING>
