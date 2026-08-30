### Issue with Decoding Encapsulated Pixel Data

#### What happened?

While working with encapsulated pixel data, an unexpected `ValueError` is raised when attempting to decode certain multi-frame images. The error seems to occur when processing the fragments of the pixel data, particularly when the Basic Offset Table (BOT) is empty or when frames are composed of multiple fragments.

#### What did you expect to happen?

The decoding process should handle multi-frame images with varying fragment structures without raising errors, correctly returning the expected list of byte sequences for each frame.

#### Minimal Complete Verifiable Example

Here's a snippet to reproduce the issue:

```python
bytestream = b'\xfe\xff\x00\xe0\x0c\x00\x00\x00\x00\x00\x00\x00\x0c\x00\x00\x00\x18\x00\x00\x00\xfe\xff\x00\xe0\x04\x00\x00\x00\x01\x00\x00\x00\xfe\xff\x00\xe0\x04\x00\x00\x00\x02\x00\x00\x00\xfe\xff\x00\xe0\x04\x00\x00\x00\x03\x00\x00\x00'
frames = _decode_data_sequence(bytestream)
```

#### MVCE confirmation

- [ ] Minimal example — the example is as focused as reasonably possible to demonstrate the underlying issue.
- [ ] Complete example — the example is self-contained, including all data and the text of any traceback.
- [ ] Verifiable example — the example copy & pastes into an IPython prompt or similar environment, returning the result.
- [ ] New issue — a search of GitHub Issues suggests this is not a duplicate.

#### Relevant log output

```plaintext
ValueError: Unexpected tag '0xFFFEE000' when parsing the pixel data fragment items
```

#### Anything else we need to know?

The issue seems to be related to the handling of the Basic Offset Table and the sequence of fragments. It appears when the BOT is empty or when frames are composed of multiple fragments, leading to unexpected behavior during the parsing process.
